# Task 9 Report: video/trace 路径补全的 slug 容错

## What I Implemented

Hardened `_resolve_video_trace` in `scripts/generate_failure_analysis.py` to handle 4 cases by priority:

1. **Exact slug match** (Task 7, preserved): `<pytest_raw_dir>/<slug>/` exists → use directly.
2. **No match, empty result** (Task 7, preserved): nonexistent slug, no pytest-raw dir → `{}`.
3. **Glob fallback (NEW)**: slug doesn't match exactly but `pytest-raw/` has exactly 1 subdir → use that subdir (tolerates slug escape drift like `小` vs literal). Also added a prefix-match branch for the multi-dir case where exactly one subdir shares the slug's first 30 chars (lowercased).
4. **Multi-candidate warning (NEW)**: `pytest-raw/` has multiple subdirs and no exact match → don't silently pick; return `{"_multi_candidate": True}` so renderer can flag human review.

Also added `_multi_candidate` handling to `render_failure_section`'s video/trace table — emits `⚠️ 多个候选目录匹配，请人工确认` row when the flag is set.

## TDD Evidence

### RED (Step 2)
```
evals/failure_analysis/test_glob_video_trace.py::test_exact_slug_match PASSED            [ 25%]
evals/failure_analysis/test_glob_video_trace.py::test_no_matching_slug_returns_empty PASSED [ 50%]
evals/failure_analysis/test_glob_video_trace.py::test_glob_fallback_when_slug_mismatch FAILED [ 75%]
evals/failure_analysis/test_glob_video_trace.py::test_multiple_candidates_warning FAILED [100%]
========================= 2 failed, 2 passed in 0.14s ==========================
```
The 2 pre-existing behaviors (exact match, no-match empty) already passed under Task 7's impl. The 2 NEW behaviors correctly failed RED.

### GREEN (Step 4)
```
evals/failure_analysis/test_glob_video_trace.py::test_exact_slug_match PASSED            [ 25%]
evals/failure_analysis/test_glob_video_trace.py::test_no_matching_slug_returns_empty PASSED [ 50%]
evals/failure_analysis/test_glob_video_trace.py::test_glob_fallback_when_slug_mismatch PASSED [ 75%]
evals/failure_analysis/test_glob_video_trace.py::test_multiple_candidates_warning PASSED [100%]
============================== 4 passed in 0.10s ===============================
```

### Full Suite (Step 5)
```
============================== 35 passed in 0.15s ==============================
```
All 31 prior tests still pass + 4 new = 35/35. No regression.

## Files Changed

- **Created**: `/Users/zhoujinjian/.claude/skills/ui-test-executor/evals/failure_analysis/test_glob_video_trace.py` — 4 tests, verbatim transcription from brief.
- **Modified**: `/Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py`
  - `_resolve_video_trace` (lines 342-401): replaced 20-line exact-match-only impl with 60-line hardened version with glob fallback + multi-candidate warning.
  - `render_failure_section` (lines 262-273): added `elif video_trace.get("_multi_candidate")` branch to both video and trace row rendering.

## Self-Review Findings

| Check | Status |
|---|---|
| `_resolve_video_trace` handles all 4 cases (exact / empty / glob fallback / multi-candidate) | PASS |
| Returns `_multi_candidate: True` when multiple candidates and no exact match | PASS |
| Single-dir fallback works even when slug doesn't match at all | PASS (test_glob_fallback_when_slug_mismatch) |
| Renderer shows `⚠️ 多个候选目录匹配，请人工确认` when `_multi_candidate` is set | PASS (impl added; covered structurally — no explicit render test in brief) |
| Existing tests `test_exact_slug_match`, `test_no_matching_slug_returns_empty` still pass | PASS |
| Full suite 35 passes | PASS |

## Deviations

None. Code is verbatim from brief for both the test file and the `_resolve_video_trace` replacement. The `render_failure_section` edit follows the brief's video-row pattern and applies the same pattern to the trace row (brief says "trace 行同理").

Note on type hint: as called out in the task description, signature uses `dict` return type and body uses `result: dict[str, object] = {}`. This is fine — mypy-compatible, runtime-compatible, all 4 tests pass.

## Concerns

- **No explicit render test for `_multi_candidate` warning**: The brief only asks for 4 `_resolve_video_trace` tests; the `render_failure_section` change is covered structurally (existing render tests in `test_render_failure_section.py` still pass with the new elif branch). A dedicated render test for the warning row would be nice-to-have but is out of scope per brief.
- **Prefix-match heuristic is lenient**: The 30-char lowercased prefix match in the multi-dir fallback path could produce surprising matches if two test slugs share a long common prefix (e.g. `tests-auth-test-login-` for parametrized variants). In that case it falls through to multi-candidate warning, which is the safe behavior — so this is self-correcting.
