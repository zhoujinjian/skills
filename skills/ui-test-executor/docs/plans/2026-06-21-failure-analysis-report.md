# 失败用例 Markdown 故障分析报告 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `ui-test-executor` skill 新增独立的 `failure_analysis.md` 报告——每条失败用例一节，含判定规则/断言原文/预期 vs 实际/元素校验/截图录屏 Trace 路径；执行后若 report.xml 显示有失败，自动生成。

**Architecture:** 三层结构。conftest hook 在用例失败时落结构化 sidecar JSON（`failure-context/<nodeid>.json`）；新脚本 `generate_failure_analysis.py` 读 JUnit XML 拿失败用例权威列表 + 读 sidecar JSON 拿深度信息 + glob `pytest-raw/<slug>/` 补 video/trace 路径 → 渲染 MD；`execute_tests.py` 在 pytest 进程结束后自动调起新脚本。所有层都有 fallback：sidecar 缺失时退到 JUnit XML，JUnit XML 也读不出细节时只显示 nodeid+message。

**Tech Stack:** Python 3.13 · pytest 9 · pytest-playwright 0.8 · Playwright 1.60 · 纯标准库（json/re/inspect/xml.etree）

**Spec 来源:** `docs/specs/2026-06-21-failure-analysis-report-design.md`

**Git 注意:** 当前 skill 目录不是 git 仓库。每个 Task 的 commit 步骤如下处理：
```bash
# 若已 git init:
git add <files> && git commit -m "..."
# 否则跳过 commit，继续下一 Task
```
若希望全程走 commit 节奏，可先在 skill 根目录 `git init && git add -A && git commit -m "chore: snapshot before failure-analysis"`，本计划默认已做此操作。

---

## File Structure

| 文件 | 动作 | 职责 |
|------|------|------|
| `evals/failure_analysis/__init__.py` | 新增 | 测试包标识 |
| `evals/failure_analysis/test_sanitize_slug.py` | 新增 | TDD: `_sanitize_nodeid_to_slug` 单测 |
| `evals/failure_analysis/test_extract_rule.py` | 新增 | TDD: `_extract_rule_from_docstring` 单测 |
| `evals/failure_analysis/test_parse_assertion.py` | 新增 | TDD: `_parse_assertion_from_longrepr` 单测 |
| `evals/failure_analysis/test_parse_playwright_error.py` | 新增 | TDD: `_parse_playwright_error` 单测 |
| `evals/failure_analysis/test_render_failure_section.py` | 新增 | TDD: MD 章节渲染单测 |
| `evals/failure_analysis/test_fallback_render.py` | 新增 | TDD: sidecar 缺失时降级渲染 |
| `evals/failure_analysis/test_glob_video_trace.py` | 新增 | TDD: video/trace 路径补全 |
| `evals/failure_analysis/fixtures/` | 新增 | 预录的 longrepr / playwright 错误消息文本 |
| `assets/conftest_template.py` | 修改 | 加 5 个新函数 + hook 接线 + PYTEST_RUN_PHASE 处理 |
| `scripts/generate_failure_analysis.py` | 新增 | 主脚本 |
| `scripts/execute_tests.py` | 修改 | 注入 PYTEST_RUN_PHASE + 执行后自动调报告 + --no-failure-analysis |
| `SKILL.md` | 修改 | Step 6 后追加 Step 6.5 |
| `references/failure_report_schema.md` | 新增 | sidecar JSON schema 文档 |
| `references/failure_analysis_guide.md` | 新增 | docstring 约定 + playwright 错误解析规则 |

**为什么这样拆：**
- 解析层（4 个纯函数）和渲染层（render_failure_section）解耦，便于单测
- sidecar 写入（conftest）和 sidecar 读取（generate_failure_analysis）跨进程，靠 JSON schema 解耦，互不读对方代码
- evals 独立目录便于 `pytest evals/failure_analysis/` 单跑

---

## Phase 1：解析层（4 个纯函数 + conftest 集成）

### Task 1: 测试包骨架 + 第一个函数 `_sanitize_nodeid_to_slug`

**Files:**
- Create: `evals/failure_analysis/__init__.py`（空文件）
- Create: `evals/failure_analysis/test_sanitize_slug.py`
- Modify: `assets/conftest_template.py`（在 `_sanitize_filename` 后追加 `_sanitize_nodeid_to_slug`）

- [ ] **Step 1: 创建测试包标识**

```bash
mkdir -p /Users/zhoujinjian/.claude/skills/ui-test-executor/evals/failure_analysis/fixtures
touch /Users/zhoujinjian/.claude/skills/ui-test-executor/evals/failure_analysis/__init__.py
```

- [ ] **Step 2: 写失败测试**

文件 `evals/failure_analysis/test_sanitize_slug.py`：

```python
"""测试 _sanitize_nodeid_to_slug 与 pytest-playwright 0.8.0 的目录命名规则一致。

pytest-playwright 在 --output 目录下为每个失败用例创建子目录，
目录名由 nodeid 经 sanitize 得出。本测试覆盖关键场景：中文参数化值。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_conftest_template():
    """以模块方式加载 conftest_template.py（不执行 pytest 部分）"""
    spec = importlib.util.spec_from_file_location(
        "_conftest_under_test",
        Path(__file__).parent.parent.parent / "assets" / "conftest_template.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_conftest_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_basic_ascii_nodeid():
    mod = _load_conftest_template()
    nodeid = "tests/auth/test_login.py::TestLogin::test_valid_login[chromium]"
    slug = mod._sanitize_nodeid_to_slug(nodeid)
    # 关键断言：与 pytest-playwright 实际产物一致（参考 shop-lab-ui-test 实测目录名）
    assert slug == "tests-auth-test-login-py-testlogin-test-valid-login-chromium"


def test_chinese_param_value():
    """中文参数化值必须转成 uXXXX 形式，否则 glob 匹配失败"""
    mod = _load_conftest_template()
    nodeid = "tests/product/test_search.py::TestSearchPositive::test_search_valid_keyword_shows_results[chromium-小米]"
    slug = mod._sanitize_nodeid_to_slug(nodeid)
    # 「小」= U+5C0F, 「米」= U+7C73
    assert slug == (
        "tests-product-test-search-py-testsearchpositive-"
        "test-search-valid-keyword-shows-results-chromium-u5c0f-u7c73"
    )


def test_multiple_params():
    """多参数化值（如 [chromium-手机-北京]）依次转义"""
    mod = _load_conftest_template()
    nodeid = "tests/test_x.py::TestX::test_t[chromium-手机-北京]"
    slug = mod._sanitize_nodeid_to_slug(nodeid)
    assert slug == "tests-test-x-py-testx-test-t-chromium-u624b-u673a-u5317-u4eac"


def test_no_class_nodeid():
    """无测试类的 nodeid（函数级测试）"""
    mod = _load_conftest_template()
    nodeid = "tests/test_simple.py::test_basic"
    slug = mod._sanitize_nodeid_to_slug(nodeid)
    assert slug == "tests-test-simple-py-test-basic"


def test_collapses_consecutive_dashes():
    """连续分隔符折叠为单个 -"""
    mod = _load_conftest_template()
    nodeid = "tests//double.py::TestX::test_a"
    slug = mod._sanitize_nodeid_to_slug(nodeid)
    # 双斜杠不应产生连续 -
    assert "--" not in slug
```

