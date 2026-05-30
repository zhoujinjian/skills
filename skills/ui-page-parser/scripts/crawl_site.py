#!/usr/bin/env python3
"""
crawl_site.py — 全站自动爬取：从入口 URL 发现并抓取所有可访问页面

BFS 爬虫，使用 Playwright 渲染 SPA 页面，自动发现链接、归组参数化 URL、检测认证保护。

用法：
    python3 crawl_site.py http://localhost:3000/ [options]

输出 JSON 结构：
{
  "crawl_summary": { ... },
  "pages": [ { url, path, title, depth, auth_blocked, elements, text_structure, screenshot } ],
  "url_patterns": [ { pattern, sample_urls, all_discovered_urls } ],
  "auth_blocked_urls": [ { url, redirect_to } ]
}
"""

import sys
import os
import json
import re
import argparse
import asyncio
import dataclasses
import urllib.parse
from collections import deque
from datetime import datetime, timezone

# 从 fetch_dom.py 导入共享的 JS 常量和工具函数
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_dom import DOM_EXTRACT_SCRIPT, TEXT_STRUCTURE_SCRIPT, check_cdp_available


# ── JS：从渲染后页面提取所有链接 ─────────────────────────────

LINK_DISCOVERY_SCRIPT = """
() => {
    const links = [];
    const seen = new Set();

    // 1. 标准 <a href> 链接
    document.querySelectorAll('a[href]').forEach(a => {
        const href = a.getAttribute('href');
        if (!href) return;
        if (href.startsWith('#') || href.startsWith('javascript:') || href.startsWith('mailto:')) return;
        const text = (a.textContent || '').trim().substring(0, 100);
        const key = href + '|' + text;
        if (seen.has(key)) return;
        seen.add(key);
        links.push({ href, text });
    });

    // 2. Vue Router 的 router-link 渲染结果（可能用 data-* 属性）
    document.querySelectorAll('[data-to], [data-route], [data-path]').forEach(el => {
        const href = el.getAttribute('data-to') || el.getAttribute('data-route') || el.getAttribute('data-path');
        if (!href || seen.has(href)) return;
        seen.add(href);
        links.push({ href, text: (el.textContent || '').trim().substring(0, 100) });
    });

    // 3. 可点击元素中的 onclick 包含路由跳转模式
    document.querySelectorAll('[onclick]').forEach(el => {
        const handler = el.getAttribute('onclick') || '';
        const patterns = [
            /router\\.push\\(['"](.*?)['"]/,
            /location\\.href\\s*=\\s*['"](.*?)['"]/,
            /window\\.location\\s*=\\s*['"](.*?)['"]/,
            /navigate\\(['"](.*?)['"]/,
        ];
        for (const p of patterns) {
            const m = handler.match(p);
            if (m && !seen.has(m[1])) {
                seen.add(m[1]);
                links.push({ href: m[1], text: (el.textContent || '').trim().substring(0, 100) });
            }
        }
    });

    return links;
}
"""

# ── JS：从 Vue Router 提取全站路由表 ─────────────────────────

VUE_ROUTER_DISCOVERY_SCRIPT = """
() => {
    const routes = [];
    try {
        // Vue 3: 访问 app 实例上的 router
        const appEl = document.querySelector('#app') || document.querySelector('[data-v-app]');
        if (appEl && appEl.__vue_app__) {
            const app = appEl.__vue_app__;
            const router = app.config && app.config.globalProperties && app.config.globalProperties.$router;
            if (router && router.getRoutes) {
                router.getRoutes().forEach(r => {
                    routes.push({
                        path: r.path || '',
                        name: r.name || '',
                        meta: r.meta || {},
                        has_params: (r.path || '').includes(':')
                    });
                });
            }
        }
        // Vue 2 fallback
        if (routes.length === 0) {
            const vm = document.querySelector('#app').__vue__;
            if (vm && vm.$router && vm.$router.options && vm.$router.options.routes) {
                vm.$router.options.routes.forEach(r => {
                    routes.push({
                        path: r.path || '',
                        name: r.name || '',
                        meta: r.meta || {},
                        has_params: (r.path || '').includes(':')
                    });
                });
            }
        }
    } catch(e) {}
    return routes;
}
"""


