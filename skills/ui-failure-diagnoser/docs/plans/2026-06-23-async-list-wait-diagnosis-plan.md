# 异步加载等待缺失故障诊断（两阶段）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 ui-failure-diagnoser 增加「搜索正向断言 0 结果 → missing_async_list_wait」的自动诊断 + AST 修复能力，并支持 verify 失败时升级为 assertion_mismatch。

**Architecture:** 不新增 category；在 SCRIPT_ERROR 下细分两个子根因。信号三点 AND 匹配（搜索 + 期望>0 + 实际=0），自动排除负向断言。AST 在 `get_product_count()` 首行插入 `self._wait_for_product_list_loaded()` 调用，同步在 `base_page.py` 注入 helper。verify 失败时 rollback 并把根因升级为 `assertion_mismatch`，仅报告。

**Tech Stack:** Python 3.10+、标准库 ast/re/dataclasses、pytest（evals）、Playwright（项目侧）

**Spec:** `docs/specs/2026-06-23-async-list-wait-diagnosis-design.md`

---

## File Structure

| 文件 | 责任 | 改动类型 |
|---|---|---|
| `scripts/locate_root_cause.py` | 根因定位 | 修改：SCRIPT_ERROR 分支接入新函数 |
| `scripts/apply_fix.py` | AST 修复 | 追加：`apply_async_wait_fix()` + 两个内部 helper |
| `scripts/diagnose.py` | 主编排 | 修改：`_apply_deterministic_fix` 加分支 + `_verify_and_maybe_rollback` 升级 + `DiagnosisRecord` 字段 + `generate_report` / `_render_record` |
| `evals/core/test_locate_root_cause.py` | 根因测试 | 追加：4 个 SCRIPT_ERROR 子根因测试 |
| `evals/core/test_apply_fix.py` | AST 测试 | 追加：3 个 `apply_async_wait_fix` 测试 |
| `evals/core/test_diagnose.py` | 集成测试 | 追加：2 个两阶段流程测试 |
| `SKILL.md` | Skill 文档 | 修改：根因表 12→14，新增两阶段流程章节 |
| `references/fix_strategies.md` | 修复策略参考 | 追加：missing_async_list_wait + assertion_mismatch 章节 |

---

## Task 1: 信号匹配 — locate_root_cause.py 新增 SCRIPT_ERROR 细分

**Files:**
- Modify: `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/locate_root_cause.py:88-95`（替换 SCRIPT_ERROR 分支）+ 文件末尾追加新函数
- Test: `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/evals/core/test_locate_root_cause.py`（文件末尾追加）

- [ ] **Step 1.1: 写失败测试（4 个场景）**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/evals/core/test_locate_root_cause.py` 末尾追加：

```python
# ============ 扩展：SCRIPT_ERROR 子根因 ============

def test_script_error_search_zero_assertion_classified_as_missing_async_wait():
    """搜索正向断言 + 0 结果 → missing_async_list_wait."""
    cf = type("CF", (), {
        "category": "SCRIPT_ERROR",
        "locator_hint": None,
        "nodeid": "tests/x.py::t1",
        "raw_message": "AssertionError: 搜索 '手表' 应返回商品，但结果数为 0",
    })()
    r = locate(cf)
    assert r is not None
    assert r.root_cause == "missing_async_list_wait"
    assert r.fix_strategy == "ast_rewrite"


def test_script_error_search_negative_assertion_not_matched():
    """搜索负向断言（应 0 实际 N）→ 仍走 script_error_unspecified."""
    cf = type("CF", (), {
        "category": "SCRIPT_ERROR",
        "locator_hint": None,
        "nodeid": "tests/x.py::t1",
        "raw_message": "AssertionError: 搜索 '飞机' 应无结果，但返回 3 个商品",
    })()
    r = locate(cf)
    assert r is not None
    assert r.root_cause == "script_error_unspecified"


def test_script_error_non_search_assertion_not_matched():
    """非搜索场景的 AssertionError → 仍走 script_error_unspecified."""
    cf = type("CF", (), {
        "category": "SCRIPT_ERROR",
        "locator_hint": None,
        "nodeid": "tests/x.py::t1",
        "raw_message": "AssertionError: 购物车商品数应为 0",
    })()
    r = locate(cf)
    assert r.root_cause == "script_error_unspecified"


def test_script_error_english_search_zero_matched():
    """英文搜索 0 结果 → 也命中（跨项目支持）."""
    cf = type("CF", (), {
        "category": "SCRIPT_ERROR",
        "locator_hint": None,
        "nodeid": "tests/x.py::t1",
        "raw_message": "AssertionError: search 'watch' should return items, count is 0",
    })()
    r = locate(cf)
    assert r.root_cause == "missing_async_list_wait"
```

- [ ] **Step 1.2: 跑测试看失败**

Run:
```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  /usr/local/bin/python3.13 -m pytest evals/core/test_locate_root_cause.py -k "script_error" -v
```

Expected: 4 FAIL，原因 `assert r.root_cause == "missing_async_list_wait"` 失败（当前返回 `script_error_unspecified`）。

- [ ] **Step 1.3: 修改 locate_root_cause.py 主入口的 SCRIPT_ERROR 分支**

把 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/locate_root_cause.py:88-95` 的 SCRIPT_ERROR 块：

```python
    # SCRIPT_ERROR：交给 _apply_category_repair 处理，locate 只打 tag
    if category == "SCRIPT_ERROR":
        return RootCause(
            root_cause="script_error_unspecified",
            fix_strategy="category_repair",
            evidence={"message": message},
        )
```

替换为：

```python
    # SCRIPT_ERROR：细分 missing_async_list_wait / script_error_unspecified
    if category == "SCRIPT_ERROR":
        return _locate_script_error(classified_failure)
```

