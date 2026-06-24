### Task 2: `_extract_rule_from_docstring`（含参数化占位替换）

**Files:**
- Create: `evals/failure_analysis/test_extract_rule.py`
- Modify: `assets/conftest_template.py`（追加 `_extract_rule_from_docstring`）

- [ ] **Step 1: 写失败测试**

文件 `evals/failure_analysis/test_extract_rule.py`：

```python
"""测试 _extract_rule_from_docstring。

约定：测试函数 docstring 首行作为「判定规则」。
若 docstring 含 {param} 占位符，用 nodeid 末尾参数化值替换
（去掉第一个 chromium/firefox/webkit 引擎段）。
无 docstring → fallback 到函数名做人类化转换，rule_source = "fallback_funcname"。
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


def test_docstring_first_line():
    mod = _load()

    def fake_test(self, keyword):
        """搜索「{keyword}」应返回至少 1 件商品"""

    result = mod._extract_rule_from_docstring(
        fake_test,
        "tests/test_search.py::TestS::test_search[chromium-小米]",
    )
    assert result["rule"] == "搜索「小米」应返回至少 1 件商品"
    assert result["rule_source"] == "docstring"


def test_docstring_without_placeholder():
    mod = _load()

    def fake_test(self):
        """登录成功后应跳转到首页"""

    result = mod._extract_rule_from_docstring(
        fake_test,
        "tests/test_login.py::TestL::test_login",
    )
    assert result["rule"] == "登录成功后应跳转到首页"
    assert result["rule_source"] == "docstring"


def test_docstring_multiple_placeholders():
    """多个占位符按 nodeid 中括号内顺序（去掉引擎段）依次填入"""
    mod = _load()

    def fake_test(self, browser, region, keyword):
        """搜索 {keyword}（区域：{region}）"""

    result = mod._extract_rule_from_docstring(
        fake_test,
        "tests/test_search.py::TestS::test_t[chromium-华北-手机]",
    )
    assert result["rule"] == "搜索 手机（区域：华北）"


def test_no_docstring_fallback_to_funcname():
    mod = _load()

    def fake_test_valid_login_redirects_to_home(self):
        pass  # 无 docstring

    result = mod._extract_rule_from_docstring(
        fake_test,
        "tests/test_login.py::TestL::test_test_valid_login_redirects_to_home",
    )
    # fallback：test_ 前缀去掉 + 下划线转空格
    assert "valid login redirects to home" in result["rule"].lower()
    assert result["rule_source"] == "fallback_funcname"


def test_placeholder_without_param_match():
    """docstring 含 {param} 但 nodeid 无参数化 → 占位符保留并标注"""
    mod = _load()

    def fake_test(self):
        """用户 {name} 应能登录"""

    result = mod._extract_rule_from_docstring(
        fake_test,
        "tests/test_login.py::TestL::test_login",
    )
    assert "{name}" in result["rule"]
    assert "未匹配" in result["rule_source"] or result["rule_source"] == "docstring_unmatched_param"


def test_docstring_multiline_takes_first_line():
    mod = _load()

    def fake_test(self):
        """首行判定规则。

        详细描述......
        """

    result = mod._extract_rule_from_docstring(
        fake_test,
        "tests/test_login.py::TestL::test_t",
    )
    assert result["rule"] == "首行判定规则。"
```

- [ ] **Step 2: 跑测试看失败**

```bash
python3 -m pytest evals/failure_analysis/test_extract_rule.py -v
```
Expected: FAIL with `AttributeError: ... has no attribute '_extract_rule_from_docstring'`

- [ ] **Step 3: 实现**

在 `assets/conftest_template.py` 的 `_sanitize_nodeid_to_slug` 后追加：

```python
import inspect as _inspect


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

    # 占位符替换
    import re as _re

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
```

- [ ] **Step 4: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_extract_rule.py -v
```
Expected: PASS (6 个测试)

- [ ] **Step 5: Commit**

```bash
git add evals/failure_analysis/test_extract_rule.py assets/conftest_template.py
git commit -m "feat(failure-analysis): extract rule from test docstring with param substitution"
```

---

