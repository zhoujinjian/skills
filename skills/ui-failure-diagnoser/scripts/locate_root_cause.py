"""locate_root_cause.py — 根因定位（12 种）

对 6 类失败都做根因定位，返回具体的可执行修复策略。

12 种根因：
    LOCATOR/TIMEOUT（5 种）:
        locator_drift            DOM 改了 → Claude 语义推断新 selector
        insufficient_wait        元素在但 timeout 太短 → AST rewrite timeout
        missing_iframe_switch    iframe 未切换 → AST rewrite 加 frame_locator
        page_not_loaded          页面未加载完就交互 → 加 wait_for_load_state
        shadow_dom_not_pierced   元素在 Shadow DOM → 推荐用 >>> piercing selector

    ENV_ERROR（4 种）:
        missing_browser_binary   Playwright 浏览器未安装 → playwright install
        missing_python_package   Python 包缺失 → pip install
        port_conflict            端口被占用 → lsof kill
        service_unavailable      后端服务不可达 → 启动服务

    DATA_ERROR（2 种）:
        unique_constraint_conflict  唯一约束冲突（脏数据）→ 清理
        fixture_data_missing        fixture 初始化失败 → seed

    BUG（1 种）:
        known_bug_pattern        命中已知 bug 指纹 → xfail/flaky marker

fix_strategy 取值：
    ast_rewrite        确定性 AST 修改（pages/**/*.py）
    claude_semantic    由 Claude 语义推断（无确定性修复）
    category_repair    派发到类别专属修复模块（env_repair / data_repair / bug_repair）
    none               仅诊断，无自动修复
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RootCause:
    """根因定位结果。"""
    root_cause: str  # 见模块 docstring 的 12 种
    fix_strategy: str  # ast_rewrite / claude_semantic / category_repair / none
    evidence: dict[str, Any] = field(default_factory=dict)


# ============ 主入口 ============

def locate(
    classified_failure,
    page_source: str | None = None,
    iframe_contents: dict[str, str] | None = None,
) -> RootCause | None:
    """对单个 ClassifiedFailure 定位根因（6 类 × 12 子因）。

    Args:
        classified_failure: classify_failure.classify() 返回的对象
        page_source: 失败时主文档的 HTML 快照
        iframe_contents: {iframe_url: iframe_html} 映射，用于 missing_iframe_switch 判定

    Returns:
        RootCause 或 None（证据不足时）
    """
    category = getattr(classified_failure, "category", "")
    locator_hint = getattr(classified_failure, "locator_hint", None)
    message = getattr(classified_failure, "raw_message", "") or ""

    # LOCATOR_ERROR / TIMEOUT_ERROR
    if category in ("LOCATOR_ERROR", "TIMEOUT_ERROR"):
        if not locator_hint:
            return None
        if category == "TIMEOUT_ERROR":
            return _locate_timeout(classified_failure, page_source)
        return _locate_locator_error(classified_failure, page_source, iframe_contents)

    # ENV_ERROR
    if category == "ENV_ERROR":
        return _locate_env_error(classified_failure)

    # DATA_ERROR
    if category == "DATA_ERROR":
        return _locate_data_error(classified_failure)

    # BUG
    if category == "BUG":
        return _locate_bug(classified_failure)

    # SCRIPT_ERROR：细分 missing_async_list_wait / script_error_unspecified
    if category == "SCRIPT_ERROR":
        return _locate_script_error(classified_failure)

    return None


def locate_all(
    classified_failures: list,
    page_source_map: dict[str, str] | None = None,
    iframe_contents_map: dict[str, dict[str, str]] | None = None,
) -> list[RootCause | None]:
    """批量定位。返回与输入同序的列表（不可定位的为 None）。"""
    page_source_map = page_source_map or {}
    iframe_contents_map = iframe_contents_map or {}
    results: list[RootCause | None] = []
    for cf in classified_failures:
        nodeid = getattr(cf, "nodeid", "")
        ps = page_source_map.get(nodeid)
        ic = iframe_contents_map.get(nodeid)
        results.append(locate(cf, page_source=ps, iframe_contents=ic))
    return results


# ============ 内部实现 ============

_TIMEOUT_PATTERN = re.compile(r"Timeout\s+(\d+)\s*ms", re.IGNORECASE)
_PAGE_GOTO_PATTERN = re.compile(r"page\.goto|page\.wait_for_url", re.IGNORECASE)


def _locate_timeout(classified_failure, page_source: str | None = None) -> RootCause:
    """TIMEOUT_ERROR → insufficient_wait / page_not_loaded。

    区分策略：
        - message 含 page.goto → page_not_loaded（页面导航后未加载完）
        - 否则 → insufficient_wait（单纯超时太短）
    """
    msg = getattr(classified_failure, "raw_message", "") or ""
    locator_hint = getattr(classified_failure, "locator_hint", None)

    # 1. 页面未加载完（goto 之后立即交互）
    if _PAGE_GOTO_PATTERN.search(msg):
        return RootCause(
            root_cause="page_not_loaded",
            fix_strategy="ast_rewrite",
            evidence={
                "locator_hint": locator_hint,
                "suggested_wait_state": "networkidle",
                "reason": "Timeout 紧跟 page.goto，可能是页面未加载完",
            },
        )

    # 2. 默认：等待不足
    m = _TIMEOUT_PATTERN.search(msg)
    original_ms = int(m.group(1)) if m else 10000
    suggested_ms = max(original_ms * 3, 30000)
    return RootCause(
        root_cause="insufficient_wait",
        fix_strategy="ast_rewrite",
        evidence={
            "original_timeout_ms": original_ms,
            "suggested_timeout_ms": suggested_ms,
            "locator_hint": locator_hint,
        },
    )


def _locate_locator_error(
    classified_failure,
    page_source: str | None,
    iframe_contents: dict[str, str] | None,
) -> RootCause:
    """LOCATOR_ERROR → missing_iframe_switch / shadow_dom_not_pierced / locator_drift。"""
    locator_hint = getattr(classified_failure, "locator_hint", None)

    # 1. 检查 iframe 内是否有 locator
    if iframe_contents:
        iframe_hit = _find_locator_in_iframes(locator_hint, iframe_contents)
        if iframe_hit:
            return RootCause(
                root_cause="missing_iframe_switch",
                fix_strategy="ast_rewrite",
                evidence={
                    "iframe_url": iframe_hit["url"],
                    "iframe_locator": iframe_hit["css_selector"],
                    "locator_hint": locator_hint,
                },
            )

    # 2. 检查 Shadow DOM（启发式：page-source 含 #shadow-root 或 custom-element）
    if page_source and _looks_like_shadow_dom(page_source):
        return RootCause(
            root_cause="shadow_dom_not_pierced",
            fix_strategy="claude_semantic",
            evidence={
                "original_locator": locator_hint,
                "reason": "page-source 含 Shadow DOM 标志，元素可能在闭 Shadow Root 内",
                "suggested_pierce": "使用 page.locator('custom-element >>> target') 穿透 Shadow DOM",
            },
        )

    # 3. 默认：locator_drift，收集候选元素
    candidates = _collect_candidates(locator_hint, page_source)
    return RootCause(
        root_cause="locator_drift",
        fix_strategy="claude_semantic",
        evidence={
            "original_locator": locator_hint,
            "candidates": candidates,
        },
    )


def _looks_like_shadow_dom(page_source: str) -> bool:
    """启发式：判定页面是否使用了 Shadow DOM。"""
    if not page_source:
        return False
    signals = [
        "shadowRoot",
        "attachShadow",
        "customElements",
        "<my-",  # 自定义元素（如 <my-button>）
        "data-v-",  # Vue scoped style
    ]
    return any(sig in page_source for sig in signals)


# ============ ENV_ERROR 根因（4 种）============

def _locate_env_error(classified_failure) -> RootCause:
    """ENV_ERROR → 4 种子因之一。"""
    msg = getattr(classified_failure, "raw_message", "") or ""

    # 1. Playwright 浏览器未安装
    if re.search(r"Executable doesn't exist|Executable does not exist|playwright install", msg, re.IGNORECASE):
        browser = "chromium"
        for b in ("firefox", "webkit", "chrome", "chromium"):
            if b in msg.lower():
                browser = "chromium" if b == "chrome" else b
                break
        return RootCause(
            root_cause="missing_browser_binary",
            fix_strategy="category_repair",
            evidence={"browser": browser, "raw_message": msg},
        )

    # 2. Python 包缺失
    m = re.search(r"ModuleNotFoundError: No module named ['\"]([\w.]+)['\"]", msg)
    if m:
        module = m.group(1)
        return RootCause(
            root_cause="missing_python_package",
            fix_strategy="category_repair",
            evidence={"module": module, "raw_message": msg},
        )

    # 3. 端口冲突
    m = re.search(r"Address already in use[^0-9]*(\d+)|EADDRINUSE.*?(\d+)", msg, re.IGNORECASE)
    if m:
        port = int(m.group(1) or m.group(2))
        return RootCause(
            root_cause="port_conflict",
            fix_strategy="category_repair",
            evidence={"port": port, "raw_message": msg},
        )

    # 4. 服务不可达
    m = re.search(r"ECONNREFUSED\s+([\d.]+):(\d+)|ERR_CONNECTION_REFUSED\s+([\d.]+):(\d+)", msg)
    if m:
        host = m.group(1) or m.group(3)
        port = int(m.group(2) or m.group(4))
        return RootCause(
            root_cause="service_unavailable",
            fix_strategy="category_repair",
            evidence={"host": host, "port": port, "raw_message": msg},
        )

    # 兜底：未知 ENV 问题
    return RootCause(
        root_cause="env_error_unspecified",
        fix_strategy="category_repair",
        evidence={"raw_message": msg},
    )


# ============ DATA_ERROR 根因（2 种）============

def _locate_data_error(classified_failure) -> RootCause:
    """DATA_ERROR → unique_constraint / fixture_init_fail。"""
    msg = getattr(classified_failure, "raw_message", "") or ""

    # 1. 唯一约束冲突
    m = re.search(
        r"unique\s+constraint\s+failed:\s*([\w.]+)|"
        r"Duplicate entry.*?for key.*?['\"]([\w.]+)['\"]|"
        r'duplicate key value violates unique constraint "([\w_]+)"',
        msg, re.IGNORECASE,
    )
    if m:
        constraint = next((g for g in m.groups() if g), "unknown")
        return RootCause(
            root_cause="unique_constraint_conflict",
            fix_strategy="category_repair",
            evidence={"constraint": constraint, "raw_message": msg},
        )

    # 2. Fixture 数据缺失
    m = re.search(r"fixture ['\"]([\w_]+)['\"].*?(?:not found|failed)|ERROR at setup of\s+([\w_]+)", msg, re.IGNORECASE)
    if m:
        fixture = m.group(1) or m.group(2)
        return RootCause(
            root_cause="fixture_data_missing",
            fix_strategy="category_repair",
            evidence={"fixture": fixture, "raw_message": msg},
        )

    # 兜底
    return RootCause(
        root_cause="data_error_unspecified",
        fix_strategy="category_repair",
        evidence={"raw_message": msg},
    )


# ============ BUG 根因（1 种 + 兜底）============

def _locate_bug(classified_failure) -> RootCause:
    """BUG → known_bug_pattern / stable_bug。"""
    # KNOWN_BUG_SIGNATURES 在 bug_repair 中维护；本函数仅打 tag
    msg = getattr(classified_failure, "raw_message", "") or ""
    return RootCause(
        root_cause="known_bug_pattern",
        fix_strategy="category_repair",
        evidence={"raw_message": msg},
    )


def _find_locator_in_iframes(
    locator_hint: str, iframe_contents: dict[str, str]
) -> dict | None:
    """判定 locator 是否出现在某个 iframe 的 HTML 中。"""
    # 提取 locator_hint 的核心文本（如 placeholder 的值）
    target_text = _extract_target_text(locator_hint)
    if not target_text:
        return None

    for url, html in iframe_contents.items():
        if target_text in html:
            css = f'iframe[src="{url}"]'
            if css not in html and url:
                # 尝试 src 部分匹配
                path = url.rsplit("/", 1)[-1] if "/" in url else url
                if f'src="{url}' in html or f"src='{url}" in html:
                    css = f'iframe[src="{url}"]'
                elif path and f'src="{path}' in html:
                    css = f'iframe[src="{path}"]'
            return {"url": url, "css_selector": css}
    return None


def _extract_target_text(locator_hint: str) -> str | None:
    """从 locator 字符串提取核心目标文本（用于 iframe 内搜索）。"""
    for pattern in [
        r'get_by_placeholder\(["\'](.+?)["\']',
        r'get_by_label\(["\'](.+?)["\']',
        r'get_by_text\(["\'](.+?)["\']',
        r'get_by_role\(\s*["\']\w+["\']\s*,\s*name=["\'](.+?)["\']',
        r'get_by_test_id\(["\'](.+?)["\']',
    ]:
        m = re.search(pattern, locator_hint)
        if m:
            return m.group(1)
    # CSS locator 的核心：class / id
    m = re.search(r'locator\(["\']\.(.+?)["\']', locator_hint)
    if m:
        return m.group(1)
    m = re.search(r'locator\(["\']#(.+?)["\']', locator_hint)
    if m:
        return m.group(1)
    return None


def _collect_candidates(locator_hint: str, page_source: str | None) -> list[dict]:
    """从 page-source 收集与 locator_hint 同类的候选元素。

    Returns:
        [{"kind": "placeholder", "value": "账号"}, ...]
    """
    if not page_source:
        return []

    candidates: list[dict] = []
    hint_kind = _detect_hint_kind(locator_hint)

    if hint_kind == "placeholder":
        for m in re.finditer(r'placeholder="([^"]+)"', page_source):
            candidates.append({"kind": "placeholder", "value": m.group(1)})
        for m in re.finditer(r"placeholder='([^']+)'", page_source):
            candidates.append({"kind": "placeholder", "value": m.group(1)})
    elif hint_kind == "label":
        for m in re.finditer(r"<label[^>]*>([^<]+)</label>", page_source):
            candidates.append({"kind": "label", "value": m.group(1).strip()})
        for m in re.finditer(r'aria-label="([^"]+)"', page_source):
            candidates.append({"kind": "aria_label", "value": m.group(1)})
    elif hint_kind == "role_button":
        for m in re.finditer(r"<button[^>]*>([^<]*)</button>", page_source):
            text = m.group(1).strip()
            if text:
                candidates.append({"kind": "button_text", "value": text})
    elif hint_kind == "text":
        target = _extract_target_text(locator_hint)
        if target:
            for m in re.finditer(r">([^<]{0,50})<", page_source):
                text = m.group(1).strip()
                if text and len(text) < 50:
                    candidates.append({"kind": "text_node", "value": text})
    elif hint_kind == "class":
        for m in re.finditer(r'class="([^"]+)"', page_source):
            candidates.append({"kind": "class", "value": m.group(1)})
    elif hint_kind == "id":
        for m in re.finditer(r'id="([^"]+)"', page_source):
            candidates.append({"kind": "id", "value": m.group(1)})

    # 去重 + 截短
    seen = set()
    unique: list[dict] = []
    for c in candidates:
        key = (c["kind"], c["value"])
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique[:20]  # 避免候选过多


def _detect_hint_kind(locator_hint: str) -> str:
    """识别 locator 类型，用于候选收集。"""
    if "get_by_placeholder" in locator_hint:
        return "placeholder"
    if "get_by_label" in locator_hint:
        return "label"
    if "get_by_role" in locator_hint:
        if "button" in locator_hint.lower():
            return "role_button"
        return "role_other"
    if "get_by_text" in locator_hint:
        return "text"
    if "get_by_test_id" in locator_hint:
        return "test_id"
    if "locator(" in locator_hint:
        if re.search(r'locator\(["\']\.', locator_hint):
            return "class"
        if re.search(r'locator\(["\']#', locator_hint):
            return "id"
        return "css_other"
    return "unknown"


# ============ SCRIPT_ERROR 根因（2 种）============

_SEARCH_CONTEXT = re.compile(
    r"搜索|search|查询|检索",
    re.IGNORECASE,
)
_POSITIVE_EXPECTATION = re.compile(
    r"应返回|应为|应存在|应该有|should return|should have|expected",
    re.IGNORECASE,
)
_ZERO_ACTUAL = re.compile(
    r"结果数.{0,3}0(?![0-9])"
    r"|count.{0,5}=\s*0(?![0-9])"
    r"|count is 0"
    r"|returned 0"
    r"|数量为 0"
    r"|共 0 条"
    r"|实际.{0,5}0(?![0-9])",
    re.IGNORECASE,
)


def _locate_script_error(classified_failure) -> RootCause:
    """SCRIPT_ERROR → missing_async_list_wait / script_error_unspecified.

    信号三点 AND：
        - 搜索语境（搜索/search/查询/检索）
        - 正向期望（应返回/应为/should return/expected）
        - 实际为 0（结果数为 0/count is 0/returned 0）

    负向断言（应 0 实际 N）自动不匹配：ZERO_ACTUAL 不命中。
    """
    msg = getattr(classified_failure, "raw_message", "") or ""

    if _is_search_zero_assertion(msg):
        return RootCause(
            root_cause="missing_async_list_wait",
            fix_strategy="ast_rewrite",
            evidence={
                "reason": "搜索正向断言期望>0 实际=0，可能是异步加载未完成",
                "suggested_fix": "在 get_product_count() 之前插入 _wait_for_product_list_loaded()",
            },
        )

    return RootCause(
        root_cause="script_error_unspecified",
        fix_strategy="category_repair",
        evidence={"message": msg},
    )


def _is_search_zero_assertion(message: str) -> bool:
    """三点 AND 判定搜索 0 结果断言。"""
    return all(
        p.search(message) for p in
        (_SEARCH_CONTEXT, _POSITIVE_EXPECTATION, _ZERO_ACTUAL)
    )
