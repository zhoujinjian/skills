#!/usr/bin/env python3
"""
fetch_dom.py — 使用 Playwright 抓取页面渲染后的完整 DOM、元素信息与截图

支持两种连接模式（自动探测，优先使用 CDP 连接）：

  模式 A: CDP 连接模式
    连接已运行的 Chrome CDP 实例（localhost:9222）。

  模式 B: Launch 模式（默认）
    直接由 Playwright 启动无头浏览器。沙箱外环境自动使用。

  模式 C: Playwright MCP 模式（--mcp）
    通过 webapp-testing 的 Playwright 集成，截图 + DOM + 交互发现。

用法：
    python fetch_dom.py <url> [--output <path>] [--timeout <ms>] [--cdp-port <port>]
                            [--wait-for <selector>] [--launch] [--screenshot <path>]
                            [--full-page-screenshot] [--extract-text-structure]

输出（JSON）：
{
  "url": "...",
  "title": "...",
  "html": "<html>...</html>",
  "elements": [ ... ],
  "text_structure": [ ... ],
  "screenshot": "<base64 or path>",
  "fetch_mode": "cdp_connect" | "launch",
  "auth_mode": "cdp_authenticated" | "storage_state" | null,
  "error": null
}
"""

import sys
import json
import argparse
import asyncio
import base64
import urllib.request
from datetime import datetime, timezone


def parse_args():
    parser = argparse.ArgumentParser(description="抓取页面 DOM 结构")
    parser.add_argument("url", help="目标页面 URL")
    parser.add_argument("--output", "-o", default=None, help="输出文件路径（默认 stdout）")
    parser.add_argument("--timeout", type=int, default=30000, help="页面加载超时（毫秒，默认 30000）")
    parser.add_argument("--cdp-port", type=int, default=9222, help="Chrome 远程调试端口（默认 9222）")
    parser.add_argument("--wait-for", default=None, help="等待指定 CSS 选择器出现后再抓取")
    parser.add_argument("--launch", action="store_true", help="强制使用 launch 模式")
    parser.add_argument("--screenshot", default=None, help="截图保存路径")
    parser.add_argument("--full-page-screenshot", action="store_true", help="全页截图（而非视口截图）")
    parser.add_argument("--extract-text-structure", action="store_true", help="提取页面文本结构（标题、段落等）")
    parser.add_argument("--storage-state", default=None, help="Playwright Storage State 文件路径（认证复用）")
    return parser.parse_args()


def check_cdp_available(port: int) -> bool:
    try:
        req = urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=2)
        return req.status == 200
    except Exception:
        return False