- [ ] **Step 3: 跑测试看失败**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
python3 -m pytest evals/failure_analysis/test_sanitize_slug.py -v
```
Expected: FAIL with `AttributeError: module '_conftest_under_test' has no attribute '_sanitize_nodeid_to_slug'`

- [ ] **Step 4: 实现 `_sanitize_nodeid_to_slug`**

在 `assets/conftest_template.py` 文件末尾（`pytest_sessionfinish` 函数之后）追加：

```python
def _sanitize_nodeid_to_slug(nodeid: str) -> str:
    """nodeid → pytest-playwright --output 子目录名

    pytest-playwright 0.8.0 的 sanitize 规则（实测对齐）：
      1. '/' → '-'
      2. '::' → '-'（每对冒号折叠为单个 -）
      3. '[' → '-', ']' → ''（参数化方括号展开）
      4. '(' / ')' → '-'
      5. 空格 / '.'（py 文件后缀的 .）→ '-'
      6. 非 ASCII 字符 → 'uXXXX'（4 位 hex 小写，不加下划线）
      7. 连续 '-' 折叠为单个 '-'

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
    # 非 ASCII 字符 → uXXXX（不带上划线，对齐实测）
    s = re.sub(
        r"[-￿]",
        lambda m: f"u{ord(m.group(0)):04x}",
        s,
    )
    # 其他非法字符兜底转 -
    s = re.sub(r"[^A-Za-z0-9_-]", "-", s)
    # 折叠连续 -
    s = re.sub(r"-+", "-", s)
    return s
```

- [ ] **Step 5: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_sanitize_slug.py -v
```
Expected: PASS (5 个测试)

- [ ] **Step 6: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git add evals/failure_analysis/__init__.py evals/failure_analysis/test_sanitize_slug.py assets/conftest_template.py
git commit -m "feat(failure-analysis): add _sanitize_nodeid_to_slug for pytest-playwright dir naming"
```

---

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

### Task 5: `_dump_failure_context` 集成（组装 + 写 JSON）

**Files:**
- Create: `evals/failure_analysis/test_dump_failure_context.py`
- Modify: `assets/conftest_template.py`（追加 `_dump_failure_context` + 修改 `_collect_failure_artifacts` 调用链）

- [ ] **Step 1: 写失败测试**

文件 `evals/failure_analysis/test_dump_failure_context.py`：

```python
"""测试 _dump_failure_context：失败时把所有解析结果组装成 JSON 写到 failure-context/<nodeid>.json。
"""
from __future__ import annotations

import importlib.util
import json
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


def _build_fake_item_and_report(tmp_path, *, phase="main", browser="chromium"):
    """构造 fake pytest Item + TestReport"""
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)

    # 测试函数（带 docstring）
    def fake_test(self, keyword):
        """搜索「{keyword}」应返回至少 1 件商品"""

    item = SimpleNamespace(
        nodeid="tests/test_search.py::TestS::test_search[chromium-小米]",
        func=fake_test,
        funcargs={},
        config=SimpleNamespace(
            getoption=lambda name, default=None: {
                "--artifact-root": str(artifact_root),
            }.get(name, default)
        ),
    )

    # fake report
    longrepr = SimpleNamespace(
        reprcrash=SimpleNamespace(message="AssertionError: ...\nassert 0 > 0"),
        reprtraceback=SimpleNamespace(
            reprentries=[
                SimpleNamespace(
                    reprfileloc=SimpleNamespace(
                        source_line='assert count > 0',
                        path="tests/test_search.py",
                        lineno="55",
                    )
                )
            ]
        ),
        longreprtext="...",
    )
    report = SimpleNamespace(
        nodeid=item.nodeid,
        duration=1.56,
        longrepr=longrepr,
        sections=[],
        failed=True,
        when="call",
    )
    return item, report, artifact_root


def test_dump_writes_json(tmp_path, monkeypatch):
    mod = _load()
    item, report, artifact_root = _build_fake_item_and_report(tmp_path)

    # 把 phase 环境变量准备好
    monkeypatch.setenv("PYTEST_RUN_PHASE", "main")

    mod._dump_failure_context(item, report, browser="chromium", url="http://x/search?q=小", title="搜索")

    sidecar_dir = artifact_root / "failure-context"
    files = list(sidecar_dir.glob("*.json"))
    assert len(files) == 1, f"应只写 1 个 sidecar，实际: {files}"

    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["nodeid"] == item.nodeid
    assert data["phase"] == "main"
    assert data["browser"] == "chromium"
    assert data["url"] == "http://x/search?q=小"
    assert data["title"] == "搜索"
    assert data["duration"] == 1.56
    assert "搜索「小米」" in data["rule"]
    assert data["rule_source"] == "docstring"
    assert data["assertion"]["statement"].startswith("assert count > 0")
    assert data["assertion"]["file"] == "tests/test_search.py:55"
    assert data["expect_failure"]["hint"]  # 推断原因非空
    assert data["slug_hint"]  # slug 已生成
    assert data["pytest_raw_dir"]  # pytest-raw 路径已记录


def test_dump_phase_pre_run(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setenv("PYTEST_RUN_PHASE", "pre-run")
    item, report, artifact_root = _build_fake_item_and_report(tmp_path)
    mod._dump_failure_context(item, report, browser="chromium", url="http://x", title="t")
    sidecar = list((artifact_root / "failure-context").glob("*.json"))[0]
    assert json.loads(sidecar.read_text(encoding="utf-8"))["phase"] == "pre-run"


def test_dump_resilient_to_exception(tmp_path):
    """任何子步骤失败不应让 _dump_failure_context 抛异常（影响主测试流程）"""
    mod = _load()
    # 构造会引发异常的 fake item（inspect.getdoc 拿不到）
    item = SimpleNamespace(
        nodeid="bad/nodeid",
        func=None,  # inspect.getdoc(None) 会返回 None，不抛
        funcargs={},
        config=SimpleNamespace(
            getoption=lambda name, default=None: str(tmp_path / "artifacts") if name == "--artifact-root" else default
        ),
    )
    report = SimpleNamespace(
        nodeid="bad/nodeid",
        duration=0,
        longrepr="something went wrong",
        sections=[],
        failed=True,
        when="call",
    )
    # 不抛 = 通过
    mod._dump_failure_context(item, report, browser="chromium", url="", title="")
```

- [ ] **Step 2: 跑测试看失败**

```bash
python3 -m pytest evals/failure_analysis/test_dump_failure_context.py -v
```
Expected: FAIL with `AttributeError: ... has no attribute '_dump_failure_context'`

- [ ] **Step 3: 实现 `_dump_failure_context`**

在 `assets/conftest_template.py` 的 `_parse_playwright_error` / `_infer_hint` 后追加：

```python
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

        # 3. playwright 错误解析（输入：longreprtext 全文）
        longreprtext = getattr(report, "longreprtext", "") or ""
        try:
            expect_info = _parse_playwright_error(longreprtext)
        except Exception:
            expect_info = {
                "locator": "",
                "expected": "",
                "received": "",
                "action": "",
                "hint": "",
                "raw": longreprtext[:500],
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
```

- [ ] **Step 4: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_dump_failure_context.py -v
```
Expected: PASS (3 个测试)

- [ ] **Step 5: 把 `_dump_failure_context` 接到 `_collect_failure_artifacts`**

修改 `assets/conftest_template.py` 中 `_collect_failure_artifacts` 函数末尾（在 `info_line` 那段之前），追加对 `_dump_failure_context` 的调用。找到：

```python
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
```

替换为：

```python
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
```

- [ ] **Step 6: 跑所有 failure_analysis 测试看通过**

```bash
python3 -m pytest evals/failure_analysis/ -v
```
Expected: PASS（之前 5 个文件的所有测试都过）

- [ ] **Step 7: Commit**

```bash
git add evals/failure_analysis/test_dump_failure_context.py assets/conftest_template.py
git commit -m "feat(failure-analysis): dump structured sidecar JSON on test failure"
```

---

## Phase 2：渲染层（generate_failure_analysis.py）

### Task 6: 脚本骨架 + JUnit XML 解析（复用 generate_report 模式）

**Files:**
- Create: `scripts/generate_failure_analysis.py`

- [ ] **Step 1: 写脚本骨架（仅含 main + XML 解析，渲染留 TODO 占位由后续 Task 实现）**

文件 `scripts/generate_failure_analysis.py`：

```python
#!/usr/bin/env python3
"""
generate_failure_analysis.py — 失败用例 Markdown 故障分析报告生成器

输入:
  - JUnit XML (test-results/report.xml) — 失败用例的权威来源
  - failure-context/<nodeid>.json sidecar — conftest 落的深度信息
  - pytest-raw/<slug>/{video.webm,trace.zip} — pytest-playwright 原生产物

输出:
  - test-results/failure_analysis.md（仅当 ≥1 失败时生成）

降级链：
  sidecar JSON 缺失 → 退化到 JUnit XML 渲染（仅 nodeid+message+traceback）
  JUnit XML 解析失败 → 退出码 2，stderr 报错

用法:
  python3 generate_failure_analysis.py \
      --junit-xml ./test-results/report.xml \
      --artifacts-dir ./test-results/artifacts \
      --output-dir ./test-results
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FailureCase:
    """从 JUnit XML 解析出的失败用例"""
    nodeid: str          # classname::name 拼回（粗略）
    classname: str
    name: str
    file: str = ""
    line: str = ""
    duration: float = 0.0
    message: str = ""
    traceback: str = ""
    sidecar: dict = field(default_factory=dict)  # failure-context/<nodeid>.json 内容（可选）