- [ ] **Step 1.4: 在 locate_root_cause.py 文件末尾追加新函数**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/locate_root_cause.py` 末尾追加：

```python


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
```

- [ ] **Step 1.5: 跑测试看通过**

Run:
```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  /usr/local/bin/python3.13 -m pytest evals/core/test_locate_root_cause.py -v
```

Expected: 所有测试 PASS（原有的 + 新增 4 个）。

- [ ] **Step 1.6: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  git add scripts/locate_root_cause.py evals/core/test_locate_root_cause.py && \
  git commit -m "feat(diagnoser): add missing_async_list_wait root cause for SCRIPT_ERROR

Search-zero-result assertions (e.g., '搜索 X 应返回商品，但结果数为 0')
now classify as missing_async_list_wait (fix_strategy=ast_rewrite)
instead of falling through to script_error_unspecified.

Three-point AND signal matching:
- SEARCH_CONTEXT (搜索/search/查询/检索)
- POSITIVE_EXPECTATION (应返回/应为/should return/expected)
- ZERO_ACTUAL (结果数为 0/count is 0/returned 0)

Negative assertions ('应无结果，但返回 N') auto-rejected: ZERO_ACTUAL
doesn't match 'N'."
```

---

## Task 2: AST 修复 — apply_fix.py 新增 apply_async_wait_fix

**Files:**
- Modify: `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/apply_fix.py`（末尾追加新函数 + 模块 docstring 更新）
- Test: `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/evals/core/test_apply_fix.py`（末尾追加）

- [ ] **Step 2.1: 写失败测试（3 个场景：插入 / 幂等 / 备份）**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/evals/core/test_apply_fix.py` 顶部 import 块追加 `apply_async_wait_fix`：

```python
from apply_fix import (
    apply_insufficient_wait_fix,
    apply_iframe_switch_fix,
    apply_method_typo_fix,
    apply_deprecated_api_fix,
    apply_async_wait_fix,
    suggest_method_correction,
    DEPRECATED_API_MAPPING,
    generate_patch,
    FixResult,
)
```

在文件末尾追加测试：

```python


# ============ apply_async_wait_fix: 异步列表加载等待 ============

def test_async_wait_inserts_call_in_get_product_count(tmp_path):
    """get_product_count 方法体首行插入 self._wait_for_product_list_loaded() 调用."""
    src = _write(tmp_path, "search_result_page.py", """
        from pages.base_page import BasePage
        class SearchResultPage(BasePage):
            def get_product_count(self) -> int:
                return self._product_cards.count()
    """)
    base = _write(tmp_path, "base_page.py", """
        class BasePage:
            def __init__(self, page):
                self.page = page
    """)
    result = apply_async_wait_fix(
        source_path=src, base_page_path=base, dry_run=False,
    )
    assert result.modified is True
    # source 文件：在 return 之前插入了 wait 调用
    assert "self._wait_for_product_list_loaded()" in result.new_source
    assert result.new_source.index("self._wait_for_product_list_loaded()") < \
           result.new_source.index("self._product_cards.count()")
    # base_page：追加了 helper 方法定义
    base_new = base.read_text()
    assert "def _wait_for_product_list_loaded(self" in base_new
    assert "wait_for_load_state" in base_new


def test_async_wait_idempotent_when_already_inserted(tmp_path):
    """幂等：方法首行已是 self._wait_for_* 时跳过."""
    src = _write(tmp_path, "search_result_page.py", """
        from pages.base_page import BasePage
        class SearchResultPage(BasePage):
            def get_product_count(self) -> int:
                self._wait_for_product_list_loaded()
                return self._product_cards.count()
    """)
    base = _write(tmp_path, "base_page.py", """
        class BasePage:
            def _wait_for_product_list_loaded(self):
                pass
    """)
    result = apply_async_wait_fix(
        source_path=src, base_page_path=base, dry_run=False,
    )
    assert result.modified is False


def test_async_wait_creates_bak(tmp_path):
    """backup=True 时 source 文件写 .bak（base_page 不写 .bak）."""
    src = _write(tmp_path, "search_result_page.py", """
        from pages.base_page import BasePage
        class SearchResultPage(BasePage):
            def get_product_count(self) -> int:
                return self._product_cards.count()
    """)
    base = _write(tmp_path, "base_page.py", "class BasePage: pass\n")
    apply_async_wait_fix(
        source_path=src, base_page_path=base, backup=True,
    )
    assert src.with_suffix(".py.bak").exists()
    assert "return self._product_cards.count()" in \
           src.with_suffix(".py.bak").read_text()
```

- [ ] **Step 2.2: 跑测试看失败**

Run:
```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  /usr/local/bin/python3.13 -m pytest evals/core/test_apply_fix.py -k "async_wait" -v
```

Expected: 3 FAIL，原因 `ImportError: cannot import name 'apply_async_wait_fix'`。

- [ ] **Step 2.3: 更新 apply_fix.py 模块 docstring**

把 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/apply_fix.py:1-15` 的 docstring：

```python
"""apply_fix.py — AST rewrite 确定性修复

仅对 pages/**/*.py（page 对象层）做修改，不动 tests/**.**。

修复策略:
    insufficient_wait      timeout=N → timeout=max(N*3, 30000)
    missing_iframe_switch  page.locator(X) → page.frame_locator(...).locator(X)
    method_typo            .clcik( → .click(（基于 AttributeError 智能提示）
    deprecated_api         .query_selector( → .locator(（Playwright 已弃用 API）

安全保证:
    - 默认 backup=True，原文件写 .bak
    - dry_run=True 时不写文件、不写 .bak
    - AST 级修改，保留代码格式（不重新格式化整个文件）
"""
```

替换为：

```python
"""apply_fix.py — AST rewrite 确定性修复

仅对 pages/**/*.py（page 对象层）做修改，不动 tests/**.**。

修复策略:
    insufficient_wait      timeout=N → timeout=max(N*3, 30000)
    missing_iframe_switch  page.locator(X) → page.frame_locator(...).locator(X)
    method_typo            .clcik( → .click(（基于 AttributeError 智能提示）
    deprecated_api         .query_selector( → .locator(（Playwright 已弃用 API）
    async_wait             在 list-getter 方法首行插入 _wait_for_product_list_loaded()
                           + base_page.py 注入 helper（修复异步加载导致 count=0 误报）

安全保证:
    - 默认 backup=True，原文件写 .bak
    - dry_run=True 时不写文件、不写 .bak
    - AST 级修改，保留代码格式（不重新格式化整个文件）
"""
```