# Enhanced DOM extraction: captures more interactive elements
DOM_EXTRACT_SCRIPT = """
() => {
    const INTERACTIVE_TAGS = ['input', 'button', 'select', 'textarea', 'a', 'form', 'label', 'option', 'summary', 'details'];
    const INTERACTIVE_ROLES = [
        'button', 'link', 'menuitem', 'tab', 'tabpanel', 'checkbox', 'radio',
        'switch', 'slider', 'textbox', 'searchbox', 'combobox', 'listbox',
        'option', 'dialog', 'alertdialog', 'alert', 'treeitem', 'gridcell',
        'menuitemradio', 'menuitemcheckbox', 'spinbutton', 'scrollbar',
        'navigation', 'banner', 'main', 'contentinfo'
    ];
    const CLICKABLE_INDICATORS = [
        'cursor: pointer', 'pointer', 'hand'
    ];

    function getXPath(el) {
        if (!el || el.nodeType !== 1) return '';
        const parts = [];
        let current = el;
        while (current && current.nodeType === 1) {
            let idx = 1;
            let sibling = current.previousElementSibling;
            while (sibling) {
                if (sibling.tagName === current.tagName) idx++;
                sibling = sibling.previousElementSibling;
            }
            const tag = current.tagName.toLowerCase();
            parts.unshift(idx > 1 ? `${tag}[${idx}]` : tag);
            current = current.parentElement;
            if (current === document.documentElement) { parts.unshift('html'); break; }
        }
        return '//' + parts.join('/');
    }

    function getCssPath(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        const parts = [];
        let current = el;
        while (current && current !== document.body) {
            let selector = current.tagName.toLowerCase();
            if (current.id) { selector = '#' + CSS.escape(current.id); parts.unshift(selector); break; }
            const classes = Array.from(current.classList).slice(0, 2).map(c => '.' + CSS.escape(c)).join('');
            if (classes) selector += classes;
            parts.unshift(selector);
            current = current.parentElement;
        }
        return parts.join(' > ');
    }

    // Tags that should NOT be auto-detected as clickable just from cursor style
    const GENERIC_TAGS = new Set(['div','span','p','section','article','main','header','footer','nav','ul','ol','li','h1','h2','h3','h4','h5','h6','aside','figure']);

    function isClickable(el) {
        const tag = el.tagName.toLowerCase();
        // Vue/React event handlers
        if (el.__vue__ || el.__vueParentComponent) return true;
        if (el._reactEvents || Object.keys(el).some(k => k.startsWith('__react'))) return true;
        // cursor:pointer only for non-generic tags
        if (!GENERIC_TAGS.has(tag)) {
            const style = window.getComputedStyle(el);
            const cursor = style.cursor || '';
            if (CLICKABLE_INDICATORS.some(ind => cursor.includes(ind))) return true;
        }
        // tabindex for non-generic tags
        if (el.tabIndex >= 0 && !GENERIC_TAGS.has(tag)) return true;
        return false;
    }

    function getInteractionHint(el) {
        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || '';
        const type = el.getAttribute('type') || '';

        if (tag === 'a' || role === 'link') return 'navigate';
        if (tag === 'input' && (type === 'submit' || type === 'button')) return 'submit';
        if (tag === 'button' || role === 'button') {
            const text = (el.textContent || '').trim().toLowerCase();
            if (text.includes('提交') || text.includes('submit') || text.includes('保存') || text.includes('save')) return 'submit';
            if (text.includes('删除') || text.includes('delete') || text.includes('移除') || text.includes('remove')) return 'delete';
            if (text.includes('取消') || text.includes('cancel') || text.includes('关闭') || text.includes('close')) return 'cancel';
            if (text.includes('搜索') || text.includes('search') || text.includes('查询') || text.includes('筛选') || text.includes('filter')) return 'search';
            if (text.includes('添加') || text.includes('add') || text.includes('新增') || text.includes('create') || text.includes('新建')) return 'create';
            if (text.includes('编辑') || text.includes('edit') || text.includes('修改') || text.includes('modify')) return 'edit';
            if (text.includes('下载') || text.includes('download') || text.includes('导出') || text.includes('export')) return 'download';
            return 'click';
        }
        if (tag === 'input' || tag === 'textarea' || role === 'textbox') return 'input';
        if (tag === 'select' || role === 'combobox' || role === 'listbox') return 'select';
        if (role === 'tab') return 'tab-switch';
        if (role === 'checkbox' || type === 'checkbox') return 'toggle';
        if (role === 'radio' || type === 'radio') return 'select';
        if (role === 'switch') return 'toggle';
        if (role === 'dialog' || role === 'alertdialog') return 'modal';
        if (tag === 'form') return 'form-submit';
        return 'click';
    }

    const seen = new Set();
    const results = [];

    document.querySelectorAll('*').forEach(el => {
        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role') || '';

        const isInteractive =
            INTERACTIVE_TAGS.includes(tag) ||
            INTERACTIVE_ROLES.includes(role) ||
            el.hasAttribute('onclick') ||
            el.hasAttribute('data-click') ||
            el.hasAttribute('data-action') ||
            isClickable(el);

        if (!isInteractive) return;

        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        const visible = rect.width > 0 && rect.height > 0
            && style.visibility !== 'hidden' && style.display !== 'none' && style.opacity !== '0';

        const dataTestid = el.getAttribute('data-testid') || el.getAttribute('data-test-id')
            || el.getAttribute('data-qa') || el.getAttribute('data-cy') || '';
        const key = tag + '|' + (el.id || '') + '|' + (el.getAttribute('name') || '') + '|' + dataTestid;
        if (seen.has(key) && key !== 'button|||') return;
        seen.add(key);

        results.push({
            tag,
            type: el.getAttribute('type') || '',
            id: el.id || '',
            name: el.getAttribute('name') || '',
            placeholder: el.getAttribute('placeholder') || '',
            data_testid: dataTestid,
            aria_label: el.getAttribute('aria-label') || '',
            aria_labelledby: el.getAttribute('aria-labelledby') || '',
            role,
            class: el.className || '',
            text_content: (el.textContent || '').trim().substring(0, 120),
            href: el.getAttribute('href') || '',
            value: el.value || '',
            disabled: el.disabled || false,
            required: el.required || false,
            is_visible: visible,
            is_interactive: true,
            interaction_hint: getInteractionHint(el),
            bounding_box: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
            xpath: getXPath(el),
            css: getCssPath(el),
        });
    });

    return results;
}
"""

# Text structure extraction for semantic understanding
TEXT_STRUCTURE_SCRIPT = """
() => {
    const SEMANTIC_TAGS = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'th', 'td', 'label', 'legend', 'figcaption', 'caption', 'blockquote'];
    const results = [];

    SEMANTIC_TAGS.forEach(tag => {
        document.querySelectorAll(tag).forEach(el => {
            const text = (el.textContent || '').trim();
            if (!text || text.length === 0) return;
            const rect = el.getBoundingClientRect();
            const visible = rect.width > 0 && rect.height > 0;
            if (!visible) return;
            results.push({
                tag,
                text: text.substring(0, 200),
                id: el.id || '',
                class: (el.className || '').substring(0, 100),
            });
        });
    });

    // Also extract nav/link structure
    const navs = document.querySelectorAll('nav, [role="navigation"]');
    navs.forEach(nav => {
        const links = nav.querySelectorAll('a');
        links.forEach(a => {
            results.push({
                tag: 'nav-link',
                text: (a.textContent || '').trim().substring(0, 100),
                href: a.getAttribute('href') || '',
                id: a.id || '',
                class: (a.className || '').substring(0, 100),
            });
        });
    });

    return results;
}
"""