def parse_junit_failures(xml_path: Path) -> list[FailureCase]:
    """从 JUnit XML 解析所有 failed 用例（含 setup 阶段的 error）

    JUnit XML 结构：
        <testsuite>
          <testcase classname time file line>
            <failure message type>traceback</failure>  # call 阶段失败
            <error message type>traceback</error>      # setup 阶段失败
            <system-out>...</system-out>
          </testcase>
        </testsuite>
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    failures: list[FailureCase] = []
    for tc in root.iter("testcase"):
        # 失败标志：有 <failure> 或 <error> 子节点
        fail_node = tc.find("failure")
        err_node = tc.find("error")
        bad_node = fail_node if fail_node is not None else err_node
        if bad_node is None:
            continue

        # nodeid 拼回：JUnit 把 nodeid 拆成 classname + name
        # 但参数化方括号在 name 里
        classname = tc.attrib.get("classname", "")
        name = tc.attrib.get("name", "")
        nodeid = f"{classname}::{name}" if classname else name

        case = FailureCase(
            nodeid=nodeid,
            classname=classname,
            name=name,
            file=tc.attrib.get("file", ""),
            line=tc.attrib.get("line", ""),
            duration=float(tc.attrib.get("time", "0") or "0"),
            message=bad_node.attrib.get("message", "") or "",
            traceback=(bad_node.text or "").strip(),
        )
        failures.append(case)

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="失败用例 Markdown 故障分析报告生成器")
    parser.add_argument("--junit-xml", required=True, help="JUnit XML 报告路径")
    parser.add_argument("--artifacts-dir", default="./test-results/artifacts", help="artifact 根目录")
    parser.add_argument("--output-dir", default=".", help="MD 输出目录")
    parser.add_argument("--execution-summary", default="", help="执行概述（用于报告头部，如 'P0 and run_smoke · chromium · headless'）")
    args = parser.parse_args(argv)

    junit_path = Path(args.junit_xml).resolve()
    if not junit_path.exists():
        print(f"[ERROR] JUnit XML 不存在: {junit_path}", file=sys.stderr)
        return 2

    failures = parse_junit_failures(junit_path)
    if not failures:
        print(f"[OK] 无失败用例，不生成 failure_analysis.md", file=sys.stderr)
        return 0

    print(f"[INFO] 检测到 {len(failures)} 个失败用例，开始生成 failure_analysis.md", file=sys.stderr)

    # 渲染（Task 7-10 实现）
    md = render_failure_analysis(
        failures=failures,
        artifacts_dir=Path(args.artifacts_dir).resolve(),
        execution_summary=args.execution_summary,
    )

    output_path = Path(args.output_dir).resolve() / "failure_analysis.md"
    output_path.write_text(md, encoding="utf-8")
    print(f"[OK] 已生成 {output_path}", file=sys.stderr)
    return 0


def render_failure_analysis(failures: list[FailureCase], artifacts_dir: Path, execution_summary: str) -> str:
    """渲染完整 MD（Task 7-10 实现）"""
    # 占位，后续 Task 替换
    raise NotImplementedError("render_failure_analysis 由 Task 7-10 实现")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 冒烟测试脚本能跑（用现有 report.xml）**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py \
    --junit-xml test-results/report.xml \
    --artifacts-dir test-results/artifacts \
    --output-dir test-results
```
Expected: `[INFO] 检测到 N 个失败用例...` 然后崩在 `NotImplementedError`（Task 7 会修复）

- [ ] **Step 3: Commit（骨架先入库，后续 Task 渐进实现）**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git add scripts/generate_failure_analysis.py
git commit -m "feat(failure-analysis): scaffold generate_failure_analysis.py with JUnit XML parsing"
```

---

### Task 7: 渲染单条失败用例 MD 章节

**Files:**
- Create: `evals/failure_analysis/test_render_failure_section.py`
- Modify: `scripts/generate_failure_analysis.py`（追加 `render_failure_section` + 实现 `render_failure_analysis`）

- [ ] **Step 1: 写失败测试**

文件 `evals/failure_analysis/test_render_failure_section.py`：

```python
"""测试 render_failure_section：单条失败用例 → MD 章节。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    """加载 generate_failure_analysis.py 作为模块"""
    spec = importlib.util.spec_from_file_location(
        "_gen_failure_analysis",
        Path(__file__).parent.parent.parent / "scripts" / "generate_failure_analysis.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_gen_failure_analysis"] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_sidecar_native_assert():
    return {
        "nodeid": "tests/test_search.py::TestS::test_search[chromium-小米]",
        "slug_hint": "tests-test-search-py-tests-test-search-chromium-u5c0f-u7c73",
        "phase": "main",
        "duration": 1.56,
        "browser": "chromium",
        "url": "http://localhost:3000/search?q=小米",
        "title": "搜索结果",
        "failure_type": "AssertionError",
        "rule": "搜索「小米」应返回至少 1 件商品",
        "rule_source": "docstring",
        "assertion": {
            "statement": 'assert count > 0, f"搜索 \'{keyword}\' 应返回商品"',
            "file": "tests/test_search.py:55",
            "introspection": "assert 0 > 0\ncount = 0\nkeyword = '小米'",
            "message": "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0",
        },
        "expect_failure": {
            "locator": "",
            "expected": "",
            "received": "",
            "action": "",
            "hint": "定位器与实际 DOM class 不匹配（推断，仅作参考）",
            "raw": "AssertionError: ...\nassert 0 > 0\ncount = 0",
        },
        "artifacts": {
            "screenshots": [
                "/tmp/screenshots/x-viewport.png",
                "/tmp/screenshots/x-fullpage.png",
            ],
            "page_source": "/tmp/x.html",
            "console_log": "/tmp/x.log",
        },
        "pytest_raw_dir": "/tmp/pytest-raw",
    }


def test_section_contains_required_sections():
    mod = _load()
    case = mod.FailureCase(
        nodeid="tests/test_search.py::TestS::test_search[chromium-小米]",
        classname="tests.test_search.TestS",
        name="test_search[chromium-小米]",
        file="tests/test_search.py",
        line="55",
        duration=1.56,
        message="AssertionError: ...",
    )
    md = mod.render_failure_section(case, sidecar=_build_sidecar_native_assert(), video_trace={})
    assert "判定规则" in md
    assert "断言原文" in md
    assert "预期 vs 实际" in md
    assert "页面元素校验" in md
    assert "失败截图" in md
    assert "失败录屏与 Trace" in md
    assert "搜索「小米」应返回至少 1 件商品" in md  # rule 出现
    assert "tests/test_search.py:55" in md  # 文件:行号


def test_section_native_assert_renders_empty_locator_row():
    """原生 assert 失败 → locator/expected/received 行显示「未提取」"""
    mod = _load()
    case = mod.FailureCase(
        nodeid="...", classname="...", name="...", duration=1, message="..."
    )
    md = mod.render_failure_section(case, sidecar=_build_sidecar_native_assert(), video_trace={})
    assert "原生 assert" in md or "未提取" in md


def test_section_playwright_expect_renders_locator():
    """playwright expect 失败 → locator/expected/received 行有值"""
    mod = _load()
    sidecar = _build_sidecar_native_assert()
    sidecar["expect_failure"] = {
        "locator": ".product-card",
        "expected": "visible",
        "received": "Timeout 30000ms",
        "action": "to_be_visible",
        "hint": "元素未在超时内出现/可见（推断，仅作参考）",
        "raw": "",
    }
    case = mod.FailureCase(nodeid="...", classname="...", name="...", duration=1, message="...")
    md = mod.render_failure_section(case, sidecar=sidecar, video_trace={})
    assert ".product-card" in md
    assert "visible" in md
    assert "Timeout" in md


def test_section_video_trace_paths_rendered():
    mod = _load()
    case = mod.FailureCase(nodeid="...", classname="...", name="...", duration=1, message="...")
    video_trace = {
        "video": "/tmp/pytest-raw/slug/video.webm",
        "trace": "/tmp/pytest-raw/slug/trace.zip",
    }
    md = mod.render_failure_section(case, sidecar=_build_sidecar_native_assert(), video_trace=video_trace)
    assert "video.webm" in md
    assert "trace.zip" in md
    assert "playwright show-trace" in md


def test_section_video_trace_missing_renders_warning():
    mod = _load()
    case = mod.FailureCase(nodeid="...", classname="...", name="...", duration=1, message="...")
    md = mod.render_failure_section(case, sidecar=_build_sidecar_native_assert(), video_trace={})
    assert "未生成" in md
```

- [ ] **Step 2: 跑测试看失败**

```bash
python3 -m pytest evals/failure_analysis/test_render_failure_section.py -v
```
Expected: FAIL with `AttributeError: ... has no attribute 'render_failure_section'`

- [ ] **Step 3: 实现 `render_failure_section` + 替换 `render_failure_analysis` 占位**

在 `scripts/generate_failure_analysis.py` 文件末尾的 `render_failure_analysis` 占位函数之前，追加 `render_failure_section`：

```python
def _is_playwright_expect_failure(sidecar: dict) -> bool:
    """判断是否 playwright expect 失败（vs 原生 assert 失败）"""
    ef = sidecar.get("expect_failure", {}) or {}
    return any([ef.get("locator"), ef.get("expected"), ef.get("received"), ef.get("action")])


