### Task 4: `_parse_playwright_error`

**Files:**
- Create: `evals/failure_analysis/fixtures/playwright_expect_visible.txt`
- Create: `evals/failure_analysis/test_parse_playwright_error.py`
- Modify: `assets/conftest_template.py`（追加 `_parse_playwright_error`）

- [ ] **Step 1: 准备 fixture（预录真实 playwright expect 失败消息）**

文件 `evals/failure_analysis/fixtures/playwright_expect_visible.txt`：

```
LocatorAssertions.to_be_visible: Timeout 30000ms exceeded.
Call log:
  LocatorAssertions.to_be_visible with timeout 30000ms

  Waiting for Locator(selector=".product-card")
    ...
```

文件 `evals/failure_analysis/fixtures/playwright_text_mismatch.txt`：

```
Error: Locator.expect(to_have_text):
  Expected value: "小米手机"
  Received value: ""
  Locator: get_by_role("button", name="搜索")
```

- [ ] **Step 2: 写失败测试**

文件 `evals/failure_analysis/test_parse_playwright_error.py`：

```python
"""测试 _parse_playwright_error。

输入：playwright 失败消息原文（从 report.longreprtext 提取的段落）。
输出：结构化字段 locator / expected / received / action / hint / raw。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    spec = importlib.util.spec_from_file_location(
        "_conftest_under_test",
        Path(__file__).parent.parent.parent / "assets" / "conftest_template.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_conftest_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_locator_timeout_visible():
    mod = _load()
    msg = Path(__file__).parent / "fixtures" / "playwright_expect_visible.txt"
    text = msg.read_text(encoding="utf-8")
    result = mod._parse_playwright_error(text)
    assert result["locator"] == ".product-card"
    assert result["action"] == "to_be_visible"
    assert "Timeout" in result["received"] or "30000ms" in result["received"]
    assert "元素未在超时内出现/可见" in result["hint"]


def test_text_mismatch():
    mod = _load()
    msg = Path(__file__).parent / "fixtures" / "playwright_text_mismatch.txt"
    text = msg.read_text(encoding="utf-8")
    result = mod._parse_playwright_error(text)
    assert result["expected"] == "小米手机"
    assert result["received"] == '""' or result["received"] == ""
    assert "文案变更" in result["hint"]


def test_no_playwright_structure_falls_back_to_raw():
    """非 playwright 错误消息 → 所有字段空，raw 保留原文"""
    mod = _load()
    text = "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0\nassert 0 > 0"
    result = mod._parse_playwright_error(text)
    assert result["locator"] == ""
    assert result["expected"] == ""
    assert result["received"] == ""
    assert result["action"] == ""
    assert result["raw"] == text
    # hint 仍可基于关键词匹配得出（断言含 count = 0）
    assert result["hint"]  # 非空


def test_hint_for_count_zero_locator_inferred():
    """原生 assert count = 0 + introspection 中能看出 locator → 推断「定位器不匹配」"""
    mod = _load()
    text = (
        "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0\n"
        "assert 0 > 0\n"
        "count = 0"
    )
    result = mod._parse_playwright_error(text)
    assert "定位器" in result["hint"] or "DOM" in result["hint"]


def test_protocol_error_navigation_hint():
    """Protocol error + navigate → URL/base_url 配置问题"""
    mod = _load()
    text = 'playwright._impl._errors.Error: Page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL\n  navigating to "/register"'
    result = mod._parse_playwright_error(text)
    assert "URL" in result["hint"] or "base_url" in result["hint"] or "配置" in result["hint"]


def test_empty_input():
    mod = _load()
    result = mod._parse_playwright_error("")
    assert result["raw"] == ""
    assert result["hint"] == ""
```

- [ ] **Step 3: 跑测试看失败**

```bash
python3 -m pytest evals/failure_analysis/test_parse_playwright_error.py -v
```
Expected: FAIL with `AttributeError: ... has no attribute '_parse_playwright_error'`

- [ ] **Step 4: 实现**

在 `assets/conftest_template.py` 的 `_parse_assertion_from_longrepr` 后追加：

```python
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
# count = 0 / count=0 / count is 0
_PW_COUNT_ZERO_RE = _re_pw.compile(r"count\s*[=><!]+\s*0\b|count\s+is\s+0\b", _re_pw.IGNORECASE)


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
      3. Expected ≠ Received（且 received 为空或不同） → 文案变更
      4. count = 0 + locator 已知 → 定位器与实际 DOM class 不匹配
      5. 其他 → hint 为空
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

    # 3. Expected ≠ Received 文本不匹配
    if parsed["expected"] and parsed["received"] and parsed["expected"] != parsed["received"]:
        return "文案变更（推断，仅作参考）"

    # 4. count = 0 类断言 + locator 已知
    if _PW_COUNT_ZERO_RE.search(text) and has_locator:
        return "定位器与实际 DOM class 不匹配（推断，仅作参考）"

    # 5. count = 0 但无 locator（原生 assert）
    if _PW_COUNT_ZERO_RE.search(text):
        return "定位器与实际 DOM class 不匹配（推断，仅作参考）"

    return ""
```

- [ ] **Step 5: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_parse_playwright_error.py -v
```
Expected: PASS (6 个测试)

- [ ] **Step 6: Commit**

```bash
git add evals/failure_analysis/fixtures/playwright_expect_visible.txt evals/failure_analysis/fixtures/playwright_text_mismatch.txt evals/failure_analysis/test_parse_playwright_error.py assets/conftest_template.py
git commit -m "feat(failure-analysis): parse playwright error structure + infer hint by keyword match"
```

---

