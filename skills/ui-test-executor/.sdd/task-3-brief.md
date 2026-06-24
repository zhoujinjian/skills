### Task 3: `_parse_assertion_from_longrepr`

**Files:**
- Create: `evals/failure_analysis/fixtures/longrepr_native_assert.txt`（预录的 playwright 原生错误消息）
- Create: `evals/failure_analysis/test_parse_assertion.py`
- Modify: `assets/conftest_template.py`（追加 `_parse_assertion_from_longrepr`）

- [ ] **Step 1: 准备 fixture（预录真实 pytest longrepr 文本）**

文件 `evals/failure_analysis/fixtures/longrepr_native_assert.txt`（复制 shop-lab-ui-test 实测的小米搜索失败 traceback）：

```
tests/product/test_search.py:55: in test_search_valid_keyword_shows_results
    assert count > 0, f"搜索 '{keyword}' 应返回商品，但结果数为 {count}"
E   AssertionError: 搜索 '小米' 应返回商品，但结果数为 0
E   assert 0 > 0
```

- [ ] **Step 2: 写失败测试**

文件 `evals/failure_analysis/test_parse_assertion.py`：

```python
"""测试 _parse_assertion_from_longrepr。

测试策略：构造 fake report 对象，模拟 pytest 的 ReprExceptionInfo 关键属性。
不直接 mock pytest 内部，因为接口在不同 pytest 版本下会变。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def _load():
    spec = importlib.util.spec_from_file_location(
        "_conftest_under_test",
        Path(__file__).parent.parent.parent / "assets" / "conftest_template.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_conftest_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_fake_longrepr(statement: str, file_loc: str, message: str, longreprtext: str):
    """构造与 pytest ReprExceptionInfo 接口兼容的 fake 对象"""
    reprfileloc = SimpleNamespace(source_line=statement)
    reprcrash = SimpleNamespace(message=message)
    reprtraceback = SimpleNamespace(
        reprentries=[SimpleNamespace(reprfileloc=reprfileloc)]
    )
    return SimpleNamespace(
        reprcrash=reprcrash,
        reprtraceback=reprtraceback,
        longreprtext=longreprtext,
    )


def _build_fake_report(longrepr):
    return SimpleNamespace(longrepr=longrepr, longreprtext=getattr(longrepr, "longreprtext", ""))


def test_native_assert_extraction():
    mod = _load()
    longrepr = _build_fake_longrepr(
        statement='assert count > 0, f"搜索 \'{keyword}\' 应返回商品，但结果数为 {count}"',
        file_loc="tests/product/test_search.py:55",
        message="AssertionError: 搜索 '小米' 应返回商品，但结果数为 0\nassert 0 > 0",
        longreprtext="...",
    )
    report = _build_fake_report(longrepr)
    result = mod._parse_assertion_from_longrepr(report)
    assert result["statement"].startswith("assert count > 0")
    assert result["file"] == "tests/product/test_search.py:55"
    assert "0 > 0" in result["introspection"]
    assert "AssertionError" in result["message"]


def test_longrepr_is_string():
    """setup 阶段失败时 longrepr 可能是字符串"""
    mod = _load()
    report = SimpleNamespace(longrepr="fixture 'foo' not found", longreprtext="fixture 'foo' not found")
    result = mod._parse_assertion_from_longrepr(report)
    assert result["statement"] == ""
    assert result["file"] == ""
    assert "fixture 'foo' not found" in result["message"]


def test_longrepr_without_reprcrash():
    mod = _load()
    longrepr = SimpleNamespace(longreprtext="some error", spec=None)
    longrepr.reprcrash = None  # type: ignore[assignment]
    # longrepr 没有 reprcrash 属性的 fallback
    report = _build_fake_report(longrepr)
    # 模拟 hasattr 链路失败
    delattr(report.longrepr, "reprcrash") if hasattr(report.longrepr, "reprcrash") else None
    result = mod._parse_assertion_from_longrepr(report)
    # 至少能给出 message
    assert "message" in result


def test_empty_longrepr():
    mod = _load()
    report = SimpleNamespace(longrepr=None, longreprtext="")
    result = mod._parse_assertion_from_longrepr(report)
    assert result["statement"] == ""
    assert result["message"] == ""
```

- [ ] **Step 3: 跑测试看失败**

```bash
python3 -m pytest evals/failure_analysis/test_parse_assertion.py -v
```
Expected: FAIL with `AttributeError: ... has no attribute '_parse_assertion_from_longrepr'`

- [ ] **Step 4: 实现**

在 `assets/conftest_template.py` 的 `_extract_rule_from_docstring` 后追加：

```python
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
      - longrepr 是字符串 → 全部字段置空，message = str(longrepr)
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

    # 提取 message（最后一行通常含 ExceptionClass: ...）
    longreprtext = getattr(report, "longreprtext", "") or getattr(longrepr, "longreprtext", "") or ""
    if longreprtext:
        # 取以 'E ' 开头的最后一行（pytest traceback 错误行的标志）
        e_lines = [ln for ln in longreprtext.splitlines() if ln.startswith("E ")]
        if e_lines:
            result["message"] = e_lines[-1][2:].strip()
        else:
            result["message"] = longreprtext.splitlines()[-1] if longreprtext.splitlines() else ""

    # 尝试拿 reprcrash / reprentries（pytest 原生结构）
    reprcrash = getattr(longrepr, "reprcrash", None)
    reprtraceback = getattr(longrepr, "reprtraceback", None)

    if reprcrash is not None:
        msg = getattr(reprcrash, "message", "")
        if msg:
            result["introspection"] = msg
            # 若 message 字段空，用 reprcrash.message 兜底
            if not result["message"]:
                result["message"] = msg.splitlines()[-1] if msg.splitlines() else msg

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
```

- [ ] **Step 5: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_parse_assertion.py -v
```
Expected: PASS (4 个测试)

- [ ] **Step 6: Commit**

```bash
git add evals/failure_analysis/fixtures/longrepr_native_assert.txt evals/failure_analysis/test_parse_assertion.py assets/conftest_template.py
git commit -m "feat(failure-analysis): parse assertion statement + pytest introspection from longrepr"
```

---