def render_failure_section(case: FailureCase, sidecar: dict, video_trace: dict) -> str:
    """渲染单条失败用例的 MD 章节

    Args:
        case: 从 JUnit XML 解析出的失败用例
        sidecar: failure-context/<nodeid>.json 内容（可能为空 dict = 降级模式）
        video_trace: {"video": str, "trace": str} 路径，空 dict = 未生成

    返回 MD 字符串（不含顶部 ## 标题前的空行；末尾含 ---）
    """
    lines: list[str] = []

    # 章节标题：rule 首行 或 函数名
    title_rule = (sidecar.get("rule") or "").splitlines()[0] if sidecar.get("rule") else case.name
    lines.append(f"## ❌ {title_rule}")
    lines.append("")

    # 元信息行
    phase = sidecar.get("phase", "main")
    duration = sidecar.get("duration") or case.duration
    browser = sidecar.get("browser", "")
    failure_type = sidecar.get("failure_type", "")
    meta_parts = [f"**阶段**: {phase}", f"**耗时**: {duration:.2f}s"]
    if browser:
        meta_parts.append(f"**浏览器**: {browser}")
    if failure_type:
        meta_parts.append(f"**失败类型**: {failure_type}")
    lines.append(f"**位置**: `{case.nodeid}`")
    lines.append(" · ".join(meta_parts))
    lines.append("")

    # 判定规则
    lines.append("### 判定规则")
    rule = sidecar.get("rule", "")
    if rule:
        lines.append(f"> {rule}")
        lines.append("")
        rule_source = sidecar.get("rule_source", "")
        if rule_source == "fallback_funcname":
            lines.append("> 📌 **来源**: 函数名 fallback（无 docstring）")
        elif rule_source == "docstring_unmatched_param":
            lines.append("> 📌 **来源**: docstring（含未匹配的参数化占位符）")
        else:
            lines.append("> 📌 **来源**: 测试 docstring 首行")
        lines.append("")
    else:
        lines.append("> *(无 sidecar，rule 字段缺失，详见断言原文)*")
        lines.append("")

    # 断言原文
    lines.append("### 断言原文")
    assertion = sidecar.get("assertion", {}) or {}
    statement = assertion.get("statement", "")
    file_loc = assertion.get("file", "")
    if statement:
        lines.append("```python")
        if file_loc:
            lines.append(f"# {file_loc}")
        lines.append(statement)
        lines.append("```")
    else:
        lines.append("*(sidecar 缺失或解析失败)*")
    lines.append("")

    # 预期 vs 实际
    lines.append("### 预期 vs 实际（pytest 内省）")
    introspection = assertion.get("introspection", "")
    if introspection:
        lines.append("```")
        lines.append(introspection)
        lines.append("```")
    else:
        lines.append("*(无内省信息)*")
    lines.append("")

    # 页面元素校验
    lines.append("### 页面元素校验")
    ef = sidecar.get("expect_failure", {}) or {}
    url = sidecar.get("url", "") or case.message
    is_pw = _is_playwright_expect_failure(sidecar)
    lines.append("| 字段 | 值 |")
    lines.append("|------|---|")
    lines.append(f"| 失败 URL | `{url}` |")
    if is_pw:
        lines.append(f"| 定位器 | `{ef.get('locator', '')}` |")
        lines.append(f"| 期望 | {ef.get('expected', '')} |")
        lines.append(f"| 实际 | {ef.get('received', '')} |")
    else:
        lines.append("| 定位器 | *(原生 assert，无 playwright 错误结构)* |")
        lines.append("| 期望 | *(原生 assert，未提取)* |")
        lines.append("| 实际 | *(原生 assert，未提取)* |")
    hint = ef.get("hint", "")
    lines.append(f"| 推断原因 | {hint or '（无）'} |")
    lines.append("")
    if not is_pw:
        lines.append("> ⚠️ 本用例是**原生 assert** 失败（非 playwright expect）。")
        lines.append("> 「定位器/期望/实际」仅在 playwright expect 失败时从错误消息结构化提取。")
        lines.append("")
    raw = ef.get("raw", "")
    if raw and not is_pw:
        lines.append("**错误消息原文**：")
        lines.append("```")
        lines.append(raw[:500])
        lines.append("```")
        lines.append("")

    # 失败截图
    lines.append("### 失败截图")
    lines.append("| 类型 | 路径 |")
    lines.append("|------|------|")
    artifacts = sidecar.get("artifacts", {}) or {}
    screenshots = artifacts.get("screenshots", [])
    if isinstance(screenshots, list) and len(screenshots) >= 2:
        lines.append(f"| 视口截图 | `{screenshots[0]}` |")
        lines.append(f"| 全页截图 | `{screenshots[1]}` |")
    elif screenshots:
        for s in screenshots:
            lines.append(f"| 截图 | `{s}` |")
    else:
        lines.append("| 视口截图 | *(未采集)* |")
        lines.append("| 全页截图 | *(未采集)* |")
    # Playwright 原生失败截图（在 pytest-raw/<slug>/test-failed-N.png）
    if video_trace.get("native_screenshot"):
        lines.append(f"| Playwright 原生失败截图 | `{video_trace['native_screenshot']}` |")
    lines.append("")

    # 失败录屏与 Trace
    lines.append("### 失败录屏与 Trace")
    lines.append("| 类型 | 路径 | 复现命令 |")
    lines.append("|------|------|---------|")
    video = video_trace.get("video", "")
    trace = video_trace.get("trace", "")
    if video:
        lines.append(f"| 录屏 | `{video}` | `open {video}` |")
    else:
        lines.append("| 录屏 | *(未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off)* | - |")
    if trace:
        lines.append(f"| Trace | `{trace}` | `python3 -m playwright show-trace {trace}` |")
    else:
        lines.append("| Trace | *(未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off)* | - |")
    lines.append("")

    # 其他诊断材料
    lines.append("### 其他诊断材料")
    page_source = artifacts.get("page_source", "")
    console_log = artifacts.get("console_log", "")
    if page_source:
        lines.append(f"- 页面源码: `{page_source}`")
    if console_log:
        lines.append(f"- Console 日志: `{console_log}`")
    if url:
        lines.append(f"- 失败时 URL: `{url}`")
    lines.append("")

    lines.append("---")
    return "\n".join(lines)