async def fetch_page(
    url: str,
    timeout: int,
    wait_for: str | None,
    cdp_port: int,
    force_launch: bool,
    screenshot_path: str | None,
    full_page_screenshot: bool,
    extract_text_structure: bool,
    storage_state: str | None = None,
) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "error": "playwright 未安装。请运行：pip install playwright && playwright install chromium",
            "fetch_mode": "unavailable",
            "auth_mode": None,
            "url": url,
            "title": "",
            "html": "",
            "elements": [],
            "text_structure": [],
            "screenshot": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    use_cdp = (not force_launch) and check_cdp_available(cdp_port)
    fetch_mode = "cdp_connect" if use_cdp else "launch"

    if use_cdp:
        auth_mode = "cdp_authenticated"
    elif storage_state:
        auth_mode = "storage_state"
    else:
        auth_mode = None

    async with async_playwright() as p:
        try:
            if use_cdp:
                print(f"CDP 模式：连接 localhost:{cdp_port}", file=sys.stderr)
                browser = await p.chromium.connect_over_cdp(f"http://localhost:{cdp_port}")
                context = browser.contexts[0] if browser.contexts else await browser.new_context(
                    viewport={"width": 1440, "height": 900}
                )
                page = await context.new_page()
            else:
                print("Launch 模式：直接启动无头浏览器", file=sys.stderr)
                browser = await p.chromium.launch(headless=True)
                context_kwargs = {
                    "viewport": {"width": 1440, "height": 900},
                    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                }
                if storage_state:
                    print(f"注入 Storage State: {storage_state}", file=sys.stderr)
                    context_kwargs["storage_state"] = storage_state
                context = await browser.new_context(**context_kwargs)
                page = await context.new_page()

            await page.goto(url, timeout=timeout, wait_until="domcontentloaded")

            if wait_for:
                await page.wait_for_selector(wait_for, timeout=timeout)
                print(f"等待选择器 '{wait_for}' 出现成功", file=sys.stderr)
            else:
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass

            title = await page.title()
            html = await page.content()
            elements = await page.evaluate(DOM_EXTRACT_SCRIPT)

            # Optional: extract text structure
            text_structure = []
            if extract_text_structure:
                text_structure = await page.evaluate(TEXT_STRUCTURE_SCRIPT)

            # Optional: screenshot
            screenshot_data = None
            if screenshot_path:
                await page.screenshot(
                    path=screenshot_path,
                    full_page=full_page_screenshot,
                )
                screenshot_data = screenshot_path
                print(f"截图已保存: {screenshot_path}", file=sys.stderr)

            print(f"抓取成功：{url}  |  title={title!r}  |  elements={len(elements)}", file=sys.stderr)

            result = {
                "url": url,
                "title": title,
                "html": html,
                "elements": elements,
                "text_structure": text_structure,
                "screenshot": screenshot_data,
                "fetch_mode": fetch_mode,
                "auth_mode": auth_mode,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": None,
            }

            if use_cdp:
                await page.close()
            else:
                await browser.close()

            return result

        except Exception as e:
            err_msg = str(e)
            if "MachPortRendezvousServer" in err_msg or "Permission denied (1100)" in err_msg:
                err_msg = (
                    "macOS App Sandbox 阻止了浏览器子进程 MachPort 通信（Launch 模式不可用）。\n"
                    "请改用 CDP 连接模式：\n"
                    "  1. 打开 Terminal，执行：\n"
                    '     /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\\n'
                    "       --headless=new --remote-debugging-port=9222 \\\n"
                    "       --no-sandbox --user-data-dir=/tmp/chrome_cdp about:blank &\n"
                    "  2. 等待 2 秒后重新运行本脚本"
                )
            return {
                "url": url,
                "title": "",
                "html": "",
                "elements": [],
                "text_structure": [],
                "screenshot": None,
                "fetch_mode": fetch_mode + "_failed",
                "auth_mode": auth_mode,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": err_msg,
            }


def main():
    args = parse_args()

    cdp_available = check_cdp_available(args.cdp_port)
    if cdp_available:
        print(f"检测到 CDP 服务（localhost:{args.cdp_port}），使用 CDP 连接模式", file=sys.stderr)
    else:
        print(f"未检测到 CDP 服务，使用 Launch 模式", file=sys.stderr)

    result = asyncio.run(fetch_page(
        url=args.url,
        timeout=args.timeout,
        wait_for=args.wait_for,
        cdp_port=args.cdp_port,
        force_launch=args.launch,
        screenshot_path=args.screenshot,
        full_page_screenshot=args.full_page_screenshot,
        extract_text_structure=args.extract_text_structure,
        storage_state=args.storage_state,
    ))

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"DOM 数据已写入: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
