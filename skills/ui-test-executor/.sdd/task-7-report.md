# Task 7 Report: render_failure_section

## What was implemented

1. **Created** `evals/failure_analysis/test_render_failure_section.py` with 5 tests (verbatim from brief):
   - `test_section_contains_required_sections` — asserts all 7 subsection headers + rule + file:line present
   - `test_section_native_assert_renders_empty_locator_row` — native assert shows "原生 assert" / "未提取"
   - `test_section_playwright_expect_renders_locator` — locator/expected/received rendered when playwright expect failure
   - `test_section_video_trace_paths_rendered` — video/trace paths + `playwright show-trace` command
   - `test_section_video_trace_missing_renders_warning` — "未生成" marker when missing

2. **Modified** `scripts/generate_failure_analysis.py`:
   - Appended `_is_playwright_expect_failure(sidecar)` helper
   - Appended `render_failure_section(case, sidecar, video_trace)` — renders MD with all 7 required subsections
   - Replaced `render_failure_analysis` placeholder (NotImplementedError) with full impl: top-level header + execution_summary + per-failure iteration using `_load_sidecar` + `_resolve_video_trace`
   - Appended `_load_sidecar(artifacts_dir, case)` — safe-loads `failure-context/<safe_nodeid>.json`, returns `{}` on miss
   - Appended `_resolve_video_trace(sidecar)` — resolves `video.webm` / `trace.zip` / `test-failed-*.png` from `pytest_raw_dir/slug_hint`

## TDD Evidence

### RED (before impl)
```
5 failed in 0.14s
AttributeError: module '_gen_failure_analysis' has no attribute 'render_failure_section'
```

### GREEN (after impl)
```
5 passed in 0.09s
```

### Full failure_analysis suite
```
29 passed in 0.13s
```
(5 new + 24 prior: dump_failure_context 3, extract_rule 6, parse_assertion 4, parse_playwright_error 6, sanitize_slug 5 = 24 prior)

### End-to-end smoke (shop-lab-ui-test artifacts)
```
[INFO] 检测到 1 个失败用例，开始生成 failure_analysis.md
[OK] 已生成 /Users/zhoujinjian/ai_project/shop-lab-ui-test/test-results/failure_analysis.md
exit=0
```

Generated MD head shows:
- Top-level `# 失败用例故障分析报告` header
- Execution summary line: `**测试执行**: P0 and run_smoke · chromium · headless`
- Failure count: `**失败统计**: 1 个失败用例`
- One `## ❌` section with all 7 required subsections (判定规则 / 断言原文 / 预期 vs 实际 / 页面元素校验 / 失败截图 / 失败录屏与 Trace / 其他诊断材料)
- Degraded-mode markers as expected (sidecar JSON missing — Task 8 scope)

## Files Changed
- `/Users/zhoujinjian/.claude/skills/ui-test-executor/evals/failure_analysis/test_render_failure_section.py` (created)
- `/Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py` (modified — appended 3 functions + replaced placeholder)

## Self-Review Findings

| Check | Result |
|---|---|
| `render_failure_section` returns MD with all 7 required subsections | PASS |
| Native assert case renders "原生 assert" warning | PASS |
| Playwright expect case renders locator/expected/received in table | PASS |
| video/trace paths rendered when provided | PASS |
| "未生成" when video/trace missing | PASS |
| `playwright show-trace` command in Trace row when trace exists | PASS |
| Top-level `render_failure_analysis` has header + execution_summary + failure count | PASS |
| `_load_sidecar` handles missing file (returns `{}`) | PASS |
| `_resolve_video_trace` handles missing dir / no slug | PASS (early return on empty slug/raw_dir) |
| Full test suite passes (29 tests) | PASS |

## Deviations
None. Code transcribed verbatim from brief; tests pass on first run.

## Concerns
- **Degraded mode in smoke test is verbose**: When sidecar is missing, the "失败 URL" cell falls back to `case.message` which contains the full AssertionError + assert line (multi-line, breaks table formatting). This is functional but not pretty. Task 8 (降级渲染) is expected to refine this.
- **`render_failure_analysis` has unused `i` variable** in `enumerate(failures, 1)` loop — transcribed as-is from brief, not load-bearing.
- **`url` in "其他诊断材料" duplicates** the value in "失败 URL" cell when sidecar is missing (both fall back to `case.message`). Will clean up in Task 8.