- [ ] **Step 2.4: 在 apply_fix.py 文件末尾追加实现**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/apply_fix.py` 末尾追加：

```python


# ============ async_wait 修复（missing_async_list_wait）============

_ASYNC_WAIT_HELPER_TEMPLATE = '''
    def _wait_for_product_list_loaded(self, timeout_ms: int = 10000) -> None:
        """等商品列表首屏渲染完成。

        修复异步加载导致 get_product_count() 立即返回 0 的误报。
        策略：先等 networkidle（请求完结），再等常见商品 selector 出现至少 1 个元素。
        失败不抛异常，让后续 count/assert 揭示真实状态。
        """
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass
        try:
            self.page.wait_for_function(
                """() => {
                    const sels = ['.product-card', '.goods-card', '.search-result-item',
                                  '.item-card', '[data-product-id]', '.product-item'];
                    return sels.some(s => document.querySelectorAll(s).length > 0);
                }""",
                timeout=timeout_ms,
            )
        except Exception:
            pass
'''


def apply_async_wait_fix(
    source_path: Path,
    base_page_path: Path,
    method_name: str = "get_product_count",
    helper_name: str = "_wait_for_product_list_loaded",
    backup: bool = True,
    dry_run: bool = False,
) -> FixResult:
    """在 page object 的 list-getter 方法首行插入 self.<helper_name>() 调用，
    并在 base_page.py 追加 helper 方法定义。

    触发：SCRIPT_ERROR + 搜索正向断言 0 结果（missing_async_list_wait）。

    Args:
        source_path: pages/**/*.py，含 `def <method_name>(self)`
        base_page_path: pages/base_page.py，BasePage 类所在
        method_name: 要插入 wait 的方法名（默认 get_product_count）
        helper_name: wait helper 方法名（默认 _wait_for_product_list_loaded）
    """
    old_source = source_path.read_text(encoding="utf-8")

    method_modified, new_source = _insert_wait_call(
        old_source, method_name, helper_name,
    )

    base_old = base_page_path.read_text(encoding="utf-8") if base_page_path.exists() else ""
    base_modified = False
    new_base = base_old
    if f"def {helper_name}(" not in base_old:
        new_base = _append_helper_to_base_page(base_old)
        base_modified = True

    if not method_modified and not base_modified:
        return FixResult(modified=False, new_source=old_source)

    patch = generate_patch(source_path, old_source, new_source)

    backup_path: Path | None = None
    if not dry_run:
        if backup:
            backup_path = source_path.with_suffix(source_path.suffix + ".bak")
            shutil.copy2(source_path, backup_path)
        source_path.write_text(new_source, encoding="utf-8")
        if base_modified:
            base_page_path.write_text(new_base, encoding="utf-8")

    return FixResult(
        modified=True, new_source=new_source,
        backup_path=backup_path, patch=patch,
    )


def _insert_wait_call(
    source: str, method_name: str, helper_name: str,
) -> tuple[bool, str]:
    """在 `def <method_name>(self)` 方法体首行插入 self.<helper_name>() 调用。

    Returns:
        (modified, new_source)
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False, source

    target_method: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            target_method = node
            break

    if target_method is None:
        return False, source

    body = target_method.body
    # 幂等：方法体首行已是 self.<helper_name>() 或 self._wait_for_*() → 跳过
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Call):
        call = body[0].value
        if (isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "self"
                and (call.func.attr == helper_name
                     or call.func.attr.startswith("_wait_for_"))):
            return False, source

    # 插入位置：方法体首条语句之前（同行缩进）
    first_stmt = body[0]
    insert_lineno = first_stmt.lineno
    lines = source.splitlines(keepends=True)
    line = lines[insert_lineno - 1]
    indent = line[:len(line) - len(line.lstrip())]

    wait_line = f"{indent}self.{helper_name}()\n"
    lines.insert(insert_lineno - 1, wait_line)

    return True, "".join(lines)


def _append_helper_to_base_page(source: str) -> str:
    """在 BasePage 类末尾追加 _wait_for_product_list_loaded 方法定义。

    简化策略：AST 找 BasePage 类，在类最后一条语句后插入模板。
    若解析失败 / 无 BasePage 类，追加到文件末尾（best-effort）。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source + "\n" + _ASYNC_WAIT_HELPER_TEMPLATE + "\n"

    base_class: ast.ClassDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "BasePage":
            base_class = node
            break

    if base_class is None:
        return source + "\n" + _ASYNC_WAIT_HELPER_TEMPLATE + "\n"

    last_stmt = base_class.body[-1]
    end_lineno = last_stmt.end_lineno or len(source.splitlines())

    lines = source.splitlines(keepends=True)
    lines.insert(end_lineno, _ASYNC_WAIT_HELPER_TEMPLATE + "\n")

    return "".join(lines)
```

- [ ] **Step 2.5: 跑测试看通过**

Run:
```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  /usr/local/bin/python3.13 -m pytest evals/core/test_apply_fix.py -k "async_wait" -v
```

Expected: 3 PASS。

- [ ] **Step 2.6: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  git add scripts/apply_fix.py evals/core/test_apply_fix.py && \
  git commit -m "feat(apply_fix): add apply_async_wait_fix for missing_async_list_wait

Inserts self._wait_for_product_list_loaded() as first statement of
get_product_count(), and injects the helper method into BasePage if
not already present.

Idempotent: skips when method body already starts with self._wait_for_*.
Helper uses networkidle + 6 common product selectors (best-effort,
failure-tolerant)."
```

---

## Task 3: diagnose.py — _apply_deterministic_fix 接入 missing_async_list_wait

**Files:**
- Modify: `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/diagnose.py:29-36`（import 块）+ `:421-437`（`_apply_deterministic_fix` 末尾追加分支）
- Test: `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/evals/core/test_diagnose.py`（末尾追加）

- [ ] **Step 3.1: 写失败测试（root_cause=missing_async_list_wait 时调起 apply_async_wait_fix）**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/evals/core/test_diagnose.py` 末尾追加：

```python


# ============ missing_async_list_wait: AST 修复派发 ============

