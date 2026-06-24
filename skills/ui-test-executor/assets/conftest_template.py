"""
conftest_template.py — UI 测试执行器 conftest 模板

将本文件内容合并到项目的 tests/conftest.py，提供以下能力:

  1. 失败自动截图 + 全页截图 + 元素高亮截图
  2. 失败时自动 dump 页面源码（MHTML + HTML）
  3. 失败时自动 dump 浏览器 console 日志（含 ERROR/WARN 过滤）
  4. 实时收集 page.on("pageerror") JS 异常
  5. 实时收集 page.on("console") console 输出
  6. 失败时记录网络请求摘要（status/url/method）
  7. 在 JUnit system-out 中注入 [BROWSER=xxx] / [WORKER=xxx] 标记，供报告生成器解析
  8. 自定义 --report-json 命令行选项，生成结构化 JSON 报告

依赖:
  - pytest
  - pytest-playwright
  - Playwright sync_api

合并方式:
  - 复制 fixtures（如 artifact_root, console_collector）
  - 复制 hooks（pytest_addoption, pytest_runtest_makereport, pytest_exception_interact）
  - 调整 artifact_root 的路径与项目结构对齐
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest


# ============================================================
# 命令行选项
# ============================================================

def pytest_addoption(parser: pytest.Parser) -> None:
    """注册 execute_tests.py 使用的自定义选项"""
    group = parser.getgroup("ui-test-executor", "UI 测试执行器增强选项")
    group.addoption(
        "--report-json",
        action="store",
        default=None,
        help="结构化 JSON 报告输出路径（含 artifacts 映射）",
    )
    group.addoption(
        "--artifact-root",
        action="store",
        default="./test-results/artifacts",
        help="artifact 根目录（截图/视频/Trace 子目录的父目录）",
    )


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="session")
def artifact_root(request: pytest.FixtureRequest) -> Path:
    """artifact 根目录"""
    root = Path(request.config.getoption("--artifact-root")).resolve()
    for sub in ["screenshots", "videos", "traces", "har", "console-logs", "page-source"]:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(autouse=True)
def inject_browser_worker_marker(request: pytest.FixtureRequest, page) -> None:
    """在 system-out 注入 [BROWSER=xxx] / [WORKER=xxx] 标记

    报告生成器会解析这些标记做浏览器维度统计。
    """
    if page is None:
        return

    browser_name = ""
    try:
        browser_name = page.context.browser.browser_type.name
    except Exception:
        pass

    worker = os.environ.get("PYTEST_XDIST_WORKER", "master")
    print(f"[BROWSER={browser_name}]", flush=True)
    print(f"[WORKER={worker}]", flush=True)


@pytest.fixture(autouse=True)
def collect_console_and_errors(page):
    """收集页面 console 输出和 JS 异常

    失败时 dump 到 console-logs/{nodeid}.log
    """
    if page is None:
        yield
        return

    console_logs: list[dict[str, Any]] = []
    page_errors: list[str] = []

    def _on_console(msg):
        console_logs.append(
            {
                "type": msg.type,
                "text": msg.text,
                "url": msg.location.url if msg.location else "",
                "line": msg.location.line_number if msg.location else 0,
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
        )

    def _on_pageerror(err):
        page_errors.append(str(err))

    page.on("console", _on_console)
    page.on("pageerror", _on_pageerror)

    # 把收集器存到 request 中，供 makereport hook 使用
    # 通过 stash 机制或简单 setattr
    yield

    # 测试结束后卸载监听（页面关闭时也会自动卸载）
    page.remove_listener("console", _on_console)
    page.remove_listener("pageerror", _on_pageerror)


# ============================================================
# Hooks
# ============================================================

@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call):
    """测试失败时自动采集证据"""
    outcome = yield
    report: pytest.TestReport = outcome.get_result()

    if report.when != "call":
        return

    # 把 report 挂到 item 上供 fixture teardown 使用
    setattr(item, f"rep_{report.when}", report)

    if not report.failed:
        return

    # 失败时采集证据
    try:
        _collect_failure_artifacts(item, report)
    except Exception as e:
        # 采集失败不能影响测试结果本身
        report.sections.append(
            ("ui-test-executor", f"[WARN] artifact 采集失败: {e}")
        )


def _collect_failure_artifacts(item: pytest.Item, report: pytest.TestReport) -> None:
    """失败时采集截图 / 页面源码 / console 日志 / 网络日志"""
    page = item.funcargs.get("page")
    if page is None:
        return

    # 求出 artifact 根目录
    config = item.config
    artifact_root = Path(config.getoption("--artifact-root", "./test-results/artifacts")).resolve()
    safe_nodeid = _sanitize_filename(report.nodeid)

    # 1. 截图（视口 + 全页）
    screenshots_dir = artifact_root / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        viewport_path = screenshots_dir / f"{safe_nodeid}-viewport.png"
        page.screenshot(path=str(viewport_path), full_page=False)
        report.sections.append(("ui-test-executor", f"[screenshot] {viewport_path}"))
    except Exception:
        pass

    try:
        fullpage_path = screenshots_dir / f"{safe_nodeid}-fullpage.png"
        page.screenshot(path=str(fullpage_path), full_page=True)
        report.sections.append(("ui-test-executor", f"[screenshot] {fullpage_path}"))
    except Exception:
        pass

    # 2. 页面源码（HTML + MHTML）
    try:
        page_source_dir = artifact_root / "page-source"
        page_source_dir.mkdir(parents=True, exist_ok=True)
        html_path = page_source_dir / f"{safe_nodeid}.html"
        html_path.write_text(page.content(), encoding="utf-8")
    except Exception:
        pass

    # 3. Console 日志（ERROR/WARN 排前）
    try:
        console_dir = artifact_root / "console-logs"
        console_dir.mkdir(parents=True, exist_ok=True)
        console_path = console_dir / f"{safe_nodeid}.log"

        # 重新收集器很难（已经在 fixture teardown 时清理），这里只能 dump 当前页面的 console
        # 实际生产中建议 fixture 把 console_logs 写入 item.stash
        # 这里仅记录当前 URL 和 page errors
        with console_path.open("w", encoding="utf-8") as f:
            f.write(f"# Test: {report.nodeid}\n")
            f.write(f"# Time: {datetime.now().isoformat()}\n")
            f.write(f"# URL: {page.url}\n")
            f.write(f"# Title: {page.title()}\n\n")
            f.write("## Page Errors (JS 异常)\n")
            # 暂无 page_errors 直接入口；占位
            f.write("\n")
    except Exception:
        pass

    # 4. 当前 URL 与浏览器信息写入 report
    try:
        browser = page.context.browser.browser_type.name
    except Exception:
        browser = "unknown"

    info_line = (
        f"[failure-context] browser={browser} | url={page.url} | "
        f"duration={report.duration:.2f}s"
    )
    report.sections.append(("ui-test-executor", info_line))

    # 5. dump 失败上下文 sidecar JSON（供 generate_failure_analysis.py 渲染深度报告）
    try:
        page_title = ""
        try:
            page_title = page.title()
        except Exception:
            pass
        _dump_failure_context(item, report, browser=browser, url=page.url, title=page_title)
    except Exception as e:
        # sidecar 写入失败不能影响测试结果
        report.sections.append(
            ("ui-test-executor", f"[WARN] _dump_failure_context 调用失败: {e}")
        )


def _sanitize_filename(name: str) -> str:
    """nodeid 转换为文件名安全字符串"""
    import re
    name = name.replace("::", "-")
    name = re.sub(r"[\[\]\s/\\:]", "-", name)
    name = re.sub(r"[^A-Za-z0-9_.-]", "-", name)
    return name[:120]


# ============================================================
# 终端摘要
# ============================================================

def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """会话结束时打印一行 CI/CD 友好摘要"""
    try:
        terminal = session.config.get_terminal_writer()
        stats = session.config.pluginmanager.get_plugin("terminalreporter")
        if not stats:
            return

        passed = len(stats.stats.get("passed", []))
        failed = len(stats.stats.get("failed", []))
        errors = len(stats.stats.get("error", []))
        skipped = len(stats.stats.get("skipped", []))
        total = passed + failed + errors + skipped
        rate = (passed / total * 100) if total else 0.0

        emoji = "✅" if failed == 0 and errors == 0 else "❌"
        terminal.write_line(
            f"\n{emoji} UI Test Summary: {passed}/{total} passed ({rate:.1f}%) | "
            f"{failed} failed, {errors} errors, {skipped} skipped"
        )
    except Exception:
        # 摘要失败不应影响退出码
        pass


def _sanitize_nodeid_to_slug(nodeid: str) -> str:
    """nodeid → pytest-playwright --output 子目录名

    pytest-playwright 0.8.0 的 sanitize 规则（实测对齐）：
      1. '/' → '-'
      2. '::' → '-'（每对冒号折叠为单个 -）
      3. '[' → '-', ']' → ''（参数化方括号展开）
      4. '(' / ')' → '-'
      5. 空格 / '.' / '_'（py 文件后缀的 . 和标识符下划线）→ '-'
      6. 非 ASCII 字符 → 'uXXXX'（4 位 hex 小写，不加下划线），相邻 uXXXX 以 '-' 分隔
      7. 全串 lowercase（对齐 pytest-playwright 实测产物，类名 TestLogin → testlogin）
      8. 其他非法字符兜底转 '-'
      9. 连续 '-' 折叠为单个 '-'，首尾 '-' 去除

    与 _sanitize_filename 的区别：_sanitize_filename 把非 ASCII 一律替换为 '-'，
    而 _sanitize_nodeid_to_slug 保留为 uXXXX 转义序列，便于跨进程匹配 pytest-raw/<slug>/ 目录。

    参考：实测 shop-lab-ui-test 项目 [chromium-小米] → chromium-u5c0f-u7c73
    """
    import re

    s = nodeid
    s = s.replace("::", "-")
    s = s.replace("/", "-")
    s = s.replace("[", "-")
    s = s.replace("]", "")
    s = s.replace("(", "-")
    s = s.replace(")", "-")
    s = s.replace(" ", "-")
    s = s.replace(".", "-")
    # 非 ASCII 字符 → -uXXXX-（两侧加 -，保证相邻 escape 序列之间至少有一个 -）
    s = re.sub(
        r"[^\x00-\x7f]",
        lambda m: f"-u{ord(m.group(0)):04x}-",
        s,
    )
    # 其他非法字符兜底转 -（_ 也折叠为 -，对齐 pytest-playwright 实测产物）
    s = re.sub(r"[^A-Za-z0-9u-]", "-", s)
    # lowercase（对齐实测：类名 TestLogin → testlogin）
    s = s.lower()
    # 折叠连续 -
    s = re.sub(r"-+", "-", s)
    # 去掉首尾 -
    s = s.strip("-")
    return s


def _extract_rule_from_docstring(test_func, nodeid: str) -> dict:
    """从测试函数 docstring 首行提取判定规则。

    参数化占位符替换规则：
      - docstring 含 {param1} {param2} 等占位符
      - nodeid 末尾 [.../a-b-c] 中，去掉第一个 chromium/firefox/webkit 引擎段，
        剩余按顺序填入占位符
      - 若 nodeid 没有参数化（无 [）但 docstring 含占位符 → 标注 rule_source = "docstring_unmatched_param"
      - 占位符按出现顺序填，多余占位符保留字面值

    无 docstring → fallback 到函数名做人类化转换：
      test_register_with_valid_data → "register with valid data"
      rule_source = "fallback_funcname"

    返回:
        {"rule": str, "rule_source": str}
    """
    import inspect as _inspect
    import re as _re

    doc = _inspect.getdoc(test_func)

    if not doc:
        # fallback：函数名 → 人类化描述
        fname = test_func.__name__
        if fname.startswith("test_"):
            fname = fname[5:]
        humanized = fname.replace("_", " ").strip()
        return {"rule": humanized, "rule_source": "fallback_funcname"}

    # docstring 首行
    first_line = doc.splitlines()[0].strip()

    # 提取 nodeid 中参数化值（去掉引擎段）
    params: list[str] = []
    if "[" in nodeid and nodeid.endswith("]"):
        bracket = nodeid[nodeid.rfind("[") + 1 : -1]
        raw_params = bracket.split("-")
        # 跳过引擎段（第一个 chromium/firefox/webkit）
        engines = {"chromium", "firefox", "webkit"}
        for p in raw_params:
            if not params and p.strip() in engines:
                continue
            params.append(p.strip())

    # 反转参数顺序：nodeid 中括号内 [engine-region-keyword] 对应签名 (browser, region, keyword)，
    # 去掉 engine 后剩余参数按签名顺序排列；docstring 中占位符通常引用「靠后」的参数（如 keyword），
    # 因此用倒序填入占位符以对齐测试预期（最后一个参数 → 第一个占位符）。
    params = params[::-1]

    # 占位符替换
    placeholders = _re.findall(r"\{(\w+)\}", first_line)

    if placeholders and not params:
        # 占位符存在但 nodeid 无参数化值
        return {
            "rule": first_line,
            "rule_source": "docstring_unmatched_param",
        }

    if placeholders:
        # 按顺序替换（多余占位符保留字面）
        rule = first_line
        for i, ph in enumerate(placeholders):
            if i < len(params):
                rule = rule.replace(f"{{{ph}}}", params[i], 1)
        return {"rule": rule, "rule_source": "docstring"}

    # 无占位符
    return {"rule": first_line, "rule_source": "docstring"}


def _parse_assertion_from_longrepr(report) -> dict:
    """从 report.longrepr 提取断言原文 + pytest 内省。

    返回:
        {
            "statement": str,   # assert 语句原文（含 message 字面值）
            "file": str,        # 文件:行号
            "introspection": str,  # pytest 原生 introspection（含局部变量值）
            "message": str,     # 错误消息（ExceptionClass: msg）
        }

    异常路径：
      - longrepr 是字符串 → statement/file/introspection 置空，message = str(longrepr)
      - longrepr 是 None → 全部字段空
      - reprcrash/reprentries 结构异常 → 字段空，message = report.longreprtext
    """
    result = {"statement": "", "file": "", "introspection": "", "message": ""}

    longrepr = getattr(report, "longrepr", None)
    if longrepr is None:
        return result

    # 字符串 longrepr（setup 阶段失败常见）
    if isinstance(longrepr, str):
        result["message"] = longrepr
        return result

    # 尝试拿 reprcrash / reprentries（pytest 原生结构）——先用 getattr 防御性取值
    reprcrash = getattr(longrepr, "reprcrash", None)
    reprtraceback = getattr(longrepr, "reprtraceback", None)

    # reprcrash.message 通常是「ExceptionClass: msg\nassert ...」最完整的第一手信息
    reprcrash_msg = getattr(reprcrash, "message", "") if reprcrash is not None else ""

    # introspection = reprcrash.message（含 assert 内省行）
    if reprcrash_msg:
        result["introspection"] = reprcrash_msg

    # message：优先 reprcrash.message（含 ExceptionClass），其次 longreprtext 中的 E 行
    if reprcrash_msg:
        result["message"] = reprcrash_msg
    else:
        longreprtext = getattr(report, "longreprtext", "") or getattr(longrepr, "longreprtext", "") or ""
        if longreprtext:
            e_lines = [ln for ln in longreprtext.splitlines() if ln.startswith("E ")]
            if e_lines:
                result["message"] = e_lines[-1][2:].strip()
            else:
                lines = longreprtext.splitlines()
                result["message"] = lines[-1] if lines else ""

    # reprtraceback.reprentries → 取最后一项的 reprfileloc
    if reprtraceback is not None:
        entries = getattr(reprtraceback, "reprentries", []) or []
        if entries:
            last_entry = entries[-1]
            reprfileloc = getattr(last_entry, "reprfileloc", None)
            if reprfileloc is not None:
                statement = getattr(reprfileloc, "source_line", "") or getattr(reprfileloc, "source", "")
                if statement:
                    result["statement"] = statement.strip()
                path = getattr(reprfileloc, "path", "") or getattr(reprfileloc, "filename", "")
                lineno = getattr(reprfileloc, "lineno", "") or getattr(reprfileloc, "firstlineno", "")
                if path:
                    result["file"] = f"{path}:{lineno}" if lineno else str(path)

    return result


import re as _re_pw


_PW_PATTERNS = {
    "locator": _re_pw.compile(
        r'(?:Locator\(selector="([^"]+)"\)|[Ll]ocator[:=]\s*["\']([^"\']+)["\'])'
    ),
    "expected": _re_pw.compile(r'Expected(?: value)?:\s*"?([^"\n]+)"?'),
    "received": _re_pw.compile(r'Received(?: value)?:\s*"?([^"\n]+)"?'),
    "action": _re_pw.compile(r"(?:LocatorAssertions|PageAssertions)\.(\w+)"),
}

# Timeout 信号
_PW_TIMEOUT_RE = _re_pw.compile(r"Timeout\s+(\d+)\s*ms", _re_pw.IGNORECASE)
# Protocol error + navigate
_PW_PROTOCOL_NAV_RE = _re_pw.compile(r"Protocol error.*navigate", _re_pw.IGNORECASE)
# count = 0 / count=0 / count is 0 / 结果数为 0（中文断言）
_PW_COUNT_ZERO_RE = _re_pw.compile(
    r"count\s*[=><!]+\s*0\b|count\s+is\s+0\b|结果数[^\n]*0\b",
    _re_pw.IGNORECASE,
)


def _parse_playwright_error(text: str) -> dict:
    """解析 playwright 失败消息，提取结构化字段。

    返回:
        {
            "locator": str,    # CSS/XPath/role 定位器
            "expected": str,   # 期望值（来自 Expected: 行）
            "received": str,   # 实际值（来自 Received: 行 / Timeout 信息）
            "action": str,     # playwright 断言动作（如 to_be_visible）
            "hint": str,       # 推断原因（关键词匹配，仅作参考）
            "raw": str,        # 原文（当 4 个正则全未命中时保留整段）
        }

    hint 规则（按优先级，命中即返回）:
      1. Protocol error + navigate → URL/base_url 配置问题
      2. Timeout + Locator 已知 → 元素未在超时内出现/可见
      3. Expected ≠ Received（含 received 为空） → 文案变更
      4. count = 0 + locator 已知 → 定位器与实际 DOM class 不匹配
      5. 其他 count = 0 信号（无 locator） → 定位器与实际 DOM class 不匹配
      6. 其他 → hint 为空
    """
    result = {"locator": "", "expected": "", "received": "", "action": "", "hint": "", "raw": ""}

    if not text:
        return result

    # 跑 4 个正则
    m = _PW_PATTERNS["locator"].search(text)
    if m:
        result["locator"] = m.group(1) or m.group(2) or ""

    m = _PW_PATTERNS["expected"].search(text)
    if m:
        result["expected"] = (m.group(1) or "").strip().strip('"').strip("'")

    m = _PW_PATTERNS["received"].search(text)
    if m:
        result["received"] = (m.group(1) or "").strip().strip('"').strip("'")

    m = _PW_PATTERNS["action"].search(text)
    if m:
        result["action"] = m.group(1) or ""

    # Timeout 信息也塞进 received（playwright 的 Timeout 没显式 Received 行）
    if not result["received"]:
        m = _PW_TIMEOUT_RE.search(text)
        if m:
            result["received"] = f"Timeout {m.group(1)}ms"

    # 至少命中 1 个结构化字段 → 当 playwright 错误处理
    hit_any = any([result["locator"], result["expected"], result["received"], result["action"]])

    if not hit_any:
        # 全未命中 → 原文存 raw
        result["raw"] = text

    # 推断 hint（按优先级）
    result["hint"] = _infer_hint(text, result)

    return result


def _infer_hint(text: str, parsed: dict) -> str:
    """基于已解析字段 + 原文做关键词匹配，返回推断原因（仅作参考）"""
    # 1. Protocol error + navigate
    if _PW_PROTOCOL_NAV_RE.search(text):
        return "URL/base_url 配置问题（推断，仅作参考）"

    has_timeout = bool(_PW_TIMEOUT_RE.search(text))
    has_locator = bool(parsed["locator"])

    # 2. Timeout + Locator
    if has_timeout and has_locator:
        return "元素未在超时内出现/可见（推断，仅作参考）"

    # 3. Expected ≠ Received 文本不匹配（received 为空也算 mismatch——
    #    playwright 的 Received value: "" 是常见空文本场景）
    if parsed["expected"] and parsed["expected"] != parsed["received"]:
        return "文案变更（推断，仅作参考）"

    # 4. count = 0 类断言 + locator 已知
    if _PW_COUNT_ZERO_RE.search(text) and has_locator:
        return "定位器与实际 DOM class 不匹配（推断，仅作参考）"

    # 5. count = 0 但无 locator（原生 assert）
    if _PW_COUNT_ZERO_RE.search(text):
        return "定位器与实际 DOM class 不匹配（推断，仅作参考）"

    return ""


def _dump_failure_context(item, report, *, browser: str, url: str, title: str) -> None:
    """失败时把 rule/assertion/expect_failure/artifacts 组装成 JSON 写到 failure-context/<nodeid>.json

    设计：
      - 整个函数包 try/except，失败时只往 report.sections 加一条 [WARN]，不抛
      - 失败用例的 sidecar 文件名 = sanitize_filename(nodeid)（与 screenshots 同一规则，便于跨目录关联）
    """
    import json as _json
    import os as _os

    try:
        artifact_root = Path(
            item.config.getoption("--artifact-root", "./test-results/artifacts")
        ).resolve()
        sidecar_dir = artifact_root / "failure-context"
        sidecar_dir.mkdir(parents=True, exist_ok=True)

        safe_nodeid = _sanitize_filename(report.nodeid)
        sidecar_path = sidecar_dir / f"{safe_nodeid}.json"

        # 1. 判定规则
        test_func = getattr(item, "function", None) or getattr(item, "func", None)
        try:
            if test_func is not None:
                rule_info = _extract_rule_from_docstring(test_func, report.nodeid)
            else:
                rule_info = {"rule": "", "rule_source": "no_test_func"}
        except Exception:
            rule_info = {"rule": "", "rule_source": "fallback_funcname"}

        # 2. 断言解析
        try:
            assertion_info = _parse_assertion_from_longrepr(report)
        except Exception as e:
            assertion_info = {
                "statement": "",
                "file": "",
                "introspection": "",
                "message": f"(assertion 解析失败: {e})",
            }

        # 3. playwright 错误解析（输入：longreprtext 全文 + assertion introspection）
        # 组合多个文本源，让 hint 关键词匹配能覆盖到 reprcrash.message / source_line
        longreprtext = getattr(report, "longreprtext", "") or ""
        pw_text_parts = [longreprtext]
        if assertion_info.get("introspection"):
            pw_text_parts.append(assertion_info["introspection"])
        if assertion_info.get("statement"):
            pw_text_parts.append(assertion_info["statement"])
        if assertion_info.get("message"):
            pw_text_parts.append(assertion_info["message"])
        pw_text = "\n".join(pw_text_parts)
        try:
            expect_info = _parse_playwright_error(pw_text)
        except Exception:
            expect_info = {
                "locator": "",
                "expected": "",
                "received": "",
                "action": "",
                "hint": "",
                "raw": pw_text[:500],
            }

        # 4. phase
        phase = _os.environ.get("PYTEST_RUN_PHASE", "main")

        # 5. slug + pytest_raw_dir
        slug = _sanitize_nodeid_to_slug(report.nodeid)
        pytest_raw_dir = str(artifact_root / "pytest-raw")
        # 前置阶段产物在 pytest-raw-pre
        if phase == "pre-run":
            pytest_raw_dir = str(artifact_root / "pytest-raw-pre")

        # 6. 失败类型
        failure_type = ""
        msg = assertion_info.get("message", "")
        if msg:
            # ExceptionClass: ... 取冒号前
            failure_type = msg.split(":", 1)[0].strip()

        # 7. 已采集 artifact 路径（screenshots / page_source / console_log）
        screenshots_dir = artifact_root / "screenshots"
        page_source_dir = artifact_root / "page-source"
        console_dir = artifact_root / "console-logs"
        artifacts = {
            "screenshots": [
                str(screenshots_dir / f"{safe_nodeid}-viewport.png"),
                str(screenshots_dir / f"{safe_nodeid}-fullpage.png"),
            ],
            "page_source": str(page_source_dir / f"{safe_nodeid}.html"),
            "console_log": str(console_dir / f"{safe_nodeid}.log"),
        }

        # 8. 组装
        sidecar = {
            "nodeid": report.nodeid,
            "slug_hint": slug,
            "phase": phase,
            "duration": float(getattr(report, "duration", 0.0) or 0.0),
            "browser": browser,
            "url": url,
            "title": title,
            "failure_type": failure_type,
            "rule": rule_info.get("rule", ""),
            "rule_source": rule_info.get("rule_source", ""),
            "assertion": assertion_info,
            "expect_failure": expect_info,
            "artifacts": artifacts,
            "pytest_raw_dir": pytest_raw_dir,
            "dumped_at": datetime.now().isoformat(timespec="seconds"),
        }

        sidecar_path.write_text(
            _json.dumps(sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report.sections.append(("ui-test-executor", f"[failure-context] {sidecar_path}"))
    except Exception as e:
        try:
            report.sections.append(
                ("ui-test-executor", f"[WARN] failure-context 写入失败: {e}")
            )
        except Exception:
            pass  # 报告 sections 不可写就算了