# ── 数据类 ────────────────────────────────────────────────────

@dataclasses.dataclass
class CrawlConfig:
    entry_url: str
    max_depth: int = 3
    max_pages: int = 50
    timeout: int = 30000
    cdp_port: int = 9222
    force_launch: bool = False
    wait_for: str | None = None
    no_screenshot: bool = False
    screenshots_dir: str = "./screenshots"
    pattern_samples: int = 2
    delay_ms: int = 500
    verbose: bool = False
    storage_state: str | None = None


@dataclasses.dataclass
class UrlPatternGroup:
    pattern: str
    parameter_name: str
    all_urls: set = dataclasses.field(default_factory=set)
    sample_urls: list = dataclasses.field(default_factory=list)
    crawled_count: int = 0


# ── URL 工具函数 ──────────────────────────────────────────────

_STATIC_EXTENSIONS = re.compile(
    r'\.(png|jpg|jpeg|gif|svg|ico|css|js|woff2?|ttf|eot|pdf|zip|mp4|webp)(\?.*)?$',
    re.IGNORECASE
)

_NUMERIC_SEGMENT = re.compile(r'^\d+$')


def normalize_url(url: str, base_url: str) -> str:
    """规范化 URL：解析相对路径、去 fragment、排序参数、去尾斜杠"""
    resolved = urllib.parse.urljoin(base_url, url)
    parsed = urllib.parse.urlresolves(resolved) if hasattr(urllib.parse, 'urlresolves') else urllib.parse.urlparse(resolved)
    # 去 fragment
    # 排序 query 参数
    if parsed.query:
        params = urllib.parse.parse_qsl(parsed.query)
        params.sort()
        query = urllib.parse.urlencode(params)
    else:
        query = ''
    # 重建
    normalized = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip('/') or '/', '', query, ''))
    return normalized


def is_same_origin(url: str, base_origin: str) -> bool:
    """检查 URL 是否与 base 同源"""
    parsed = urllib.parse.urlparse(url)
    base = urllib.parse.urlparse(base_origin)
    return parsed.scheme == base.scheme and parsed.netloc == base.netloc


def is_static_asset(url: str) -> bool:
    """检查是否为静态资源 URL"""
    parsed = urllib.parse.urlparse(url)
    return bool(_STATIC_EXTENSIONS.search(parsed.path))


def classify_url_pattern(url: str) -> tuple[str | None, str | None]:
    """
    检测参数化 URL 模式。
    /product/5 → ("/product/{product}", "product")
    /user/order/123 → ("/user/order/{order}", "order")
    /about → (None, None)
    """
    parsed = urllib.parse.urlparse(url)
    segments = [s for s in parsed.path.split('/') if s]
    has_param = False
    param_name = None
    for i, seg in enumerate(segments):
        if _NUMERIC_SEGMENT.match(seg):
            param_name = segments[i - 1] if i > 0 else "id"
            segments[i] = "{" + param_name + "}"
            has_param = True
    if has_param:
        pattern = '/' + '/'.join(segments)
        return pattern, param_name
    return None, None


def path_to_filename(path: str) -> str:
    """URL 路径转安全的文件名：/product/1 → product_1"""
    name = path.strip('/').replace('/', '_') or '_'
    return name


# ── 认证检测 ──────────────────────────────────────────────────

AUTH_PATHS = {'/login', '/register', '/auth/login', '/auth/register'}