def test_apply_deterministic_fix_dispatches_async_wait_for_missing_async_list_wait(tmp_path):
    """root_cause=missing_async_list_wait 时调起 apply_async_wait_fix 修改 get_product_count."""
    # 构造 pages/ 结构
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "product").mkdir()
    (pages_dir / "product" / "search_result_page.py").write_text(textwrap.dedent("""
        from pages.base_page import BasePage
        class SearchResultPage(BasePage):
            def get_product_count(self) -> int:
                return self._product_cards.count()
    """))
    (pages_dir / "base_page.py").write_text(textwrap.dedent("""
        class BasePage:
            def __init__(self, page):
                self.page = page
    """))

    # 构造 record，root_cause 已是 missing_async_list_wait
    from apply_fix import FixResult
    from dataclasses import dataclass
    from pathlib import Path as PathCls

    rc = type("RC", (), {
        "root_cause": "missing_async_list_wait",
        "fix_strategy": "ast_rewrite",
        "evidence": {},
    })()
    failure = diagnose.FailureRecord(
        nodeid="tests/x.py::t", classname="x", testname="t",
        message="AssertionError: 搜索 '手表' 应返回商品，但结果数为 0",
        traceback="",
    )
    record = diagnose.DiagnosisRecord(failure=failure)
    record.root_cause = rc

    diagnose._apply_deterministic_fix(
        record=record, pages_dir=pages_dir, dry_run=False,
    )

    assert record.fix_applied is not None
    assert record.fix_applied.modified is True
    assert "_wait_for_product_list_loaded" in record.fix_applied.new_source
    # base_page 也应该被注入 helper
    assert "_wait_for_product_list_loaded" in \
           (pages_dir / "base_page.py").read_text()
```

- [ ] **Step 3.2: 跑测试看失败**

Run:
```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  /usr/local/bin/python3.13 -m pytest evals/core/test_diagnose.py -k "async_wait" -v
```

Expected: FAIL，原因 `assert record.fix_applied.modified is True` 失败（当前 `_apply_deterministic_fix` 没有 missing_async_list_wait 分支，record.fix_applied 保持 None）。

- [ ] **Step 3.3: 在 diagnose.py import 块加 apply_async_wait_fix**

把 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/diagnose.py:29-36` 的 import：

```python
from apply_fix import (  # noqa: E402
    apply_deprecated_api_fix,
    apply_iframe_switch_fix,
    apply_insufficient_wait_fix,
    apply_method_typo_fix,
    rollback,
    suggest_method_correction,
)
```

替换为：

```python
from apply_fix import (  # noqa: E402
    apply_async_wait_fix,
    apply_deprecated_api_fix,
    apply_iframe_switch_fix,
    apply_insufficient_wait_fix,
    apply_method_typo_fix,
    rollback,
    suggest_method_correction,
)
```

- [ ] **Step 3.4: 在 _apply_deterministic_fix 末尾追加 missing_async_list_wait 分支**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/diagnose.py` 的 `_apply_deterministic_fix` 函数中（`missing_iframe_switch` 分支之后、函数结束之前），追加：

```python
    elif rc.root_cause == "missing_async_list_wait":
        # 找含 def get_product_count 的 page 文件
        candidates = find_files_with_pattern(pages_dir, "def get_product_count")
        if not candidates:
            return
        target = candidates[0]
        # 找 base_page.py（class BasePage 所在文件）
        base_candidates = find_files_with_pattern(pages_dir, "class BasePage")
        if not base_candidates:
            return
        base_page = base_candidates[0]
        record.fix_target_file = target
        record.fix_applied = apply_async_wait_fix(
            source_path=target,
            base_page_path=base_page,
            dry_run=dry_run,
        )
```

定位提示：找到 `elif rc.root_cause == "missing_iframe_switch":` 块结束的位置（即 `apply_iframe_switch_fix(...)` 调用结束、函数 def 之前的最后一行），在它之后追加这个 elif。

- [ ] **Step 3.5: 跑测试看通过**

Run:
```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  /usr/local/bin/python3.13 -m pytest evals/core/test_diagnose.py -v
```

Expected: 所有测试 PASS（原有 + 新增）。

- [ ] **Step 3.6: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  git add scripts/diagnose.py evals/core/test_diagnose.py && \
  git commit -m "feat(diagnose): dispatch apply_async_wait_fix for missing_async_list_wait

Locates pages/**/search_result_page.py via 'def get_product_count'
pattern, locates base_page.py via 'class BasePage', and calls
apply_async_wait_fix to insert wait helper + base_page method."
```

---

## Task 4: DiagnosisRecord 字段 + _verify_and_maybe_rollback 升级逻辑

**Files:**
- Modify: `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/diagnose.py:48-71`（DiagnosisRecord dataclass）+ `:621-643`（`_verify_and_maybe_rollback` 函数）
- Test: `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/evals/core/test_diagnose.py`（末尾追加）

- [ ] **Step 4.1: 写失败测试（verify 失败 + missing_async_list_wait → 升级 + rollback）**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/evals/core/test_diagnose.py` 末尾追加：

```python


# ============ Stage 2: verify 失败升级为 assertion_mismatch ============

def test_verify_failure_with_missing_async_list_wait_upgrades_to_assertion_mismatch(tmp_path):
    """missing_async_list_wait 修复后 verify 失败 → 升级为 assertion_mismatch + rollback."""
    from unittest import mock
    from apply_fix import FixResult

    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    src_file = pages_dir / "search_result_page.py"
    src_file.write_text(textwrap.dedent("""
        class SearchResultPage:
            def get_product_count(self):
                return self._product_cards.count()
    """))
    base_file = pages_dir / "base_page.py"
    base_file.write_text("class BasePage: pass\n")

    # 预先应用修复（直接走 apply_async_wait_fix）
    fix_result = diagnose.apply_async_wait_fix(
        source_path=src_file, base_page_path=base_file, backup=True,
    )
    assert fix_result.modified

    rc = type("RC", (), {
        "root_cause": "missing_async_list_wait",
        "fix_strategy": "ast_rewrite",
        "evidence": {},
    })()
    failure = diagnose.FailureRecord(
        nodeid="tests/x.py::t", classname="x", testname="t",
        message="AssertionError: 搜索 '手表' 应返回商品，但结果数为 0",
        traceback="",
    )
    record = diagnose.DiagnosisRecord(failure=failure)
    record.root_cause = rc
    record.fix_applied = fix_result
    record.fix_target_file = src_file

    # mock verify_single_test 返回 failed
    fake_verify = mock.Mock()
    fake_verify.status = "failed"
    fake_verify.duration_sec = 1.5

    with mock.patch.object(diagnose, "verify_single_test", return_value=fake_verify):
        diagnose._verify_and_maybe_rollback(
            record=record,
            project_dir=tmp_path,
            base_url=None,
            browser=None,
        )

    # 升级字段已设置
    assert record.upgraded_root_cause == "assertion_mismatch"
    assert record.upgrade_reason is not None
    assert "排查后端" in record.upgrade_reason or "异步加载" in record.upgrade_reason
    # rollback 已执行
    assert record.rolled_back is True
    # source 文件已恢复
    assert "_wait_for_product_list_loaded()" not in src_file.read_text()


