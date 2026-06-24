"""pages_yaml_resolver.py — 从 pages.yaml 找回权威 locator 定义

当 page object 中的 locator 失败时，对比 ui-page-parser 产出的 pages.yaml，
找到对应元素的**权威定义**（首选 data-testid），生成 Playwright locator 字符串。

目的：locator_drift 时提供金标准参考，比纯靠 page-source 候选推断更可靠。

pages.yaml schema（简化）:
    pages:
      - page_name: "登录页"
        url: "/login"
        elements:
          - element_name: "用户名输入框"
            element_type: "input"
            locator:
              strategy: "data-testid"
              value: "[data-testid='login-username']"
              fallback:
                - strategy: "id"
                  value: "#username"
                - strategy: "placeholder"
                  value: "请输入 用户名"
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ============ 数据结构 ============

@dataclass
class YamlResolvedLocator:
    """从 pages.yaml 解析得到的权威 locator。"""
    found: bool
    page_name: str | None = None
    element_name: str | None = None
    canonical_locator: str | None = None  # Playwright 风格 locator 字符串
    strategy: str | None = None
    value: str | None = None
    fallbacks: list[dict[str, str]] = field(default_factory=list)
    match_reason: str = ""  # 文本/placeholder/css 哪种匹配命中


# ============ 主入口 ============

def resolve_locator_from_yaml(
    pages_yaml_path: Path,
    failing_locator_hint: str,
    page_url: str | None = None,
) -> YamlResolvedLocator | None:
    """从 pages.yaml 找到失败 locator 对应的权威定义。

    Args:
        pages_yaml_path: pages.yaml 路径（ui-page-parser 产物）
        failing_locator_hint: 失败的 locator 字符串，如 'get_by_placeholder("X")'
        page_url: 可选，限定在哪个页面找（加速 + 避免误命中）

    Returns:
        YamlResolvedLocator 或 None（yaml 不存在 / 无匹配）
    """
    if not pages_yaml_path.exists():
        return None

    try:
        data = _load_yaml(pages_yaml_path)
    except Exception:
        return None

    pages = data.get("pages") or []
    if not isinstance(pages, list):
        return None

    # 从失败 hint 中提取核心文本/选择器
    hint_identity = _extract_hint_identity(failing_locator_hint)
    if not hint_identity:
        return None

    # 限定页面（若提供 page_url）
    target_pages = pages
    if page_url:
        target_pages = [p for p in pages if _page_matches_url(p, page_url)] or pages

    # 在每个页面的 elements 中找匹配
    for page in target_pages:
        page_name = page.get("page_name", "")
        for element in page.get("elements") or []:
            match = _match_element(element, hint_identity, failing_locator_hint)
            if match:
                canonical = _build_canonical_locator(element)
                return YamlResolvedLocator(
                    found=True,
                    page_name=page_name,
                    element_name=element.get("element_name", ""),
                    canonical_locator=canonical,
                    strategy=match.get("strategy"),
                    value=match.get("value"),
                    fallbacks=_extract_fallbacks(element),
                    match_reason=match.get("reason", ""),
                )

    return YamlResolvedLocator(found=False)


def _load_yaml(path: Path) -> dict[str, Any]:
    """加载 yaml，优先用 PyYAML，不可用时退化到简易解析。"""
    try:
        import yaml  # type: ignore
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data or {}
    except ImportError:
        # 无 PyYAML 时给清晰错误（pages.yaml 复杂，自己解析不现实）
        raise RuntimeError(
            "需要 PyYAML 解析 pages.yaml，请安装: pip install pyyaml"
        )


# ============ hint → identity 提取 ============

def _extract_hint_identity(hint: str) -> dict[str, str]:
    """从 failing locator hint 提取核心 identity。

    Returns:
        {"kind": "placeholder"|"label"|"text"|"css"|"testid"|"role",
         "value": "X"}
    """
    hint = hint.strip()

    # get_by_placeholder("X") / get_by_label("X") / get_by_text("X")
    for api_name in ("placeholder", "label", "text"):
        m = re.search(rf'get_by_{api_name}\(\s*(["\'])(.+?)\1', hint)
        if m:
            return {"kind": api_name, "value": m.group(2)}

    # get_by_test_id("X")
    m = re.search(r'get_by_test_id\(\s*(["\'])(.+?)\1', hint)
    if m:
        return {"kind": "testid", "value": m.group(2)}

    # get_by_role("button", name="X")
    m = re.search(r'get_by_role\(\s*(["\'])(\w+)\1(?:,\s*name=(["\'])(.+?)\3)?', hint)
    if m:
        return {
            "kind": "role",
            "value": m.group(4) or m.group(2),
            "role": m.group(2),
        }

    # locator(".css") / locator("#id") / locator("[attr=val]")
    m = re.search(r'locator\(\s*(["\'])(.+?)\1', hint)
    if m:
        css = m.group(2)
        # 提取 class / id
        cm = re.match(r'\.([a-zA-Z0-9_-]+)', css)
        if cm:
            return {"kind": "css_class", "value": cm.group(1)}
        im = re.match(r'#([a-zA-Z0-9_-]+)', css)
        if im:
            return {"kind": "css_id", "value": im.group(1)}
        tm = re.search(r"data-testid=['\"]([^'\"]+)", css)
        if tm:
            return {"kind": "testid", "value": tm.group(1)}
        return {"kind": "css_raw", "value": css}

    return {}


# ============ element 匹配 ============

def _match_element(
    element: dict,
    hint_identity: dict,
    failing_hint: str,
) -> dict | None:
    """检查 yaml element 是否匹配 hint identity。

    匹配优先级：
        1. element_name 文本完全一致（最严格）
        2. locator.value 直接包含
        3. fallback 列表中包含
    """
    element_name = element.get("element_name", "")
    locator = element.get("locator") or {}
    strategy = locator.get("strategy", "")
    value = locator.get("value", "")

    kind = hint_identity.get("kind", "")
    hint_value = hint_identity.get("value", "")

    # placeholder/label/text 类：element_name 或 locator.value 命中
    if kind in ("placeholder", "label", "text"):
        # element_name 含 hint 文本（如 "用户名输入框" 含 "用户名"）
        if hint_value and (
            hint_value in element_name
            or element_name in hint_value
            or _text_overlap(hint_value, element_name) >= 0.5
        ):
            return {"strategy": strategy, "value": value, "reason": f"element_name '{element_name}' matches hint {kind}"}
        # locator.value 直接含 hint 文本
        if hint_value and hint_value in value:
            return {"strategy": strategy, "value": value, "reason": f"locator.value contains hint {kind}"}
        # fallback 中有 placeholder/label 策略且值匹配
        for fb in locator.get("fallback") or []:
            if fb.get("strategy") == kind and fb.get("value") == hint_value:
                return {"strategy": strategy, "value": value, "reason": f"fallback {kind} exact match"}

    # testid 类
    elif kind == "testid":
        testid = hint_value
        # locator.value 是 [data-testid='xxx'] 形式
        if testid in value:
            return {"strategy": strategy, "value": value, "reason": "data-testid value match"}
        for fb in locator.get("fallback") or []:
            if fb.get("strategy") == "data-testid" and testid in fb.get("value", ""):
                return {"strategy": strategy, "value": value, "reason": "fallback testid match"}

    # role 类
    elif kind == "role":
        role = hint_identity.get("role", "")
        name_hint = hint_value
        if strategy == "role" and role in value:
            if not name_hint or name_hint in value:
                return {"strategy": strategy, "value": value, "reason": "role match"}

    # css 类
    elif kind == "css_class":
        cls = hint_value
        if strategy in ("class", "css") and cls in value:
            return {"strategy": strategy, "value": value, "reason": "css class match"}
    elif kind == "css_id":
        idv = hint_value
        if strategy in ("id", "css") and idv in value:
            return {"strategy": strategy, "value": value, "reason": "css id match"}
    elif kind == "css_raw":
        if value and value in failing_hint:
            return {"strategy": strategy, "value": value, "reason": "css raw match"}

    return None


def _text_overlap(a: str, b: str) -> float:
    """两字符串的字符级重叠率（粗略）。"""
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    overlap = len(set_a & set_b)
    return overlap / max(len(set_a | set_b), 1)


def _page_matches_url(page: dict, url: str) -> bool:
    """yaml page 的 url 是否匹配给定的 url。"""
    page_url = page.get("url", "")
    if not page_url:
        return False
    # 精确 / 后缀 / 包含
    return (
        page_url == url
        or url.endswith(page_url)
        or page_url in url
    )


def _extract_fallbacks(element: dict) -> list[dict[str, str]]:
    locator = element.get("locator") or {}
    return list(locator.get("fallback") or [])


# ============ 构建 Playwright 风格 locator 字符串 ============

def _build_canonical_locator(element: dict) -> str:
    """把 yaml element 的 locator 转换为 Playwright 风格字符串。

    优先级：data-testid > role > label/placeholder/text > id > css > xpath
    """
    locator = element.get("locator") or {}
    strategy = locator.get("strategy", "")
    value = locator.get("value", "")

    # 优先用主 locator，主 locator 不友好时用 fallback
    candidates = [(strategy, value)] + [
        (fb.get("strategy", ""), fb.get("value", ""))
        for fb in locator.get("fallback") or []
    ]

    # 按 Playwright API 友好度排序
    priority = ["data-testid", "role", "label", "placeholder", "text", "id", "css", "xpath"]
    candidates_sorted = sorted(
        candidates,
        key=lambda c: priority.index(c[0]) if c[0] in priority else 99,
    )

    for strat, val in candidates_sorted:
        playwright_str = _to_playwright_locator(strat, val)
        if playwright_str:
            return playwright_str

    # 兜底：直接用主 locator 的 value 作为 css
    return f'page.locator("{value}")'


def _to_playwright_locator(strategy: str, value: str) -> str | None:
    """单条 locator → Playwright 字符串。"""
    if not value:
        return None
    s = strategy.lower()
    if s == "data-testid":
        # value 可能是 "[data-testid='xxx']" 或纯 "xxx"
        m = re.search(r"data-testid=['\"]([^'\"]+)", value)
        testid = m.group(1) if m else value
        return f'page.get_by_test_id("{testid}")'
    if s == "role":
        # value 形如 "button[name='登录']" 或 "button"
        m = re.match(r"(\w+)(?:\[(\w+)=['\"](.+?)['\"]\])?", value)
        if m:
            role = m.group(1)
            attr = m.group(2)
            attr_val = m.group(3)
            if attr == "name" and attr_val:
                return f'page.get_by_role("{role}", name="{attr_val}")'
            return f'page.get_by_role("{role}")'
        return None
    if s == "label":
        return f'page.get_by_label("{value}")'
    if s == "placeholder":
        return f'page.get_by_placeholder("{value}")'
    if s == "text":
        return f'page.get_by_text("{value}")'
    if s == "id":
        # value 可能是 "#xxx" 或纯 "xxx"
        idv = value.lstrip("#")
        return f'page.locator("#{idv}")'
    if s == "css":
        return f'page.locator("{value}")'
    if s == "xpath":
        # value 可能以 // 开头，或不带前缀
        xp = value if value.startswith(("//", "(")) else f"//{value}"
        return f'page.locator("xpath={xp}")'
    if s == "class":
        return f'page.locator(".{value}")'
    return None