```

然后替换 `render_failure_analysis` 占位实现：

```python
def render_failure_analysis(failures: list[FailureCase], artifacts_dir: Path, execution_summary: str) -> str:
    """渲染完整 MD：顶部总览 + 每条失败用例一节"""
    from datetime import datetime

    lines: list[str] = []

    # 顶部总览
    lines.append("# 失败用例故障分析报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    exec_line = execution_summary or "(未指定)"
    lines.append(f"**测试执行**: {exec_line}")
    lines.append(f"**失败统计**: {len(failures)} 个失败用例")
    lines.append("")
    lines.append("> 本报告由 `ui-test-executor` 自动生成。每条失败用例一节，含判定规则、")
    lines.append("> 断言详情、元素校验、失败截图与录屏路径。Trace 复现命令见每节末尾。")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 每条失败用例
    for i, case in enumerate(failures, 1):
        # 读 sidecar
        sidecar = _load_sidecar(artifacts_dir, case)
        # 补 video/trace
        video_trace = _resolve_video_trace(sidecar)
        # 渲染
        section = render_failure_section(case, sidecar=sidecar, video_trace=video_trace)
        lines.append(section)
        lines.append("")

    return "\n".join(lines)


def _load_sidecar(artifacts_dir: Path, case: FailureCase) -> dict:
    """从 failure-context/<safe_nodeid>.json 读 sidecar；不存在返回空 dict（降级模式）"""
    import re
    safe = re.sub(r"[\[\]\s/\\:]", "-", case.nodeid)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", safe)
    safe = safe[:120]
    sidecar_path = artifacts_dir / "failure-context" / f"{safe}.json"
    if not sidecar_path.exists():
        return {}
    try:
        import json
        return json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_video_trace(sidecar: dict) -> dict:
    """根据 sidecar.slug_hint + sidecar.pytest_raw_dir 补全 video/trace 路径"""
    result: dict[str, str] = {}
    slug = sidecar.get("slug_hint", "")
    pytest_raw_dir = sidecar.get("pytest_raw_dir", "")
    if not slug or not pytest_raw_dir:
        return result

    base = Path(pytest_raw_dir) / slug
    video = base / "video.webm"
    trace = base / "trace.zip"
    # 也找 test-failed-N.png
    if video.exists():
        result["video"] = str(video)
    if trace.exists():
        result["trace"] = str(trace)
    # 找 test-failed-N.png（N=1,2,...）
    failed_pngs = sorted(base.glob("test-failed-*.png"))
    if failed_pngs:
        result["native_screenshot"] = str(failed_pngs[0])

    return result
```

- [ ] **Step 4: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_render_failure_section.py -v
```
Expected: PASS (5 个测试)

- [ ] **Step 5: 端到端冒烟（用现有 shop-lab-ui-test 的 report.xml）**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py \
    --junit-xml test-results/report.xml \
    --artifacts-dir test-results/artifacts \
    --output-dir test-results \
    --execution-summary "P0 and run_smoke · chromium · headless"
cat test-results/failure_analysis.md | head -80
```
Expected: 看到 MD 报告，每条失败用例一节，含判定规则/断言原文/截图路径

- [ ] **Step 6: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git add evals/failure_analysis/test_render_failure_section.py scripts/generate_failure_analysis.py
git commit -m "feat(failure-analysis): render per-failure MD section with rule/assertion/artifacts"
```

---

### Task 8: 降级渲染（sidecar JSON 缺失时）

**Files:**
- Create: `evals/failure_analysis/test_fallback_render.py`
- Modify: `scripts/generate_failure_analysis.py`（`render_failure_section` 接受空 sidecar）

- [ ] **Step 1: 写失败测试**

文件 `evals/failure_analysis/test_fallback_render.py`：

```python
"""测试 sidecar JSON 缺失时的降级渲染。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    spec = importlib.util.spec_from_file_location(
        "_gen_failure_analysis",
        Path(__file__).parent.parent.parent / "scripts" / "generate_failure_analysis.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_gen_failure_analysis"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_empty_sidecar_still_renders():
    """sidecar = {} → 仍然能渲染一个 MD 章节，不抛"""
    mod = _load()
    case = mod.FailureCase(
        nodeid="tests/test_x.py::TestX::test_a",
        classname="tests.test_x.TestX",
        name="test_a",
        file="tests/test_x.py",
        line="10",
        duration=2.3,
        message="AssertionError: expected 5 got 3",
        traceback="traceback...",
    )
    md = mod.render_failure_section(case, sidecar={}, video_trace={})
    assert "test_a" in md  # 标题 fallback 到函数名
    assert "expected 5 got 3" in md  # message 出现
    assert "判定规则" in md  # 章节骨架仍在
    assert "未采集" in md or "未生成" in md  # 截图/录屏提示


def test_no_sidecar_section_has_warning():
    """sidecar 缺失时章节顶部应有提示（可选，断言 sidecar 来源标注）"""
    mod = _load()
    case = mod.FailureCase(nodeid="x", classname="c", name="n", duration=1, message="m")
    md = mod.render_failure_section(case, sidecar={}, video_trace={})
    assert "无 sidecar" in md or "rule 字段缺失" in md
```

- [ ] **Step 2: 跑测试看失败**

```bash
python3 -m pytest evals/failure_analysis/test_fallback_render.py -v
```
Expected: 取决于 Task 7 实现，可能部分通过部分失败。若失败，调整 render_failure_section。

- [ ] **Step 3: 如有失败，修正 render_failure_section**

Task 7 的实现已经处理空 sidecar（`sidecar.get("rule", "")` 等都返回空），所以测试应该已通过。若不过，检查：
- `title_rule` 在 rule 为空时是否 fallback 到 `case.name`
- 截图/录屏路径是否在 sidecar 为空时显示"未采集"

如确实需修，修 Task 7 的 `render_failure_section` 函数对应分支。

- [ ] **Step 4: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_fallback_render.py -v
```
Expected: PASS (2 个测试)

- [ ] **Step 5: Commit**

```bash
git add evals/failure_analysis/test_fallback_render.py scripts/generate_failure_analysis.py
git commit -m "test(failure-analysis): fallback render when sidecar JSON missing"
```

---

### Task 9: video/trace 路径补全的 slug 容错

**Files:**
- Create: `evals/failure_analysis/test_glob_video_trace.py`
- Modify: `scripts/generate_failure_analysis.py`（强化 `_resolve_video_trace` 多候选处理）

- [ ] **Step 1: 写失败测试**

文件 `evals/failure_analysis/test_glob_video_trace.py`：

```python
"""测试 _resolve_video_trace：slug 不匹配时的 glob fallback + 多候选警告。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    spec = importlib.util.spec_from_file_location(
        "_gen_failure_analysis",
        Path(__file__).parent.parent.parent / "scripts" / "generate_failure_analysis.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_gen_failure_analysis"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_exact_slug_match(tmp_path):
    mod = _load()
    pytest_raw = tmp_path / "pytest-raw"
    slug = "tests-test-x-py-testx-test-a-chromium"
    (pytest_raw / slug).mkdir(parents=True)
    (pytest_raw / slug / "video.webm").write_bytes(b"fake")
    (pytest_raw / slug / "trace.zip").write_bytes(b"fake")
    sidecar = {"slug_hint": slug, "pytest_raw_dir": str(pytest_raw)}
    result = mod._resolve_video_trace(sidecar)
    assert result["video"].endswith("video.webm")
    assert result["trace"].endswith("trace.zip")


def test_no_matching_slug_returns_empty(tmp_path):
    mod = _load()
    sidecar = {"slug_hint": "does-not-exist", "pytest_raw_dir": str(tmp_path / "pytest-raw")}
    result = mod._resolve_video_trace(sidecar)
    assert result == {} or "video" not in result


def test_glob_fallback_when_slug_mismatch(tmp_path):
    """slug 完全不匹配，但 pytest-raw 下只有一个目录 → glob fallback 命中"""
    mod = _load()
    pytest_raw = tmp_path / "pytest-raw"
    slug_actual = "different-slug-actual"
    (pytest_raw / slug_actual).mkdir(parents=True)
    (pytest_raw / slug_actual / "video.webm").write_bytes(b"fake")
    sidecar = {"slug_hint": "different-slug-expected", "pytest_raw_dir": str(pytest_raw)}
    result = mod._resolve_video_trace(sidecar)
    # glob fallback：pytest-raw 下唯一目录被选中
    assert "video" in result


def test_multiple_candidates_warning(tmp_path):
    """pytest-raw 下多个目录都无法精确匹配 → 不静默选一个，返回空 + 警告字段"""
    mod = _load()
    pytest_raw = tmp_path / "pytest-raw"
    for s in ["slug-a", "slug-b"]:
        (pytest_raw / s).mkdir(parents=True)
        (pytest_raw / s / "video.webm").write_bytes(b"fake")
    sidecar = {"slug_hint": "slug-c", "pytest_raw_dir": str(pytest_raw)}
    result = mod._resolve_video_trace(sidecar)
    # 多候选时不应贸然选
    assert "video" not in result
    assert result.get("warning") or result.get("_multi_candidate")  # 警告标志
```

- [ ] **Step 2: 跑测试看失败**

```bash
python3 -m pytest evals/failure_analysis/test_glob_video_trace.py -v
```
Expected: 部分失败（Task 7 的实现只做了精确匹配）

- [ ] **Step 3: 强化 `_resolve_video_trace`**

替换 `scripts/generate_failure_analysis.py` 的 `_resolve_video_trace`：

```python
def _resolve_video_trace(sidecar: dict) -> dict:
    """根据 sidecar.slug_hint + sidecar.pytest_raw_dir 补全 video/trace 路径

    匹配策略（按优先级）:
      1. 精确匹配：<pytest_raw_dir>/<slug>/ 存在 → 直接用
      2. glob fallback：pytest-raw 下唯一目录 → 用唯一目录（容错 slug 转义差异）
      3. 多候选：pytest-raw 下多个目录 → 不选，返回 warning

    返回:
        {"video": str, "trace": str, "native_screenshot": str} 中任意子集
        多候选时追加 "_multi_candidate": True
    """
    result: dict[str, object] = {}
    slug = sidecar.get("slug_hint", "")
    pytest_raw_dir = sidecar.get("pytest_raw_dir", "")
    if not pytest_raw_dir:
        return result

    raw_root = Path(pytest_raw_dir)
    if not raw_root.exists():
        return result

    # 1. 精确匹配
    candidate_dirs: list[Path] = []
    if slug:
        exact = raw_root / slug
        if exact.exists() and exact.is_dir():
            candidate_dirs = [exact]

    # 2. fallback：列所有子目录
    if not candidate_dirs:
        all_dirs = [d for d in raw_root.iterdir() if d.is_dir()]
        if len(all_dirs) == 1:
            candidate_dirs = all_dirs
        elif len(all_dirs) > 1 and slug:
            # 尝试按 slug 的前缀匹配（容错 unicode 转义差异）
            slug_lower = slug.lower()
            prefix_matches = [d for d in all_dirs if d.name.lower().startswith(slug_lower[:30])]
            if len(prefix_matches) == 1:
                candidate_dirs = prefix_matches
            else:
                # 多候选不选
                result["_multi_candidate"] = True
                return result

    if not candidate_dirs:
        return result

    base = candidate_dirs[0]
    video = base / "video.webm"
    trace = base / "trace.zip"
    if video.exists():
        result["video"] = str(video)
    if trace.exists():
        result["trace"] = str(trace)
    failed_pngs = sorted(base.glob("test-failed-*.png"))
    if failed_pngs:
        result["native_screenshot"] = str(failed_pngs[0])

    return result
```

并在 `render_failure_section` 里，对 `_multi_candidate` 做出渲染反应。修改 video_trace 表格段（找到 `# 失败录屏与 Trace` 部分）：

把：
```python
    if video:
        lines.append(f"| 录屏 | `{video}` | `open {video}` |")
    else:
        lines.append("| 录屏 | *(未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off)* | - |")
```

改成：
```python
    if video:
        lines.append(f"| 录屏 | `{video}` | `open {video}` |")
    elif video_trace.get("_multi_candidate"):
        lines.append("| 录屏 | ⚠️ 多个候选目录匹配，请人工确认 | - |")
    else:
        lines.append("| 录屏 | *(未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off)* | - |")
```

trace 行同理。

- [ ] **Step 4: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_glob_video_trace.py -v
```
Expected: PASS (4 个测试)

- [ ] **Step 5: 跑全部 failure_analysis 测试确认无回归**

```bash
python3 -m pytest evals/failure_analysis/ -v
```
Expected: 所有测试 PASS

- [ ] **Step 6: Commit**

```bash
git add evals/failure_analysis/test_glob_video_trace.py scripts/generate_failure_analysis.py
git commit -m "feat(failure-analysis): resilient video/trace glob with multi-candidate warning"
```

---

## Phase 3：集成层（execute_tests.py）

### Task 10: 注入 PYTEST_RUN_PHASE 环境变量

**Files:**
- Modify: `scripts/execute_tests.py`（`run_pytest` 传 env，`main` 注入 phase）

- [ ] **Step 1: 修改 `run_pytest` 让它接收 phase 并注入环境变量**

打开 `scripts/execute_tests.py`，找到 `def run_pytest(pytest_args, cwd, dry_run=False, label="MAIN")` 函数签名（约 397 行），改为：

```python
def run_pytest(pytest_args: list[str], cwd: str, dry_run: bool = False, label: str = "MAIN", phase: str = "main") -> int:
    """执行 pytest 命令，实时流式输出

    label 用于在日志中区分"前置阶段"和"主测试"（如 --pre-run vs 主筛选集）
    phase 注入到子进程环境变量 PYTEST_RUN_PHASE，供 conftest 写 sidecar 时区分阶段
    """
```

在 `subprocess.Popen` 调用（约 422 行）前加：

```python
    env = os.environ.copy()
    env["PYTEST_RUN_PHASE"] = phase
```

然后修改 `subprocess.Popen(cmd, cwd=cwd, stdout=..., stderr=..., text=True, bufsize=1, universal_newlines=True)` 调用，追加 `env=env`：

```python
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env,
        )
```

- [ ] **Step 2: 修改 `main` 调用处**

找到 main 函数末尾（约 711-718 行）：

```python
    if pre_pytest_args:
        pre_exit = run_pytest(pre_pytest_args, cwd=cwd, label="PRE-RUN")
        if pre_exit not in (0, 1):
            # 0=全过 / 1=有失败（仍允许继续主测试）/ 其他=异常
            print(f"[PRE-RUN] 前置阶段异常退出（exit={pre_exit}），终止后续执行", file=sys.stderr)
            return pre_exit

    main_exit = run_pytest(main_pytest_args, cwd=cwd, label="MAIN")
    return main_exit
```

改为：

```python
    if pre_pytest_args:
        pre_exit = run_pytest(pre_pytest_args, cwd=cwd, label="PRE-RUN", phase="pre-run")
        if pre_exit not in (0, 1):
            print(f"[PRE-RUN] 前置阶段异常退出（exit={pre_exit}），终止后续执行", file=sys.stderr)
            return pre_exit

    main_exit = run_pytest(main_pytest_args, cwd=cwd, label="MAIN", phase="main")
    return main_exit
```

- [ ] **Step 3: 手动验证 phase 注入生效**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
python3 -c "
import subprocess, os
env = os.environ.copy()
env['PYTEST_RUN_PHASE'] = 'test'
result = subprocess.run(
    ['python3', '-c', 'import os; print(\"PHASE=\", os.environ.get(\"PYTEST_RUN_PHASE\"))'],
    env=env, capture_output=True, text=True
)
print(result.stdout)
"
```
Expected: 输出 `PHASE= test`（确认 env 传递机制）

- [ ] **Step 4: 跑 execute_tests 的现有 evals 看无回归**

```bash
# 用 --dry-run 不实际跑测试，只看命令构建
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
    --priority P0 --tags run_smoke --browser chromium --base-url=http://localhost:3000 \
    --dry-run
```
Expected: 正常输出构建的命令，无 traceback

- [ ] **Step 5: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git add scripts/execute_tests.py
git commit -m "feat(failure-analysis): inject PYTEST_RUN_PHASE env to subprocess for conftest sidecar"
```

---

### Task 11: 执行后自动调 generate_failure_analysis.py + `--no-failure-analysis` 开关

**Files:**
- Modify: `scripts/execute_tests.py`（`main` 末尾追加自动调用 + CLI 加开关）

- [ ] **Step 1: 加 CLI 开关**

找到 `parse_args` 函数末尾（约 574 行 `--dry-run` 之后），追加：

```python
    # ============ 失败报告 ============
    parser.add_argument(
        "--no-failure-analysis",
        dest="no_failure_analysis",
        action="store_true",
        help="关闭自动生成 failure_analysis.md（默认开启：有失败时自动生成）",
    )
```

- [ ] **Step 2: 在 `main` 函数末尾追加自动调用**

把 Task 10 修改后的 main 函数末尾段：

```python
    main_exit = run_pytest(main_pytest_args, cwd=cwd, label="MAIN", phase="main")
    return main_exit
```

改为：

```python
    main_exit = run_pytest(main_pytest_args, cwd=cwd, label="MAIN", phase="main")

    # 自动生成 failure_analysis.md（仅当有失败且未显式关闭）
    if not args.no_failure_analysis and not args.dry_run and not args.list_only:
        _maybe_generate_failure_analysis(output_dir, args, main_exit)

    return main_exit
```

并在文件末尾（`if __name__ == "__main__":` 之前）追加新函数：

```python
def _maybe_generate_failure_analysis(output_dir: Path, args: argparse.Namespace, main_exit: int) -> None:
    """执行后自动生成 failure_analysis.md（若 report.xml 显示有失败）

    - 找不到 generate_failure_analysis.py → 跳过（脚本缺失不应阻塞主流程）
    - 脚本本身崩溃 → 仅打印 [WARN]，不改 execute_tests.py 退出码
    """
    report_xml = output_dir / "report.xml"
    if not report_xml.exists():
        return

    # 先扫 JUnit XML 看有没有失败
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(report_xml)
        root = tree.getroot()
        failures = sum(int(ts.attrib.get("failures", "0")) for ts in root.iter("testsuite"))
        errors = sum(int(ts.attrib.get("errors", "0")) for ts in root.iter("testsuite"))
        if failures == 0 and errors == 0:
            return
    except Exception:
        # XML 解析失败 → 仍然尝试调脚本，让脚本自己报错
        pass

    script = Path(__file__).parent / "generate_failure_analysis.py"
    if not script.exists():
        return

    # 构造执行概述（写到报告头部）
    summary_parts = []
    if args.priority or args.tags or args.marker_expr:
        m_expr = build_marker_expression(args.tags, args.modules, args.priority, args.marker_expr)
        if m_expr:
            summary_parts.append(m_expr)
    if args.browser:
        summary_parts.append("+".join(args.browser))
    summary_parts.append("headless" if args.headless else "headed")
    exec_summary = " · ".join(summary_parts) if summary_parts else "(未指定)"

    cmd = [
        sys.executable,
        str(script),
        "--junit-xml", str(report_xml),
        "--artifacts-dir", str(output_dir / "artifacts"),
        "--output-dir", str(output_dir),
        "--execution-summary", exec_summary,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode not in (0,):
            print(f"[WARN] generate_failure_analysis.py 退出码 {result.returncode}", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] failure_analysis 生成失败: {e}", file=sys.stderr)
```

- [ ] **Step 3: 端到端验证（用 shop-lab-ui-test 跑一次完整流程）**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
rm -rf test-results
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
    -m "P0 and run_smoke" \
    --browser chromium \
    --base-url=http://localhost:3000 \
    --output-dir ./test-results
echo "---"
ls test-results/
echo "---"
head -40 test-results/failure_analysis.md 2>/dev/null || echo "failure_analysis.md 未生成（全过）"
```
Expected: 执行完测试后自动生成 failure_analysis.md（若有失败）；日志里能看到 `[OK] 已生成 .../failure_analysis.md`

- [ ] **Step 4: 验证 `--no-failure-analysis` 开关**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
rm -rf test-results
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
    -m "P0 and run_smoke" \
    --browser chromium \
    --base-url=http://localhost:3000 \
    --output-dir ./test-results \
    --no-failure-analysis
ls test-results/failure_analysis.md 2>&1 || echo "OK: --no-failure-analysis 生效，未生成 failure_analysis.md"
```
Expected: 不生成 failure_analysis.md

- [ ] **Step 5: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git add scripts/execute_tests.py
git commit -m "feat(failure-analysis): auto-invoke generate_failure_analysis after execute; add --no-failure-analysis"
```

---

## Phase 4：文档与端到端验证

### Task 12: references/failure_report_schema.md

**Files:**
- Create: `references/failure_report_schema.md`

- [ ] **Step 1: 写文档**

文件 `references/failure_report_schema.md`：

````markdown
# failure-context sidecar JSON Schema

每个失败用例生成一份 sidecar JSON，路径：`<artifact-root>/failure-context/<safe_nodeid>.json`

## 字段说明

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| `nodeid` | string | ✅ | pytest | 失败用例完整 nodeid（含参数化方括号） |
| `slug_hint` | string | ✅ | conftest `_sanitize_nodeid_to_slug` | nodeid 转 pytest-playwright 目录名格式，供 glob 匹配 |
| `phase` | string | ✅ | 环境变量 `PYTEST_RUN_PHASE` | `main` / `pre-run` |
| `duration` | float | ✅ | pytest `report.duration` | 用例耗时秒 |
| `browser` | string | ✅ | `page.context.browser.browser_type.name` | chromium / firefox / webkit |
| `url` | string | ✅ | `page.url` | 失败时页面 URL |
| `title` | string | ✅ | `page.title()` | 失败时页面标题（可能为空） |
| `failure_type` | string | ✅ | `assertion.message` 解析 | Exception 类名（如 AssertionError） |
| `rule` | string | ✅ | docstring 首行（含参数化占位替换） | 判定规则 |
| `rule_source` | string | ✅ | docstring 提取过程 | `docstring` / `fallback_funcname` / `docstring_unmatched_param` / `no_test_func` |
| `assertion` | object | ✅ | 见下 | 断言解析 |
| `expect_failure` | object | ✅ | 见下 | playwright 错误解析 |
| `artifacts` | object | ✅ | 见下 | 已采集 artifact 路径 |
| `pytest_raw_dir` | string | ✅ | execute_tests 透传 | pytest-playwright `--output` 目录 |
| `dumped_at` | string | ✅ | `datetime.now().isoformat()` | 写入时间 |

### `assertion` 子字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `statement` | string | assert 语句原文（带 message 字面值） |
| `file` | string | `文件:行号` |
| `introspection` | string | pytest 原生 introspection（含局部变量值） |
| `message` | string | 错误消息（ExceptionClass: msg） |

### `expect_failure` 子字段

| 字段 | 类型 | playwright expect 失败 | 原生 assert 失败 |
|------|------|------------------------|------------------|
| `locator` | string | 由正则提取 | 空 |
| `expected` | string | 由正则提取 | 空 |
| `received` | string | 由正则提取 | 空 |
| `action` | string | 由正则提取（如 `to_be_visible`） | 空 |
| `hint` | string | 关键词匹配得出 | 关键词匹配得出 |
| `raw` | string | 空 | 整段错误消息原文 |

判断逻辑：4 个结构化字段至少命中 1 个 → playwright expect 失败；全未命中 → 原生 assert 失败。

### `artifacts` 子字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `screenshots` | string[2] | 视口截图 + 全页截图绝对路径 |
| `page_source` | string | DOM 快照 HTML 路径 |
| `console_log` | string | console 日志合并文件路径 |

注：`video.webm` / `trace.zip` 不在此字段内，由 `generate_failure_analysis.py` 用 `slug_hint` + `pytest_raw_dir` 在渲染时 glob 补全。

## 示例

```json
{
  "nodeid": "tests/product/test_search.py::TestSearchPositive::test_search_valid_keyword_shows_results[chromium-小米]",
  "slug_hint": "tests-product-test-search-py-testsearchpositive-test-search-valid-keyword-shows-results-chromium-u5c0f-u7c73",
  "phase": "main",
  "duration": 1.56,
  "browser": "chromium",
  "url": "http://localhost:3000/search?q=小米",
  "title": "搜索结果",
  "failure_type": "AssertionError",
  "rule": "搜索「小米」应返回至少 1 件商品",
  "rule_source": "docstring",
  "assertion": {
    "statement": "assert count > 0",
    "file": "tests/product/test_search.py:55",
    "introspection": "assert 0 > 0\ncount = 0",
    "message": "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0"
  },
  "expect_failure": {
    "locator": "",
    "expected": "",
    "received": "",
    "action": "",
    "hint": "定位器与实际 DOM class 不匹配（推断，仅作参考）",
    "raw": "..."
  },
  "artifacts": {
    "screenshots": [".../viewport.png", ".../fullpage.png"],
    "page_source": ".../...html",
    "console_log": ".../...log"
  },
  "pytest_raw_dir": "/abs/path/test-results/artifacts/pytest-raw",
  "dumped_at": "2026-06-21T14:32:00"
}
```
````

- [ ] **Step 2: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git add references/failure_report_schema.md
git commit -m "docs(failure-analysis): sidecar JSON schema reference"
```

---

### Task 13: references/failure_analysis_guide.md

**Files:**
- Create: `references/failure_analysis_guide.md`

- [ ] **Step 1: 写文档**

文件 `references/failure_analysis_guide.md`：

````markdown
# 失败分析报告使用指南

## 给测试编写者的约定

### 1. docstring 写判定规则（弱约定）

每个测试函数第一行 docstring 会被提取为「判定规则」：

```python
@pytest.mark.parametrize("keyword", ["手机", "小米", "手表"])
def test_search_valid_keyword_shows_results(self, authed_page, keyword):
    """搜索「{keyword}」应返回至少 1 件商品"""
    ...
```

报告里渲染为：

> ### 判定规则
> > 搜索「小米」应返回至少 1 件商品

**约定细节**：

- 第一行即规则，多行 docstring 只取首行
- 含 `{param}` 占位符时，用 nodeid 末尾参数化值替换（去掉 chromium/firefox/webkit 引擎段）
- 无 docstring → fallback 到测试函数名做人类化转换，标注 `fallback_funcname`
- 含占位符但 nodeid 无参数化 → 标注 `docstring_unmatched_param`

### 2. 用 playwright expect 提升报告密度

playwright expect 失败时（如 `expect(loc).to_be_visible()`），错误消息有结构化字段，报告会自动填充：

| 字段 | 例 |
|------|---|
| 定位器 | `.product-card` |
| 期望 | visible |
| 实际 | Timeout 30000ms |
| 推断原因 | 元素未在超时内出现/可见 |

原生 `assert` 失败时（如 `assert count > 0`），这些字段为空，只展示断言原文 + pytest introspection。

**写测试时的取舍**：
- 用 `expect(loc).to_have_count(n)` 比 `assert loc.count() == n` 报告更丰富
- 但不要为了报告字段把所有 assert 改成 expect——只在断言确实是"页面元素状态"时用 expect

### 3. 推断原因（hint）

报告里「推断原因」字段基于关键词匹配，**仅作参考**，不是 AI 智能诊断：

| 触发模式 | 推断 |
|----------|------|
| Protocol error + navigate | URL/base_url 配置问题 |
| Timeout + Locator 已知 | 元素未在超时内出现/可见 |
| Expected ≠ Received | 文案变更 |
| count = 0 类断言 + locator 已知 | 定位器与实际 DOM class 不匹配 |

---

## 给运维 / CI 的约定

### 1. failure_analysis.md 生成时机

- 仅当 `report.xml` 显示 ≥1 失败时生成
- 全通过 → 不生成（文件不存在 = 跑绿）
- 由 `execute_tests.py` 在 pytest 进程结束后自动调起
- 可用 `--no-failure-analysis` 关闭

### 2. 降级行为

| 失败点 | 渲染 |
|--------|------|
| conftest hook 异常未写 sidecar | 退到 JUnit XML 渲染（nodeid + message + traceback） |
| sidecar JSON 损坏 | 同上 |
| video/trace 文件未生成 | 显示「（未生成，可能此用例未失败到 call 阶段）」 |
| video/trace 多候选目录 | 显示「⚠️ 多个候选目录匹配，请人工确认」 |

### 3. 手动重新生成

```bash
python3 <skill_dir>/scripts/generate_failure_analysis.py \
    --junit-xml test-results/report.xml \
    --artifacts-dir test-results/artifacts \
    --output-dir test-results \
    --execution-summary "P0 and run_smoke · chromium · headless"
```

### 4. playwright 错误消息解析失败时

`_parse_playwright_error` 的 4 个正则全没命中 → 报告里「定位器/期望/实际」字段为空，raw 字段保留整段错误消息原文。

如果你用的是较新版本的 playwright（错误消息格式有变），需要更新 `assets/conftest_template.py` 里 `_PW_PATTERNS` 字典。

---

## 常见问题

### Q1: 报告里 rule 字段显示「fallback_funcname」

A: 测试函数没写 docstring，或 docstring 是空的。给测试函数加一行 docstring 即可。

### Q2: 截图/录屏路径显示「（未采集）」

A: 可能原因：
1. 用例在 setup 阶段失败（page 还没初始化）
2. conftest hook 未集成到项目的 `tests/conftest.py`（参考 SKILL.md Step 5）
3. execute_tests.py 未传 `--artifact-root`

### Q3: video/trace 显示「多个候选目录匹配」

A: `pytest-raw/` 下有多个相似 slug 的目录，脚本无法自动选。打开 `pytest-raw/` 看 目录列表，确认哪个是当前失败用例的，手动用 `playwright show-trace` 打开。
````

- [ ] **Step 2: Commit**

```bash
git add references/failure_analysis_guide.md
git commit -m "docs(failure-analysis): user-facing guide for docstring convention + degradation"
```

---

### Task 14: SKILL.md 追加 Step 6.5

**Files:**
- Modify: `SKILL.md`（在 Step 6 后、Step 7 前追加 Step 6.5）

- [ ] **Step 1: 找到追加位置**

`SKILL.md` 中 Step 6 结尾（约 354 行 `pytest-raw/` 行后）、Step 7 开始（355 行 `### Step 7：解读结果并给建议` 前）。

- [ ] **Step 2: 插入 Step 6.5**

把：

```markdown
| `test-results/artifacts/pytest-raw/` | pytest-playwright 原生产物（video.webm / trace.zip / test-failed-N.png，仅失败用例） |

### Step 7：解读结果并给建议
```

改为：

```markdown
| `test-results/artifacts/pytest-raw/` | pytest-playwright 原生产物（video.webm / trace.zip / test-failed-N.png，仅失败用例） |

### Step 6.5：自动生成失败用例深度报告

`execute_tests.py` 在 pytest 进程结束后，若 `report.xml` 显示有失败用例，**自动调用** `generate_failure_analysis.py` 生成 `test-results/failure_analysis.md`，无需任何额外参数。

```bash
# 自动触发（默认）
python3 execute_tests.py tests/ --priority P0 --tags run_smoke --browser chromium

# 关闭自动触发
python3 execute_tests.py tests/ --priority P0 --no-failure-analysis

# 手动重新生成（不重跑测试）
python3 generate_failure_analysis.py \
    --junit-xml ./test-results/report.xml \
    --artifacts-dir ./test-results/artifacts \
    --output-dir ./test-results
```

**failure_analysis.md vs summary.md 的区别：**

| 报告 | 字段密度 | 触发条件 | 用途 |
|------|---------|---------|------|
| `summary.md` | 低（概览统计 + 简要失败明细） | 每次 | CI 看板、流水线摘要 |
| `failure_analysis.md` | 高（每条失败一节，含 rule/assertion/playwright 字段/artifact 路径） | 仅 ≥1 失败时 | 深度故障诊断 |

**failure_analysis.md 每条失败用例包含：**

1. 判定规则（docstring 首行，含参数化占位替换）
2. 断言原文（带文件:行号）
3. 预期 vs 实际（pytest 原生 introspection）
4. 页面元素校验（locator / expected / received / 推断原因）
5. 失败截图路径（视口 + 全页 + Playwright 原生）
6. 失败录屏与 Trace 路径（含 `playwright show-trace` 复现命令）
7. 其他诊断材料（page-source / console-log / 失败时 URL）

**降级行为**（保证永远能产出 MD）：

- conftest 未集成 / sidecar 缺失 → 退到 JUnit XML 渲染（nodeid + message + traceback）
- video/trace 未生成 → 显示「（未生成）」提示
- slug 匹配多候选 → 显示「⚠️ 请人工确认」警告

详见：
- 设计文档：`docs/specs/2026-06-21-failure-analysis-report-design.md`
- Schema：`references/failure_report_schema.md`
- 使用指南：`references/failure_analysis_guide.md`

### Step 7：解读结果并给建议
```

- [ ] **Step 3: 检查 Markdown 渲染（用任意 markdown linter 或 GitHub preview）**

```bash
# 简单检查标题层级
grep -nE "^### Step" /Users/zhoujinjian/.claude/skills/ui-test-executor/SKILL.md
```
Expected: 看到 `Step 0` / `Step 1` ... / `Step 6` / `Step 6.5` / `Step 7` 完整序列

- [ ] **Step 4: Commit**

```bash
git add SKILL.md
git commit -m "docs(failure-analysis): add Step 6.5 auto failure_analysis generation"
```

---

### Task 15: 端到端验证（故意失败的测试 + 完整流程跑通）

**Files:**
- 临时修改（验证完恢复）：`/Users/zhoujinjian/ai_project/shop-lab-ui-test/tests/product/test_search.py`

- [ ] **Step 1: 备份并故意改坏一个断言**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
cp tests/product/test_search.py tests/product/test_search.py.bak
# 把「手机」关键字断言改成必然失败的（手机本来是过的，改成要求返回 999 个）
sed -i.bak2 's/assert count > 0, f"搜索/assert count > 999, f"搜索/' tests/product/test_search.py
# 复原 sed 没成功的话手动改；确认改了
grep -n "assert count" tests/product/test_search.py
```
Expected: 看到 `assert count > 999, f"搜索..."`

- [ ] **Step 2: 完整流程跑通**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
rm -rf test-results
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
    -m "P0 and run_smoke" \
    --browser chromium \
    --base-url=http://localhost:3000 \
    --output-dir ./test-results
```
Expected: 测试跑完，stderr 显示 `[INFO] 检测到 1 个失败用例` 和 `[OK] 已生成 .../failure_analysis.md`

- [ ] **Step 3: 检查 failure_analysis.md 内容**

```bash
cat test-results/failure_analysis.md | head -100
```
Expected 检查项：
- 顶部总览含执行概述
- 每条失败用例有 `## ❌` 标题
- 判定规则段含 docstring 提取
- 断言原文含 `assert count > 999`
- 预期 vs 实际含 `assert 0 > 999` 或类似 introspection
- 截图路径指向实际存在的文件
- Trace 路径含 `playwright show-trace` 命令

- [ ] **Step 4: 验证 artifact 路径真实存在**

```bash
ls test-results/artifacts/failure-context/
ls test-results/artifacts/screenshots/ | head -5
find test-results/artifacts/pytest-raw -name "trace.zip" | head -5
```
Expected: sidecar JSON / screenshots / trace.zip 文件都真实存在，且路径与 MD 报告里写的一致

- [ ] **Step 5: 恢复测试文件**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
mv tests/product/test_search.py.bak tests/product/test_search.py
rm -f tests/product/test_search.py.bak2
grep -n "assert count" tests/product/test_search.py
```
Expected: 断言恢复为 `assert count > 0`

- [ ] **Step 6: Commit（这次 commit 是 skill 自身的最终汇总，端到端通过）**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git log --oneline | head -15  # 看本计划的所有 commit 是否齐全
```
Expected: 看到 Task 1-14 的 commit 序列

无需新 commit（本 Task 只做端到端验证）。

---

## Self-Review

**1. Spec coverage（逐节核对）：**

| Spec 节 | 覆盖 Task |
|---------|----------|
| 1.2 目标字段表（rule/assertion/expect_failure/artifact 路径/Trace 命令） | Task 1-7 |
| 3.1 目录结构（failure-context/） | Task 5 |
| 3.2 数据流（conftest → sidecar → generate_failure_analysis → MD） | Task 5-7, 10-11 |
| 3.3 文件清单 | Task 1-14 全覆盖 |
| 4.1 MD 报告模板 | Task 7 |
| 4.2.1 docstring 提取规则 | Task 2 |
| 4.2.2 断言原文提取 | Task 3 |
| 4.2.3 playwright 错误解析 + hint | Task 4 |
| 4.2.4 artifact 路径聚合 + slug 规则 | Task 1, 7, 9 |
| 4.2.5 phase 注入 | Task 10 |
| 4.3 JSON sidecar schema | Task 5（实现）+ Task 12（文档） |
| 5 错误处理与降级 | Task 5, 8, 9 |
| 6 测试策略（3 个核心单测） | Task 2（docstring）+ Task 4（playwright 解析）+ Task 8（降级） |
| 后续 spec 钩子（能力 2/3） | 不需 Task，已在 spec 标注 |

✅ 全覆盖

**2. Placeholder scan：**

通读所有 Task，无 TBD/TODO/"implement later"/"add appropriate error handling" 等占位。每个步骤的代码块都是完整可运行的。

**3. Type consistency：**

- `_sanitize_nodeid_to_slug(nodeid: str) -> str` — Task 1 定义，Task 5 调用 ✓
- `_extract_rule_from_docstring(test_func, nodeid: str) -> dict` — Task 2 定义，Task 5 调用 ✓
- `_parse_assertion_from_longrepr(report) -> dict` — Task 3 定义，Task 5 调用 ✓
- `_parse_playwright_error(text: str) -> dict` — Task 4 定义，Task 5 调用 ✓
- `_dump_failure_context(item, report, *, browser, url, title) -> None` — Task 5 定义 ✓
- `render_failure_section(case, sidecar, video_trace) -> str` — Task 7 定义，Task 8/9 用 ✓
- `render_failure_analysis(failures, artifacts_dir, execution_summary) -> str` — Task 6 定义骨架，Task 7 实现 ✓
- `_resolve_video_trace(sidecar) -> dict` — Task 7 初版，Task 9 强化 ✓
- `_load_sidecar(artifacts_dir, case) -> dict` — Task 7 定义 ✓
- `FailureCase` dataclass — Task 6 定义，Task 7-9 用 ✓
- `run_pytest(pytest_args, cwd, dry_run, label, phase)` — Task 10 改签名 ✓
- `_maybe_generate_failure_analysis(output_dir, args, main_exit) -> None` — Task 11 定义 ✓

✅ 一致

**4. 跨 Task 引用一致性：**

- Task 5 步骤 5 修改 `_collect_failure_artifacts`，依赖 Task 1-4 的函数已定义在 conftest_template.py ✓
- Task 7 步骤 3 修改 `render_failure_analysis`，依赖 Task 6 骨架已定义 ✓
- Task 9 修改 `_resolve_video_trace` + `render_failure_section` video 表格段，引用 Task 7 已写代码 ✓
- Task 11 修改 `main` + 加 `_maybe_generate_failure_analysis`，引用 Task 10 的 `phase` 参数 ✓

✅ 无悬空引用

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-06-21-failure-analysis-report.md`. Two execution options:

**1. Subagent-Driven (recommended)** — 我（主 Claude）dispatch 一个 fresh subagent 跑每个 Task，每个 Task 完成后我做 code review，再起下一个。适合：希望每步都有审查、不想让 plan 执行污染主上下文。

**2. Inline Execution** — 我在当前会话里按 Task 顺序跑，每个 Phase 后停下来给你 review checkpoint。适合：希望连续执行少打断。

请选一种。