def test_verify_failure_with_other_root_cause_does_not_upgrade(tmp_path):
    """非 missing_async_list_wait 的修复 verify 失败 → 只 rollback，不升级."""
    from unittest import mock
    from apply_fix import FixResult

    src_file = tmp_path / "f.py"
    src_file.write_text("x = 1\n")
    bak = tmp_path / "f.py.bak"
    bak.write_text("x = 1\n")

    rc = type("RC", (), {
        "root_cause": "insufficient_wait",
        "fix_strategy": "ast_rewrite",
        "evidence": {},
    })()
    failure = diagnose.FailureRecord(
        nodeid="tests/x.py::t", classname="x", testname="t",
        message="TimeoutError", traceback="",
    )
    record = diagnose.DiagnosisRecord(failure=failure)
    record.root_cause = rc
    record.fix_applied = FixResult(
        modified=True, new_source="x = 2\n", backup_path=bak,
    )
    record.fix_target_file = src_file

    fake_verify = mock.Mock()
    fake_verify.status = "failed"
    fake_verify.duration_sec = 1.0

    with mock.patch.object(diagnose, "verify_single_test", return_value=fake_verify):
        diagnose._verify_and_maybe_rollback(
            record=record,
            project_dir=tmp_path,
            base_url=None,
            browser=None,
        )

    # 不升级
    assert record.upgraded_root_cause is None
    # 仍 rollback
    assert record.rolled_back is True
```

- [ ] **Step 4.2: 跑测试看失败**

Run:
```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  /usr/local/bin/python3.13 -m pytest evals/core/test_diagnose.py -k "upgrade or assertion_mismatch" -v
```

Expected: 2 FAIL，原因 `AttributeError: 'DiagnosisRecord' object has no attribute 'upgraded_root_cause'`。

- [ ] **Step 4.3: 在 DiagnosisRecord 加新字段**

把 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/diagnose.py:60-71` 的 DiagnosisRecord：

```python
@dataclass
class DiagnosisRecord:
    """单条失败的完整诊断结果。"""
    failure: FailureRecord
    classified: object | None = None  # ClassifiedFailure
    root_cause: object | None = None  # RootCause
    fix_applied: object | None = None  # FixResult
    fix_target_file: Path | None = None
    verify_result: object | None = None  # VerifyResult
    rolled_back: bool = False
    # 扩展：4 类非 ast_rewrite 修复（env / data / bug / script）
    category_repair: dict | None = None  # {"kind": "env"|"data"|"bug"|"script", "plan": ..., "result": ...}
```

替换为：

```python
@dataclass
class DiagnosisRecord:
    """单条失败的完整诊断结果。"""
    failure: FailureRecord
    classified: object | None = None  # ClassifiedFailure
    root_cause: object | None = None  # RootCause
    fix_applied: object | None = None  # FixResult
    fix_target_file: Path | None = None
    verify_result: object | None = None  # VerifyResult
    rolled_back: bool = False
    # 扩展：4 类非 ast_rewrite 修复（env / data / bug / script）
    category_repair: dict | None = None  # {"kind": "env"|"data"|"bug"|"script", "plan": ..., "result": ...}
    # 扩展：verify 失败升级（missing_async_list_wait → assertion_mismatch）
    upgraded_root_cause: str | None = None
    upgrade_reason: str | None = None
```

- [ ] **Step 4.4: 改造 _verify_and_maybe_rollback 加升级逻辑**

把 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/diagnose.py:621-643` 的 `_verify_and_maybe_rollback`：

```python
def _verify_and_maybe_rollback(
    record: DiagnosisRecord,
    project_dir: Path,
    base_url: str | None,
    browser: str | None,
) -> None:
    """重跑单用例；失败则 rollback 到 .bak。"""
    assert record.fix_applied is not None
    assert record.fix_target_file is not None
    failure = record.failure

    result = verify_single_test(
        project_dir=project_dir,
        nodeid=failure.nodeid,
        base_url=base_url,
        browser=browser,
    )
    record.verify_result = result

    if result.status != "passed" and record.fix_applied.backup_path:
        rollback(record.fix_applied.backup_path, record.fix_target_file)
        record.rolled_back = True
```

替换为：

```python
def _verify_and_maybe_rollback(
    record: DiagnosisRecord,
    project_dir: Path,
    base_url: str | None,
    browser: str | None,
) -> None:
    """重跑单用例；失败则 rollback 到 .bak。

    升级规则：原根因是 missing_async_list_wait 且 verify 失败时，
    升级为 assertion_mismatch（仅报告，不再尝试自动修复）。
    """
    assert record.fix_applied is not None
    assert record.fix_target_file is not None
    failure = record.failure

    result = verify_single_test(
        project_dir=project_dir,
        nodeid=failure.nodeid,
        base_url=base_url,
        browser=browser,
    )
    record.verify_result = result

    if result.status != "passed" and record.fix_applied.backup_path:
        rollback(record.fix_applied.backup_path, record.fix_target_file)
        record.rolled_back = True

        # 升级：missing_async_list_wait → assertion_mismatch
        rc = record.root_cause
        if rc and getattr(rc, "root_cause", "") == "missing_async_list_wait":
            record.upgraded_root_cause = "assertion_mismatch"
            record.upgrade_reason = (
                "已应用智能等待，verify 重跑仍失败。"
                "非异步加载问题，建议排查后端搜索接口/测试数据。"
            )
