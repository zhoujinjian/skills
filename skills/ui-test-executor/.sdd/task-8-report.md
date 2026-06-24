# Task 8 Report: 降级渲染（sidecar JSON 缺失时）

## What I Implemented

Created `evals/failure_analysis/test_fallback_render.py` containing 2 tests that verify `render_failure_section` handles an empty sidecar (`sidecar={}`) gracefully:

1. **`test_empty_sidecar_still_renders`** — Verifies that with `sidecar={}`:
   - The title falls back to `case.name` (`test_a` appears)
   - The JUnit message appears in output (`expected 5 got 3`)
   - The section skeleton is preserved (`判定规则` appears)
   - Screenshot/video placeholders show `未采集` / `未生成`

2. **`test_no_sidecar_section_has_warning`** — Verifies that with `sidecar={}`, the rule section shows the fallback warning (`无 sidecar` or `rule 字段缺失`).

Both tests were transcribed verbatim from the task brief.

## TDD Evidence

### Initial run (Step 2)

```
evals/failure_analysis/test_fallback_render.py::test_empty_sidecar_still_renders PASSED [ 50%]
evals/failure_analysis/test_fallback_render.py::test_no_sidecar_section_has_warning PASSED [100%]
============================== 2 passed in 0.09s ===============================
```

Both tests **passed immediately** against Task 7's existing implementation — exactly as the brief predicted ("Task 7 的实现已经处理空 sidecar...所以测试应该已通过"). Step 3 (fix `render_failure_section`) was **not needed**.

### Full suite (Step 4)

```
============================== 31 passed in 0.14s ===============================
```

All 31 tests pass (29 prior + 2 new).

## Why No Implementation Change Was Needed

Task 7's `render_failure_section` in `scripts/generate_failure_analysis.py` already handles empty sidecar via:

- **Line 143**: `title_rule = (sidecar.get("rule") or "").splitlines()[0] if sidecar.get("rule") else case.name` — falls back to `case.name` when rule is empty.
- **Lines 163-177**: `rule = sidecar.get("rule", "")` → if empty, renders `> *(无 sidecar，rule 字段缺失，详见断言原文)*`.
- **Lines 240-250**: `artifacts = sidecar.get("artifacts", {}) or {}` with `screenshots = artifacts.get("screenshots", [])` → empty list renders `*(未采集)*`.
- **Lines 260-269**: `video_trace={}` → renders `*(未生成，...)*` for both video and trace rows.
- **Line 157**: `**位置**: `{case.nodeid}`` and **line 208** `url = sidecar.get("url", "") or case.message` ensure the JUnit message appears in the output.

## Files Changed

| File | Change |
|------|--------|
| `evals/failure_analysis/test_fallback_render.py` | Created (2 tests) |
| `scripts/generate_failure_analysis.py` | **Unchanged** (Task 7 already covered these cases) |

## Self-Review Findings

- 2 tests created in `test_fallback_render.py` — yes, transcribed verbatim from brief.
- Tests passed immediately on Task 7 code — confirmed, no impl changes needed.
- Full test suite passes (31 tests) — confirmed.
- Commit skipped — confirmed (not a git repo).

## Concerns

None. Task 7's implementation robustly handles the empty-sidecar case through consistent use of `.get(key, "")` defaults and explicit `else` branches for missing screenshots/video/trace. The fallback at line 143 (`case.name` for empty rule) and line 176 (`无 sidecar` warning) cover both new test assertions directly.
