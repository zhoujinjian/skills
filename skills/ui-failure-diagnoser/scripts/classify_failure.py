"""classify_failure.py — 6 类失败分类器

基于 JUnit failure message + page-source HTML + console-log 判定失败类型。

6 类（MVP 实装前 3 类的完整判定，后 3 类只打 tag）:
    ENV_ERROR      浏览器/驱动级错误（不可恢复）
    LOCATOR_ERROR  TimeoutError + locator 在 page-source 中不存在（DOM 改了）
    TIMEOUT_ERROR  TimeoutError + locator 在 page-source 中存在（渲染慢）
    DATA_ERROR     setup 阶段失败 + fixture 数据问题
    SCRIPT_ERROR   原生 AssertionError（业务断言）
    BUG            console-logs 含 Page Error / Uncaught / 网络 5xx

判定优先级（多信号同时出现时）:
    ENV_ERROR > BUG > LOCATOR/TIMEOUT > DATA_ERROR > SCRIPT_ERROR
    （环境挂了什么都无意义；BUG 是根因；其余按可修复性排序）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable


# ============ 信号模式库 ============

_ENV_PATTERNS = [
    r"Browser has been closed",
    r"Target page, context or browser has been closed",
    r"Protocol error",
    r"chrome not reachable",
    r"Failed to connect to DevTools",
    # 浏览器未安装（playwright install 缺失）
    r"Executable doesn't exist",
    r"Executable does not exist",
    r"BrowserType\.launch.*?(?:chromium|firefox|webkit|chrome)[\s\S]{0,40}(?:not found|doesn't exist)",
    r"playwright install",
    r"ERR_CONNECTION_REFUSED",
    r"ECONNREFUSED",
    r"Address already in use",
    # Python 包缺失
    r"ModuleNotFoundError",
    r"ImportError: No module named",
]

_TIMEOUT_PATTERN = re.compile(
    r"TimeoutError|Timeout \d+ms exceeded|Locator\.\w+: Timeout",
    re.IGNORECASE,
)

# 从失败消息里提取 locator 描述（用于 LOCATOR vs TIMEOUT 判定）
_LOCATOR_HINT_PATTERNS = [
    re.compile(r'waiting for (get_by_\w+\([^)]+\)(?:\.\w+\([^)]+\))*)'),
    re.compile(r'waiting for (locator\([^)]+\))'),
    re.compile(r'(get_by_\w+\([^)]+\)(?:\.\w+\([^)]+\))*)'),
    re.compile(r'(locator\(["\'][^"\']+["\']\))'),
]

_BUG_PATTERNS = [
    r"Uncaught \w+Error",
    r"\bPage Error\b",
    r"ReferenceError",
    r"TypeError: Cannot read propert",
    r"Network[\s\S]*?\b5\d\d\b",
    r"\b5\d\d\b[\s\S]{0,40}(?:Internal Server Error|Server Error)",
]

_FIXTURE_FAILURE_PATTERNS = [
    r"failed on setup",
    r"setup.{0,50}fixture",
    r"registered_user",
    r"test_user.*not found",
]


@dataclass
class ClassifiedFailure:
    """分类结果。"""
    nodeid: str
    category: str  # ENV_ERROR / LOCATOR_ERROR / TIMEOUT_ERROR / DATA_ERROR / SCRIPT_ERROR / BUG
    confidence: float  # 0.0-1.0
    signals: list[str] = field(default_factory=list)  # 触发该分类的信号描述
    raw_message: str = ""
    locator_hint: str | None = None  # LOCATOR/TIMEOUT 时提取的 locator 字符串
    page_source_path: str | None = None
    console_log_path: str | None = None
    failure_stage: str = "call"  # setup / call / teardown


# ============ 主分类函数 ============

def classify(
    nodeid: str,
    message: str,
    traceback: str = "",
    page_source: str | None = None,
    console_log: str | None = None,
    failure_stage: str = "call",
) -> ClassifiedFailure:
    """对单个失败用例分类。

    Args:
        nodeid: pytest nodeid
        message: JUnit failure message（含异常类名 + 摘要）
        traceback: 完整 traceback（可选，用于增强判定）
        page_source: 失败时的 DOM 快照 HTML（LOCATOR vs TIMEOUT 的关键证据）
        console_log: 失败时的 5 段合并日志（BUG 判定的金标准）
        failure_stage: "setup" / "call" / "teardown"

    Returns:
        ClassifiedFailure
    """
    combined_text = f"{message}\n{traceback}"

    # 1. ENV_ERROR — 最高优先级（环境挂了什么都无意义）
    for pattern in _ENV_PATTERNS:
        if re.search(pattern, combined_text, re.IGNORECASE):
            return ClassifiedFailure(
                nodeid=nodeid,
                category="ENV_ERROR",
                confidence=0.95,
                signals=[f"matched env pattern: {pattern}"],
                raw_message=message,
                failure_stage=failure_stage,
            )

    # 2. BUG — console-log 有 Page Error / 网络 5xx
    bug_signal = _detect_bug_signal(console_log, combined_text)
    if bug_signal:
        return ClassifiedFailure(
            nodeid=nodeid,
            category="BUG",
            confidence=0.85,
            signals=[bug_signal],
            raw_message=message,
            console_log_path=None,
            failure_stage=failure_stage,
        )

    # 3. LOCATOR_ERROR / TIMEOUT_ERROR — 都基于 TimeoutError
    locator_hint = _extract_locator_hint(combined_text)
    if _TIMEOUT_PATTERN.search(combined_text) and locator_hint:
        if _is_locator_in_page_source(locator_hint, page_source):
            return ClassifiedFailure(
                nodeid=nodeid,
                category="TIMEOUT_ERROR",
                confidence=0.80,
                signals=[f"locator '{locator_hint}' present in page-source"],
                raw_message=message,
                locator_hint=locator_hint,
                failure_stage=failure_stage,
            )
        elif page_source is None:
            # page-source 缺失：消息直接含 Timeout → 优先 TIMEOUT_ERROR
            # （元素在不在 DOM 不可知，但 timeout 已是直接证据；
            #  TIMEOUT 走 ast_rewrite 确定性修复，比 LOCATOR 的语义推断更安全）
            return ClassifiedFailure(
                nodeid=nodeid,
                category="TIMEOUT_ERROR",
                confidence=0.65,
                signals=[f"Timeout keyword + page-source missing → TIMEOUT_ERROR (defer to ast_rewrite)"],
                raw_message=message,
                locator_hint=locator_hint,
                failure_stage=failure_stage,
            )
        else:
            # page-source 在但 locator 不在其中 → LOCATOR_ERROR（DOM 改了）
            return ClassifiedFailure(
                nodeid=nodeid,
                category="LOCATOR_ERROR",
                confidence=0.75,
                signals=[f"locator '{locator_hint}' absent in page-source (DOM changed)"],
                raw_message=message,
                locator_hint=locator_hint,
                failure_stage=failure_stage,
            )

    # 4. DATA_ERROR — setup 阶段 + fixture 数据
    if failure_stage == "setup" or _match_any(_FIXTURE_FAILURE_PATTERNS, combined_text):
        return ClassifiedFailure(
            nodeid=nodeid,
            category="DATA_ERROR",
            confidence=0.70,
            signals=["setup-stage failure or fixture data issue"],
            raw_message=message,
            failure_stage=failure_stage,
        )

    # 5. SCRIPT_ERROR — 原生 AssertionError（业务断言）
    if "AssertionError" in combined_text or "assert " in combined_text.lower():
        return ClassifiedFailure(
            nodeid=nodeid,
            category="SCRIPT_ERROR",
            confidence=0.65,
            signals=["native AssertionError (business assertion)"],
            raw_message=message,
            failure_stage=failure_stage,
        )

    # 兜底：归为 SCRIPT_ERROR（保守，引导人工查看）
    return ClassifiedFailure(
        nodeid=nodeid,
        category="SCRIPT_ERROR",
        confidence=0.30,
        signals=["no specific signal matched, fell back to SCRIPT_ERROR"],
        raw_message=message,
        failure_stage=failure_stage,
    )


# ============ 辅助函数 ============

def _detect_bug_signal(console_log: str | None, combined: str) -> str | None:
    """检测 BUG 信号：先看 console-log（金标准），再看 message。"""
    if console_log:
        for pattern in _BUG_PATTERNS:
            m = re.search(pattern, console_log, re.IGNORECASE)
            if m:
                return f"console-log matched: {m.group(0)}"
    for pattern in _BUG_PATTERNS:
        m = re.search(pattern, combined, re.IGNORECASE)
        if m:
            return f"message matched: {m.group(0)}"
    return None


def _extract_locator_hint(text: str) -> str | None:
    """从失败消息中提取 locator 字符串。"""
    for pattern in _LOCATOR_HINT_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1).strip()
    return None


def _match_any(patterns: Iterable[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _is_locator_in_page_source(locator_hint: str, page_source: str | None) -> bool:
    """判定 locator 描述是否能在 page-source 中找到对应元素。

    Args:
        locator_hint: 如 'get_by_placeholder("请输入 用户名")' 或 'locator("div.login-form")'
        page_source: HTML 字符串。None 时返回 False（保守判定为 LOCATOR_ERROR）。

    解析策略：
        get_by_placeholder("X")  → 找 placeholder="X" 的 <input> / <textarea>
        get_by_role("button", name="X") → 找 role="button" 且含 X 或 <button>X</button>
        get_by_text("X")  → 找含文本 X 的元素
        locator("CSS")    → CSS selector 启发式（class / id / data-testid）
    """
    if page_source is None:
        return False

    hint = locator_hint.strip()
    return _HintMatcher(hint, page_source).match()


class _HintMatcher:
    """把 Playwright locator 字符串转成 DOM 存在性判定。"""

    def __init__(self, hint: str, html: str):
        self.hint = hint
        self.html = html

    def match(self) -> bool:
        hint = self.hint
        # get_by_placeholder("X")
        m = re.match(r'get_by_placeholder\(["\'](.+?)["\']', hint)
        if m:
            return self._check_placeholder(m.group(1))

        # get_by_label("X")
        m = re.match(r'get_by_label\(["\'](.+?)["\']', hint)
        if m:
            return self._check_label(m.group(1))

        # get_by_role("button", name="X") / get_by_role("link", name="X")
        m = re.match(r'get_by_role\(["\'](\w+)["\'](?:,\s*name=["\'](.+?)["\'])?', hint)
        if m:
            return self._check_role(m.group(1), m.group(2))

        # get_by_text("X")
        m = re.match(r'get_by_text\(["\'](.+?)["\']', hint)
        if m:
            return m.group(1) in self.html

        # get_by_test_id("X") / data-testid="X"
        m = re.match(r'get_by_test_id\(["\'](.+?)["\']', hint)
        if m:
            return f'data-testid="{m.group(1)}"' in self.html or f"data-testid='{m.group(1)}'" in self.html

        # locator("CSS")
        m = re.match(r'locator\(["\'](.+?)["\']', hint)
        if m:
            return self._check_css(m.group(1))

        return False

    def _check_placeholder(self, text: str) -> bool:
        return (
            f'placeholder="{text}"' in self.html
            or f"placeholder='{text}'" in self.html
            or f'placeholder="{text.lower()}"' in self.html.lower()
        )

    def _check_label(self, text: str) -> bool:
        return (
            f'<label>{text}</label>' in self.html
            or f'>{text}</label>' in self.html
            or f'aria-label="{text}"' in self.html
        )

    def _check_role(self, role: str, name: str | None) -> bool:
        # <button>X</button> / <a>X</a> / role="button"
        tag_map = {"button": "button", "link": "a", "textbox": "input", "checkbox": "input"}
        tag = tag_map.get(role.lower(), role.lower())
        if f"<{tag}" in self.html.lower():
            if name is None:
                return True
            # 简化：元素文本包含 name 即算命中
            return name in self.html
        if f'role="{role.lower()}"' in self.html.lower():
            return True
        return False

    def _check_css(self, css: str) -> bool:
        # 启发式：class / id / data-testid
        # div.login-form → class="login-form"
        m = re.match(r'(?:[a-zA-Z0-9]+)?\.([a-zA-Z0-9_-]+)', css)
        if m:
            cls = m.group(1)
            return f'class="{cls}' in self.html or f"class='{cls}" in self.html
        # #id-name → id="id-name"
        m = re.match(r'#([a-zA-Z0-9_-]+)', css)
        if m:
            return f'id="{m.group(1)}"' in self.html
        # 其他 CSS 不做复杂解析，直接子串匹配
        return css in self.html