```

- [ ] **Step 4.5: 跑测试看通过**

Run:
```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  /usr/local/bin/python3.13 -m pytest evals/core/test_diagnose.py -v
```

Expected: 所有测试 PASS。

- [ ] **Step 4.6: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  git add scripts/diagnose.py evals/core/test_diagnose.py && \
  git commit -m "feat(diagnose): upgrade missing_async_list_wait to assertion_mismatch on verify failure

When verify_single_test fails after applying async-wait fix, the root
cause is upgraded from missing_async_list_wait to assertion_mismatch.
This signals to the user: 'wait was not the problem, look elsewhere
(backend search API / test data / business logic).'

Other root causes (insufficient_wait, missing_iframe_switch, etc.)
keep the original behavior: rollback only, no upgrade."
```

---

## Task 5: 报告生成 — generate_report + _render_record 扩展

**Files:**
- Modify: `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/diagnose.py:647-701`（generate_report）+ `:704-772`（_render_record）
- Test: `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/evals/core/test_diagnose.py`（末尾追加）

- [ ] **Step 5.1: 写失败测试（报告含升级统计 + 升级渲染）**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/evals/core/test_diagnose.py` 末尾追加：

```python


# ============ 报告生成：assertion_mismatch 统计 + 渲染 ============

def test_generate_report_includes_assertion_mismatch_stats(tmp_path):
    """报告概览含「验证失败 → 升级为 assertion_mismatch」字段."""
    rc = type("RC", (), {
        "root_cause": "missing_async_list_wait",
        "fix_strategy": "ast_rewrite",
        "evidence": {},
    })()
    failure = diagnose.FailureRecord(
        nodeid="tests/x.py::t", classname="x", testname="t",
        message="AssertionError: 搜索 '手表' 应返回商品，但结果数为 0",
        traceback="",
    )
    record = diagnose.DiagnosisRecord(failure=failure)
    record.classified = type("C", (), {"category": "SCRIPT_ERROR", "confidence": 0.65, "signals": []})()
    record.root_cause = rc
    record.upgraded_root_cause = "assertion_mismatch"
    record.upgrade_reason = "已应用智能等待，verify 重跑仍失败。"
    record.rolled_back = True

    out = tmp_path / "report.md"
    diagnose.generate_report([record], out)

    text = out.read_text()
    assert "验证失败 → 升级为 assertion_mismatch" in text
    assert "assertion_mismatch" in text  # 根因分布中也要出现


def test_render_record_shows_upgrade_section(tmp_path):
    """明细中 assertion_mismatch 用例显示升级原因 + 建议."""
    rc = type("RC", (), {
        "root_cause": "missing_async_list_wait",
        "fix_strategy": "ast_rewrite",
        "evidence": {},
    })()
    failure = diagnose.FailureRecord(
        nodeid="tests/x.py::t", classname="x", testname="t",
        message="AssertionError: 搜索 '手表' 应返回商品，但结果数为 0",
        traceback="",
    )
    record = diagnose.DiagnosisRecord(failure=failure)
    record.classified = type("C", (), {"category": "SCRIPT_ERROR", "confidence": 0.65, "signals": []})()
    record.root_cause = rc
    record.upgraded_root_cause = "assertion_mismatch"
    record.upgrade_reason = "已应用智能等待，verify 重跑仍失败。建议排查后端搜索接口。"
    record.rolled_back = True

    lines = diagnose._render_record(1, record)
    text = "\n".join(lines)

    assert "assertion_mismatch" in text
    assert "已应用智能等待" in text
    assert "建议排查后端" in text
```

- [ ] **Step 5.2: 跑测试看失败**

Run:
```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  /usr/local/bin/python3.13 -m pytest evals/core/test_diagnose.py -k "assertion_mismatch or render_record_shows_upgrade" -v
```

Expected: 2 FAIL，原因报告里没有 assertion_mismatch 字段。

- [ ] **Step 5.3: generate_report 加升级统计**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/diagnose.py` 的 `generate_report` 函数中，找到这段（约 660-678 行）：

```python
    by_category: dict[str, int] = {}
    by_root_cause: dict[str, int] = {}
    fix_applied_count = 0
    verify_passed_count = 0
    rolled_back_count = 0
    category_repair_count = 0

    for r in records:
        if r.classified:
            cat = getattr(r.classified, "category", "UNKNOWN")
            by_category[cat] = by_category.get(cat, 0) + 1
        if r.root_cause:
            rc_name = getattr(r.root_cause, "root_cause", "unknown")
            by_root_cause[rc_name] = by_root_cause.get(rc_name, 0) + 1
        if r.fix_applied and r.fix_applied.modified:
            fix_applied_count += 1
        if r.verify_result and getattr(r.verify_result, "status", "") == "passed":
            verify_passed_count += 1
        if r.rolled_back:
            rolled_back_count += 1
        if r.category_repair:
            category_repair_count += 1
```

替换为：

```python
    by_category: dict[str, int] = {}
    by_root_cause: dict[str, int] = {}
    fix_applied_count = 0
    verify_passed_count = 0
    rolled_back_count = 0
    category_repair_count = 0
    upgraded_count = 0

    for r in records:
        if r.classified:
            cat = getattr(r.classified, "category", "UNKNOWN")
            by_category[cat] = by_category.get(cat, 0) + 1
        if r.root_cause:
            rc_name = getattr(r.root_cause, "root_cause", "unknown")
            by_root_cause[rc_name] = by_root_cause.get(rc_name, 0) + 1
        if r.fix_applied and r.fix_applied.modified:
            fix_applied_count += 1
        if r.verify_result and getattr(r.verify_result, "status", "") == "passed":
            verify_passed_count += 1
        if r.rolled_back:
            rolled_back_count += 1
        if r.category_repair:
            category_repair_count += 1
        if r.upgraded_root_cause:
            upgraded_count += 1
            # 升级后的根因也计入分布
            by_root_cause[r.upgraded_root_cause] = \
                by_root_cause.get(r.upgraded_root_cause, 0) + 1
```

