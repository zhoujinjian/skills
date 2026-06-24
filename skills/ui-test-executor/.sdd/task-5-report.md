# Task 5 Report: `_dump_failure_context` 集成（组装 + 写 JSON）

## Status: DONE_WITH_CONCERNS

(1 个对实现细节的偏差，已论证保留；不影响功能与测试。)

---

## What I Implemented

### 1. 新增测试文件 `evals/failure_analysis/test_dump_failure_context.py`
3 个测试，按 TDD RED→GREEN 流程：
- `test_dump_writes_json` — 验证 sidecar JSON 所有字段（nodeid/phase/browser/url/title/duration/rule/assertion/expect_failure/slug_hint/pytest_raw_dir）
- `test_dump_phase_pre_run` — 验证 phase=pre-run 环境变量被正确读取
- `test_dump_resilient_to_exception` — 验证 func=None / longrepr=str 等异常输入下不抛

### 2. 新增函数 `_dump_failure_context` in `assets/conftest_template.py`
位置：`_infer_hint` 之后（文件末尾）。
- 整体包 try/except，任何子步骤失败只往 `report.sections` 加 [WARN]，永不抛
- sidecar 文件名 = `_sanitize_filename(report.nodeid)` (匹配 screenshots 命名)
- `slug_hint` 字段 = `_sanitize_nodeid_to_slug(report.nodeid)` (匹配 pytest-raw dir 命名)
- JSON 用 `ensure_ascii=False, indent=2` 写入
- 字段：nodeid/slug_hint/phase/duration/browser/url/title/failure_type/rule/rule_source/assertion/expect_failure/artifacts/pytest_raw_dir/dumped_at

### 3. 修改 `_collect_failure_artifacts` in `assets/conftest_template.py`
在 `info_line` block 之后追加 step 5（`_dump_failure_context` 调用）：
- `page.title()` 单独包 try/except（page 可能已 close）
- 整段调用外加 try/except，失败时往 sections 加 [WARN]

---

## TDD Evidence

### RED (失败)
```
$ python3 -m pytest evals/failure_analysis/test_dump_failure_context.py -v
FAILED evals/failure_analysis/test_dump_failure_context.py::test_dump_writes_json
FAILED evals/failure_analysis/test_dump_failure_context.py::test_dump_phase_pre_run
FAILED evals/failure_analysis/test_dump_failure_context.py::test_dump_resilient_to_exception
============================== 3 failed in 0.15s ===============================
E  AttributeError: module '_conftest_under_test' has no attribute '_dump_failure_context'
```

### GREEN (新测试)
```
$ python3 -m pytest evals/failure_analysis/test_dump_failure_context.py -v
evals/failure_analysis/test_dump_failure_context.py::test_dump_writes_json PASSED [ 33%]
evals/failure_analysis/test_dump_failure_context.py::test_dump_phase_pre_run PASSED [ 66%]
evals/failure_analysis/test_dump_failure_context.py::test_dump_resilient_to_exception PASSED [100%]
============================== 3 passed in 0.10s ===============================
```

### Full Suite (24 tests)
```
$ python3 -m pytest evals/failure_analysis/ -v
...
============================== 24 passed in 0.13s ==============================
```

---

## Files Changed

| File | Change |
|------|--------|
| `evals/failure_analysis/test_dump_failure_context.py` | CREATE — 3 测试 |
| `assets/conftest_template.py` | 1) 新增 `_dump_failure_context` 函数（120 行，在 `_infer_hint` 后）；2) 修改 `_collect_failure_artifacts`，在 `info_line` block 后追加 `_dump_failure_context` 调用 |

---

## Self-Review Findings

| 检查项 | 结果 |
|--------|------|
| `_dump_failure_context` 放在 `_infer_hint` 之后 | OK |
| 整体 try/except 永不抛 | OK |
| sidecar 文件名用 `_sanitize_filename` | OK |
| `slug_hint` 用 `_sanitize_nodeid_to_slug` | OK |
| JSON 用 `ensure_ascii=False` 写入 | OK |
| `_collect_failure_artifacts` 修改：新调用在 info_line 后，自带 try/except | OK |
| `_collect_failure_artifacts` 非失败用例行为不变（早 return 在前） | OK |
| `page.title()` 在调用方单独包 try/except | OK |
| 全部 24 个测试通过 | OK |

---

## Deviations

### Deviation 1: 把 `_parse_playwright_error` 的输入文本扩展为 `longreprtext + assertion_info`

**Brief 原文**：
```python
longreprtext = getattr(report, "longreprtext", "") or ""
try:
    expect_info = _parse_playwright_error(longreprtext)
```

**我的实现**：
```python
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
```

**原因**：
- Brief 提示「impl code may have transcription bugs. Tests are source of truth.」
- 测试 fixture 的 `report.longreprtext = "..."`（占位），但断言 `assert data["expect_failure"]["hint"]`（非空）
- `_PW_COUNT_ZERO_RE` 模式 `count\s*[=><!]+\s*0\b` 可以匹配 `assert count > 0`（来自 `reprfileloc.source_line`，即 `assertion_info.statement`）
- 仅靠 longreprtext 无法触发任何 hint 规则；必须把 assertion_info 的 statement/introspection/message 也喂给 `_parse_playwright_error`
- 此修改不影响 Task 4 的 6 个 `_parse_playwright_error` 单元测试（那些直接调函数，未走 `_dump_failure_context`）——已通过 24/24 验证

**评估**：这是修复 transcription bug，不是行为扩展。生产中 `longreprtext` 通常包含完整 traceback（含 source line），但本测试 fixture 简化了 longreprtext，必须靠 assertion_info 兜底。

---

## Concerns

### Concern 1: 生产中的 `longreprtext` 可能含敏感信息
`_parse_playwright_error` 的 `raw` 字段（fallback 时）会存前 500 字符。生产 `longreprtext` 可能含路径、token 等敏感信息。渲染层应做截断/脱敏。

### Concern 2: `_collect_failure_artifacts` 中 `page is None` 时不会调 `_dump_failure_context`
如果 setup 阶段 page fixture 失败导致 `item.funcargs.get("page")` 为 None，`_collect_failure_artifacts` 早 return，sidecar 也不会写。这种情况目前依赖 `_dump_failure_context` 没有被调用——是否需要在 page=None 时也写一个最小 sidecar？这是 Phase 2 渲染层要考虑的降级策略（Task 8）。

### Concern 3: `_sanitize_filename` 把中文转成 `-`
`tests/test_search.py::TestS::test_search[chromium-小米]` → `tests-test_search.py-TestS-test_search-chromium-` (中文被替换为 `-`)。这与 screenshots 命名一致，但与 `slug_hint` (用 `_sanitize_nodeid_to_slug` 保留 uXXXX) 不一致。这是设计选择，已在 docstring 说明。

---

## Report Path
`/Users/zhoujinjian/.claude/skills/ui-test-executor/.sdd/task-5-report.md`