def detect_auth_redirect(requested_url: str, final_url: str) -> bool:
    """检测是否被重定向到登录页（仅当目标不是认证页本身时才算拦截）"""
    requested_parsed = urllib.parse.urlparse(requested_url)
    final_parsed = urllib.parse.urlparse(final_url)
    final_path = final_parsed.path
    requested_path = requested_parsed.path

    # 如果用户就是要访问 login/register，不算拦截
    if requested_path in AUTH_PATHS:
        return False

    # 最终落在认证页面，且原始请求不是认证页 → 被拦截
    if final_path in AUTH_PATHS:
        return True

    # 检查 redirect 参数
    redirect_param = urllib.parse.parse_qs(final_parsed.query).get('redirect', [])
    if requested_path in redirect_param:
        return True

    return False


# ── 爬虫主类 ──────────────────────────────────────────────────

class CrawlSite:
    def __init__(self, config: CrawlConfig):
        self.config = config
        parsed = urllib.parse.urlparse(config.entry_url)
        self.base_origin = f"{parsed.scheme}://{parsed.netloc}"

        self.frontier: deque[tuple[str, int]] = deque()
        self.visited: set[str] = set()
        self.queued: set[str] = set()
        self.results: list[dict] = []
        self.auth_blocked_list: list[dict] = []
        self.url_patterns: dict[str, UrlPatternGroup] = {}
        self.discovered_from: dict[str, str] = {}  # url → discovered_from_url

        self.browser = None
        self.context = None
        self._start_time = None
        self._auth_mode = None

    def log(self, msg: str):
        if self.config.verbose:
            print(msg, file=sys.stderr)

    async def run(self) -> dict:
        self._start_time = datetime.now(timezone.utc)
        await self._init_browser()

        # 种子 URL 入队
        seed = normalize_url(self.config.entry_url, self.config.entry_url)
        self.frontier.append((seed, 0))
        self.queued.add(seed)

        try:
            while self.frontier and len(self.results) < self.config.max_pages:
                url, depth = self.frontier.popleft()

                if depth > self.config.max_depth:
                    self.log(f"  跳过（深度超限）: {url} depth={depth}")
                    continue

                self.visited.add(url)
                self.log(f"[{len(self.results)+1}/{self.config.max_pages}] depth={depth} {url}")

                page_data = await self._crawl_page(url, depth)
                self.results.append(page_data)

                # 认证被拦截 → 不发现链接
                if page_data.get("auth_blocked"):
                    from_url = self.discovered_from.get(url, "seed")
                    self.auth_blocked_list.append({
                        "url": url,
                        "redirect_to": page_data.get("final_url", ""),
                        "discovered_from": from_url,
                    })
                    self.log(f"  ✗ 需认证: {url}")
                    continue

                # 发现新链接
                if page_data.get("raw_links") and not page_data.get("error"):
                    new_links = self._process_discovered_links(
                        page_data["raw_links"], url, depth + 1
                    )
                    self.log(f"  发现 {len(new_links)} 个新链接")

                # 处理 Vue Router 路由表（将路由路径加入队列）
                if page_data.get("vue_routes"):
                    self._process_vue_routes(page_data["vue_routes"], url, depth + 1)

                # 页面间隔
                await asyncio.sleep(self.config.delay_ms / 1000.0)

        finally:
            await self._close_browser()

        return self._build_output()

    async def _init_browser(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            print("错误：playwright 未安装。请运行 pip install playwright && playwright install chromium", file=sys.stderr)
            sys.exit(1)

        use_cdp = (not self.config.force_launch) and check_cdp_available(self.config.cdp_port)
        self._fetch_mode = "cdp_connect" if use_cdp else "launch"

        self._playwright = await async_playwright().__aenter__()

        if use_cdp:
            print(f"CDP 模式：连接 localhost:{self.config.cdp_port}", file=sys.stderr)
            self._auth_mode = "cdp_authenticated"
            self.browser = await self._playwright.chromium.connect_over_cdp(
                f"http://localhost:{self.config.cdp_port}"
            )
            self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context(
                viewport={"width": 1440, "height": 900}
            )
        else:
            print("Launch 模式：直接启动无头浏览器", file=sys.stderr)
            self.browser = await self._playwright.chromium.launch(headless=True)
            context_kwargs = {
                "viewport": {"width": 1440, "height": 900},
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            }
            if self.config.storage_state:
                print(f"注入 Storage State: {self.config.storage_state}", file=sys.stderr)
                context_kwargs["storage_state"] = self.config.storage_state
                self._auth_mode = "storage_state"
            self.context = await self.browser.new_context(**context_kwargs)

    async def _close_browser(self):
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.__aexit__(None, None, None)
            except Exception:
                pass

    async def _crawl_page(self, url: str, depth: int) -> dict:
        page = await self.context.new_page()
        result = {
            "url": url,
            "path": urllib.parse.urlparse(url).path,
            "title": "",
            "depth": depth,
            "auth_blocked": False,
            "final_url": url,
            "elements": [],
            "text_structure": [],
            "raw_links": [],
            "screenshot": None,
            "fetch_mode": self._fetch_mode,
            "error": None,
        }

        try:
            await page.goto(url, timeout=self.config.timeout, wait_until="domcontentloaded")

            # 等待策略
            if self.config.wait_for:
                await page.wait_for_selector(self.config.wait_for, timeout=self.config.timeout)
            else:
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass

            final_url = page.url
            result["final_url"] = final_url

            # 认证检测
            if detect_auth_redirect(url, final_url):
                result["auth_blocked"] = True
                result["title"] = await page.title()
                if self._auth_mode:
                    self.log(f"  ⚠ 认证会话可能已过期（auth_mode={self._auth_mode}），页面仍被重定向到登录页")
                await page.close()
                return result

            # 提取数据
            result["title"] = await page.title()
            result["elements"] = await page.evaluate(DOM_EXTRACT_SCRIPT)
            result["text_structure"] = await page.evaluate(TEXT_STRUCTURE_SCRIPT)
            result["raw_links"] = await page.evaluate(LINK_DISCOVERY_SCRIPT)

            # Vue Router 路由发现（仅在首页执行一次）
            if depth == 0:
                vue_routes = await page.evaluate(VUE_ROUTER_DISCOVERY_SCRIPT)
                if vue_routes:
                    result["vue_routes"] = vue_routes
                    self.log(f"  Vue Router 发现 {len(vue_routes)} 条路由")

            # 截图
            if not self.config.no_screenshot:
                os.makedirs(self.config.screenshots_dir, exist_ok=True)
                filename = path_to_filename(result["path"]) + ".png"
                screenshot_path = os.path.join(self.config.screenshots_dir, filename)
                await page.screenshot(path=screenshot_path, full_page=False)
                result["screenshot"] = screenshot_path

            self.log(f"  ✓ title='{result['title']}' elements={len(result['elements'])} links={len(result['raw_links'])}")

        except Exception as e:
            result["error"] = str(e)
            self.log(f"  ✗ 错误: {e}")

        finally:
            await page.close()

        return result

    def _process_vue_routes(self, vue_routes: list[dict], source_url: str, next_depth: int):
        """将 Vue Router 路由表中的路径加入爬取队列"""
        for route in vue_routes:
            path = route.get("path", "")
            if not path or path == "/:pathMatch(.*)*" or "*" in path:
                continue

            # 含参数的路由：尝试用 sample_id 1 替换
            if route.get("has_params"):
                # /product/:id → /product/1
                sample_path = re.sub(r':\w+', '1', path)
                sample_url = self.base_origin + sample_path
            else:
                sample_url = self.base_origin + path

            normalized = normalize_url(sample_url, source_url)
            if normalized in self.queued:
                continue
            if not is_same_origin(normalized, self.base_origin):
                continue
            if is_static_asset(normalized):
                continue

            # 参数化路由归组
            if route.get("has_params"):
                pattern, param_name = classify_url_pattern(normalized)
                if pattern:
                    group = self.url_patterns.get(pattern)
                    if group is None:
                        group = UrlPatternGroup(pattern=pattern, parameter_name=param_name or "id")
                        self.url_patterns[pattern] = group
                    group.all_urls.add(normalized)

                    if group.crawled_count >= self.config.pattern_samples:
                        self.queued.add(normalized)
                        continue
                    group.crawled_count += 1
                    group.sample_urls.append(normalized)

            if next_depth <= self.config.max_depth:
                self.frontier.append((normalized, next_depth))
                self.queued.add(normalized)
                self.discovered_from[normalized] = source_url
                self.log(f"  [Vue Route] {path} → {normalized}")

    def _process_discovered_links(self, raw_links: list[dict], source_url: str, next_depth: int) -> list[str]:
        """处理发现的链接，入队新 URL，返回新入队的 URL 列表"""
        new_urls = []

        for link in raw_links:
            href = link.get("href", "")
            if not href:
                continue

            try:
                normalized = normalize_url(href, source_url)
            except Exception:
                continue

            # 过滤
            if normalized in self.queued:
                continue
            if not is_same_origin(normalized, self.base_origin):
                continue
            if is_static_asset(normalized):
                continue

            # 参数化 URL 归组
            pattern, param_name = classify_url_pattern(normalized)
            if pattern:
                group = self.url_patterns.get(pattern)
                if group is None:
                    group = UrlPatternGroup(pattern=pattern, parameter_name=param_name or "id")
                    self.url_patterns[pattern] = group
                group.all_urls.add(normalized)

                if group.crawled_count >= self.config.pattern_samples:
                    # 已达采样上限，标记为已发现但不爬取
                    self.queued.add(normalized)
                    continue
                group.crawled_count += 1
                group.sample_urls.append(normalized)

            # 入队
            if next_depth <= self.config.max_depth:
                self.frontier.append((normalized, next_depth))
                self.queued.add(normalized)
                self.discovered_from[normalized] = source_url
                new_urls.append(normalized)

        return new_urls

    def _build_output(self) -> dict:
        end_time = datetime.now(timezone.utc)
        duration = (end_time - self._start_time).total_seconds() if self._start_time else 0

        total_pattern_skipped = sum(
            len(g.all_urls) - len(g.sample_urls)
            for g in self.url_patterns.values()
        )

        return {
            "crawl_summary": {
                "entry_url": self.config.entry_url,
                "base_origin": self.base_origin,
                "auth_mode": self._auth_mode,
                "total_discovered_urls": len(self.queued),
                "total_crawled": len(self.results),
                "total_auth_blocked": len(self.auth_blocked_list),
                "total_pattern_skipped": total_pattern_skipped,
                "max_depth_reached": max((r["depth"] for r in self.results), default=0),
                "crawl_duration_seconds": round(duration, 1),
                "config": {
                    "max_depth": self.config.max_depth,
                    "max_pages": self.config.max_pages,
                    "pattern_samples": self.config.pattern_samples,
                },
                "timestamp": end_time.isoformat(),
            },
            "pages": self.results,
            "url_patterns": [
                {
                    "pattern": g.pattern,
                    "parameter_name": g.parameter_name,
                    "sample_urls": sorted(g.sample_urls),
                    "all_discovered_urls": sorted(g.all_urls),
                    "total_instances": len(g.all_urls),
                    "samples_crawled": g.crawled_count,
                }
                for g in sorted(self.url_patterns.values(), key=lambda g: g.pattern)
            ],
            "auth_blocked_urls": self.auth_blocked_list,
        }


# ── CLI ───────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="全站爬取：从入口 URL 自动发现并抓取所有可访问页面")
    parser.add_argument("entry_url", help="入口 URL（如 http://localhost:3000/）")
    parser.add_argument("--output", "-o", default="crawl_result.json", help="输出 JSON 路径（默认 crawl_result.json）")
    parser.add_argument("--screenshots-dir", default="./screenshots", help="截图保存目录（默认 ./screenshots）")
    parser.add_argument("--max-depth", type=int, default=3, help="最大爬取深度（默认 3）")
    parser.add_argument("--max-pages", type=int, default=50, help="最大爬取页数（默认 50）")
    parser.add_argument("--timeout", type=int, default=30000, help="页面加载超时毫秒（默认 30000）")
    parser.add_argument("--cdp-port", type=int, default=9222, help="CDP 端口（默认 9222）")
    parser.add_argument("--launch", action="store_true", help="强制使用 launch 模式")
    parser.add_argument("--wait-for", default=None, help="等待 CSS 选择器出现")
    parser.add_argument("--no-screenshot", action="store_true", help="跳过截图")
    parser.add_argument("--pattern-samples", type=int, default=2, help="参数化 URL 采样数量（默认 2）")
    parser.add_argument("--delay-ms", type=int, default=500, help="页面间延迟毫秒（默认 500）")
    parser.add_argument("--storage-state", default=None, help="Playwright Storage State 文件路径（认证复用）")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")
    return parser.parse_args()


def main():
    args = parse_args()

    config = CrawlConfig(
        entry_url=args.entry_url,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        timeout=args.timeout,
        cdp_port=args.cdp_port,
        force_launch=args.launch,
        wait_for=args.wait_for,
        no_screenshot=args.no_screenshot,
        screenshots_dir=args.screenshots_dir,
        pattern_samples=args.pattern_samples,
        delay_ms=args.delay_ms,
        verbose=args.verbose,
        storage_state=args.storage_state,
    )

    print(f"开始爬取: {config.entry_url}  (max_depth={config.max_depth}, max_pages={config.max_pages})", file=sys.stderr)
    result = asyncio.run(CrawlSite(config).run())

    # 写入 JSON
    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(output_json)

    # 输出 Markdown 统计报告
    report_path = _save_report(result, args.output)

    # stderr 简要摘要
    s = result["crawl_summary"]
    print(f"\n爬取完成！发现 {s['total_discovered_urls']} URL，抓取 {s['total_crawled']} 页，耗时 {s['crawl_duration_seconds']}s", file=sys.stderr)
    print(f"DOM 数据 : {os.path.abspath(args.output)}", file=sys.stderr)
    print(f"报告文件 : {report_path}", file=sys.stderr)


def _save_report(result: dict, output_path: str) -> str:
    """生成 Markdown 格式的全站抓取报告并保存为文件"""
    s = result["crawl_summary"]
    pages = result["pages"]
    patterns = result.get("url_patterns", [])
    blocked = result.get("auth_blocked_urls", [])

    public = [p for p in pages if not p.get("auth_blocked") and not p.get("error")]
    failed = [p for p in pages if p.get("error")]
    output_abs = os.path.abspath(output_path)
    screenshots_dir = os.path.abspath(public[0]["screenshot"]).rsplit(os.sep, 1)[0] if public and public[0].get("screenshot") else ""

    # 报告文件名带时间戳
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = os.path.dirname(output_abs)
    report_file = os.path.join(report_dir, f"crawl_report_{ts}.md")

    md = []

    # ── 标题与概览 ──
    md.append(f"# 全站爬取报告")
    md.append("")
    md.append(f"- **入口 URL** : {s['entry_url']}")
    md.append(f"- **爬取时间** : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append(f"- **爬取耗时** : {s['crawl_duration_seconds']}s")
    md.append(f"- **DOM 数据文件** : `{output_abs}`")
    if screenshots_dir:
        md.append(f"- **截图目录** : `{screenshots_dir}`")
    md.append("")
    md.append(f"| 指标 | 数量 |")
    md.append(f"|------|------|")
    md.append(f"| 发现 URL | {s['total_discovered_urls']} |")
    md.append(f"| 成功抓取（公开可访问） | {len(public)} |")
    md.append(f"| 需要认证 | {len(blocked)} |")
    md.append(f"| 参数化跳过 | {s['total_pattern_skipped']} |")
    if failed:
        md.append(f"| 抓取失败 | {len(failed)} |")

    # ── 已抓取页面 ──
    md.append("")
    md.append("## 已抓取页面")
    md.append("")
    md.append("| # | 页面标题 | URL | 元素数 | 截图文件 | 截图路径 |")
    md.append("|---|---------|-----|-------|---------|---------|")
    total_elements = 0
    for i, p in enumerate(public, 1):
        title = (p.get("title") or "").strip()
        url = p.get("url", "")
        path = p.get("path", "")
        elems = len(p.get("elements", []))
        total_elements += elems
        if p.get("screenshot"):
            shot_name = os.path.basename(p["screenshot"])
            shot_path = os.path.abspath(p["screenshot"])
            shot_cell = f"`{shot_name}`"
            path_cell = f"`{shot_path}`"
        else:
            shot_cell = "-"
            path_cell = "-"
        md.append(f"| {i} | {title} | [`{path}`]({url}) | {elems} | {shot_cell} | {path_cell} |")
    md.append(f"| | **合计** | | **{total_elements}** | | |")

    # ── DOM 数据说明 ──
    md.append("")
    md.append("## DOM 数据")
    md.append("")
    md.append(f"- **文件位置** : `{output_abs}`")
    md.append("- **数据格式** : JSON")
    md.append("  - `pages[]` 数组，每页包含 `elements`（交互元素）、`text_structure`（文本结构）、`html`（完整 HTML）")
    md.append("  - 每个元素包含 `tag`、`type`、`id`、`name`、`data_testid`、`aria_label`、`xpath`、`css`、`interaction_hint` 等字段")
    md.append("- **下游使用** : 传入 `build_pages_yaml.py` 或由 AI 分析生成 `pages.yaml`")

    # ── 需认证页面 ──
    if blocked:
        md.append("")
        md.append(f"## 需要认证的页面（{len(blocked)} 个）")
        md.append("")
        md.append("| # | URL 路径 | 重定向到 |")
        md.append("|---|---------|---------|")
        for i, a in enumerate(blocked, 1):
            path = urllib.parse.urlparse(a["url"]).path
            redirect = urllib.parse.urlparse(a.get("redirect_to", "")).path
            md.append(f"| {i} | `{path}` | `{redirect}` |")

    # ── 参数化 URL 模式 ──
    if patterns:
        md.append("")
        md.append("## 参数化 URL 模式")
        md.append("")
        md.append("| 路由模式 | 实例总数 | 已采样 | 采样 URL |")
        md.append("|---------|---------|--------|---------|")
        for pt in patterns:
            sample_paths = ", ".join(f"`{urllib.parse.urlparse(u).path}`" for u in pt["sample_urls"])
            md.append(f"| `{pt['pattern']}` | {pt['total_instances']} | {pt['samples_crawled']} | {sample_paths} |")

    # ── Vue Router 路由表 ──
    home_page = next((p for p in public if p.get("path") == "/"), None)
    if home_page and home_page.get("vue_routes"):
        routes = home_page["vue_routes"]
        md.append("")
        md.append(f"## Vue Router 路由表（{len(routes)} 条）")
        md.append("")
        md.append("| 路由路径 | 路由名称 | 参数化 |")
        md.append("|---------|---------|--------|")
        for r in routes:
            path = r.get("path", "")
            if path == "/:pathMatch(.*)*" or "*" in path:
                continue
            name = r.get("name", "")
            has_params = "是" if r.get("has_params") else ""
            md.append(f"| `{path}` | `{name}` | {has_params} |")

    # 写入文件
    content = "\n".join(md) + "\n"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(content)

    # 同时输出到 stderr
    print(content, file=sys.stderr)

    return report_file


if __name__ == "__main__":
    main()