然后在同函数中找到这段（约 687-690 行）：

```python
    lines.append(f"| 已应用 AST 修复 | {fix_applied_count} |")
    lines.append(f"| 已应用类别修复（ENV/DATA/BUG/SCRIPT）| {category_repair_count} |")
    lines.append(f"| 验证通过 | {verify_passed_count} |")
    lines.append(f"| 回滚（验证失败）| {rolled_back_count} |")
    lines.append("")
```

替换为：

```python
    lines.append(f"| 已应用 AST 修复 | {fix_applied_count} |")
    lines.append(f"| 已应用类别修复（ENV/DATA/BUG/SCRIPT）| {category_repair_count} |")
    lines.append(f"| 验证通过 | {verify_passed_count} |")
    lines.append(f"| 验证失败 → 升级为 assertion_mismatch | {upgraded_count} |")
    lines.append(f"| 回滚（验证失败）| {rolled_back_count} |")
    lines.append("")
```

- [ ] **Step 5.4: _render_record 加升级段**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/diagnose.py` 的 `_render_record` 函数中，找到这段（约 738-744 行）：

```python
    if record.verify_result:
        vr = record.verify_result
        status = getattr(vr, "status", "unknown")
        duration = getattr(vr, "duration_sec", 0)
        out.append(f"- **验证：** {status}（{duration:.1f}s）")
        if record.rolled_back:
            out.append("- **回滚：** 是（验证未通过，已恢复原文件）")
```

在它之后（仍在 _render_record 内部，下一个 `if` 之前）追加：

```python

    if record.upgraded_root_cause:
        out.append(f"- **根因升级：** {record.upgraded_root_cause}（由 missing_async_list_wait 升级）")
        if record.upgrade_reason:
            out.append(f"- **升级原因：** {record.upgrade_reason}")
```

- [ ] **Step 5.5: 跑测试看通过**

Run:
```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  /usr/local/bin/python3.13 -m pytest evals/core/test_diagnose.py -v
```

Expected: 所有测试 PASS。

- [ ] **Step 5.6: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  git add scripts/diagnose.py evals/core/test_diagnose.py && \
  git commit -m "feat(diagnose): surface assertion_mismatch upgrades in report

Overview gets a new row '验证失败 → 升级为 assertion_mismatch'.
Per-record rendering shows the upgrade chain and reason so users
know to investigate backend / test data instead of test code."
```

---

## Task 6: 全量回归 — 跑所有 evals 确认无破坏

**Files:** 无修改

- [ ] **Step 6.1: 跑全部 evals**

Run:
```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  /usr/local/bin/python3.13 -m pytest evals/ -v
```

Expected: 所有测试 PASS（原有 193 个 + 本次新增的 9 个 = 202 个）。

- [ ] **Step 6.2: 失败时排查**

若有失败，根据报错定位：
- 若是已有测试因 SCRIPT_ERROR 升级而失败（如 `test_returns_root_cause_for_script_error` 期望 `script_error_unspecified`），更新该测试的断言以反映新行为
- 若是 import 错误，检查 Task 3.3 的 import 是否正确
- 若是 AST 修改破坏其他测试，检查 Task 2.4 的 `_insert_wait_call` 是否误匹配

修复后回到 Step 6.1 重跑，直到全绿。

- [ ] **Step 6.3: 不需要 commit（本 Task 无代码改动）**

---

## Task 7: SKILL.md + fix_strategies.md 文档更新

**Files:**
- Modify: `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/SKILL.md`（根因表 + 新增章节）
- Modify: `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/references/fix_strategies.md`（新增章节）

- [ ] **Step 7.1: 更新 SKILL.md 根因表**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/SKILL.md` 找到「Step 4：根因定位（12 种，全部实装）」表格（约 99-114 行），在 `BUG | known_bug_pattern` 行之前追加两行：

```markdown
| SCRIPT | `missing_async_list_wait` | ast_rewrite | 在 `get_product_count()` 首行插入 `_wait_for_product_list_loaded()` + base_page helper |
| SCRIPT | `assertion_mismatch` | none | verify 失败升级，仅报告（建议排查后端/数据）|
```

同步更新该节标题（约 99 行）：

```markdown
### Step 4：根因定位（12 种，全部实装）
```

改为：

```markdown
### Step 4：根因定位（14 种，全部实装）
```

- [ ] **Step 7.2: 在 SKILL.md 「关键能力详解」前追加两阶段流程章节**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/SKILL.md` 找到「## 关键能力详解」（约 199 行），在它之前插入：

```markdown
## 两阶段诊断流程（missing_async_list_wait）

当 SCRIPT_ERROR 用例匹配搜索 0 结果断言时，走特殊两阶段流程：

```
Stage 1: 初次诊断
  SCRIPT_ERROR + 三点信号匹配（搜索 + 期望>0 + 实际=0）
    → root_cause = missing_async_list_wait
    → apply_async_wait_fix()
        · 在 get_product_count() 首行插入 self._wait_for_product_list_loaded()
        · 在 base_page.py 追加 _wait_for_product_list_loaded 方法
    → verify (重跑单用例)

Stage 2: verify 后分类升级
  verify PASS → 保留修改，报告"已修复 missing_async_list_wait"
  verify FAIL → rollback + 升级为 assertion_mismatch
              → 报告"非异步加载问题，建议排查后端搜索接口/测试数据"
```

**信号三点 AND：**
- `_SEARCH_CONTEXT`: 搜索 / search / 查询 / 检索
- `_POSITIVE_EXPECTATION`: 应返回 / 应为 / should return / expected
- `_ZERO_ACTUAL`: 结果数为 0 / count is 0 / returned 0

负向断言（`搜索 'X' 应无结果，但返回 N 个`）不匹配 `_ZERO_ACTUAL`，自动排除。

---

```

- [ ] **Step 7.3: 在 references/fix_strategies.md 追加新章节**

在 `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/references/fix_strategies.md` 找到「## category_repair 策略（3 类模块）」（约 150 行），在它之前插入：

```markdown
### 6. async_wait（异步列表加载等待缺失）

**触发条件：** SCRIPT_ERROR + message 含三点信号：
- 搜索语境（搜索/search/查询/检索）
- 正向期望（应返回/应为/should return/expected）
- 实际为 0（结果数为 0/count is 0/returned 0）

**实现：** `apply_fix.apply_async_wait_fix()`

**修改规则：**

```python
# pages/product/search_result_page.py（修改前）
class SearchResultPage(BasePage):
    def get_product_count(self) -> int:
        return self._product_cards.count()

# 修改后
class SearchResultPage(BasePage):
    def get_product_count(self) -> int:
        self._wait_for_product_list_loaded()  # ← AST 插入
        return self._product_cards.count()
```

```python
# pages/base_page.py（自动追加 helper）
class BasePage:
    ...
    def _wait_for_product_list_loaded(self, timeout_ms: int = 10000) -> None:
        """等商品列表首屏渲染完成。"""
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass
        try:
            self.page.wait_for_function(
                """() => {
                    const sels = ['.product-card', '.goods-card', '.search-result-item',
                                  '.item-card', '[data-product-id]', '.product-item'];
                    return sels.some(s => document.querySelectorAll(s).length > 0);
                }""",
                timeout=timeout_ms,
            )
        except Exception:
            pass
```

**幂等：** 若 `get_product_count` 方法体首行已是 `self._wait_for_*()`，跳过修改。
**目标方法选择：** `get_product_count` 是搜索流程与结果断言的天然桥梁，所有正/负向搜索测试都经此调用。
**verify 失败升级：** 若修复后 verify 重跑仍失败，自动 rollback 并升级根因为 `assertion_mismatch`（fix_strategy=none，仅报告）。

---

```

- [ ] **Step 7.4: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser && \
  git add SKILL.md references/fix_strategies.md && \
  git commit -m "docs(diagnoser): document missing_async_list_wait + assertion_mismatch

- SKILL.md: root cause table 12→14; new section on two-stage
  diagnosis flow with signal matching rules
- fix_strategies.md: new section on apply_async_wait_fix with
  before/after code, helper template, idempotency, and upgrade rule"
```

---

## Task 8: 实际用例验收 — shop-lab-ui-test dry-run

**Files:** 无修改（只跑诊断，不实际改 pages/）

- [ ] **Step 8.1: 准备 shop-lab-ui-test 测试结果**

如果 `test-results/report.xml` 已存在且是最新失败记录，跳到 Step 8.2。否则重跑：

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test && \
  /usr/local/bin/python3.13 -m pytest tests/ \
    --base-url http://localhost:3000 \
    --junit-xml test-results/report.xml \
    --output test-results/artifacts/pytest-raw \
    -q --no-header 2>&1 | tail -20
```

Expected: 测试跑完，生成 `test-results/report.xml`。

- [ ] **Step 8.2: dry-run 跑新诊断**

Run:
```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test && \
  /usr/local/bin/python3.13 \
    /Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/scripts/diagnose.py \
    --junit-xml test-results/report.xml \
    --artifacts-dir test-results/artifacts \
    --project-dir . \
    --dry-run \
    --output test-results/ui_repair_report_async.md
```

Expected stdout 含：
```
[diagnose] 共诊断 N 条失败
[diagnose] AST 修复：M 条（其中 dry-run 不写文件）
```

- [ ] **Step 8.3: 验证报告分类正确**

Run:
```bash
grep -E "missing_async_list_wait|script_error_unspecified|SCRIPT_ERROR" \
  /Users/zhoujinjian/ai_project/shop-lab-ui-test/test-results/ui_repair_report_async.md
```

Expected: 搜索失败用例（`test_search_valid_keyword_shows_results`）显示 `missing_async_list_wait`，而非 `script_error_unspecified`。

- [ ] **Step 8.4: 不需要 commit**

dry-run 模式不修改文件，无 commit。报告文件可选保留供后续对照。

---

## Self-Review Checklist

**Spec coverage:**
- ✅ §3 新增 2 根因 → Task 1（missing_async_list_wait）+ Task 4（assertion_mismatch 升级）
- ✅ §4 三点 AND 信号匹配 → Task 1 Step 1.4
- ✅ §4.3 反向断言排除 → Task 1 Step 1.1 测试 2
- ✅ §5.1-5.6 AST 修复模板 + 幂等 → Task 2
- ✅ §6.1 两阶段流程图 → Task 3 + Task 4
- ✅ §6.3 assertion_mismatch 不再修复 → Task 4 升级逻辑（fix_strategy=none 由报告渲染隐含）
- ✅ §7.1 概览新增字段 → Task 5 Step 5.3
- ✅ §7.2 明细新增字段 → Task 5 Step 5.4
- ✅ §8 影响范围所有文件 → Task 1-7 全覆盖
- ✅ §10.1 功能验收 8 条 → 测试覆盖
- ✅ §10.3 evals ≥ 8 个 → Task 1（4）+ Task 2（3）+ Task 4（2）+ Task 5（2）= 11 个新增
- ✅ §11 风险缓解 → 三点 AND（Task 1）+ helper 多 selector（Task 2）+ verify 升级（Task 4）

**Placeholder scan:** ✅ 无 TBD/TODO/适当错误处理/类似 Task N。

**Type consistency:** ✅
- `apply_async_wait_fix` 签名一致（Task 2.4 定义、Task 3.1 测试调用、Task 4.1 测试调用）
- `FixResult` 字段使用一致（modified / new_source / backup_path / patch）
- `DiagnosisRecord.upgraded_root_cause` 字段名一致（Task 4.3 定义、Task 5.3 渲染）
- `_is_search_zero_assertion` 函数名一致（Task 1.4 定义、内部使用）

---

## Execution Handoff

Plan complete and saved to `/Users/zhoujinjian/.claude/skills/ui-failure-diagnoser/docs/plans/2026-06-23-async-list-wait-diagnosis-plan.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — 我（Claude）每个 Task 派一个 fresh subagent 执行，两阶段审查（subagent 自检 + 我复核），任务间快速迭代。

**2. Inline Execution** — 在当前会话用 executing-plans 批量执行，检查点处停下来让你 review。

Which approach?
