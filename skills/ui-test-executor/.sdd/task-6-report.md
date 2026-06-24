# Task 6 Report: generate_failure_analysis.py 脚本骨架

## What was implemented

Created `/Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py` verbatim from `task-6-brief.md`. The script contains:

- Module docstring with inputs/outputs/degradation chain/usage
- Imports: `argparse`, `sys`, `xml.etree.ElementTree as ET`, `dataclasses.dataclass` + `field`, `pathlib.Path`
- `from __future__ import annotations` for PEP 604 (`list[str] | None`) on Python 3.9 compatibility
- `FailureCase` dataclass with all 9 fields (`nodeid`, `classname`, `name`, `file`, `line`, `duration`, `message`, `traceback`, `sidecar`)
- `parse_junit_failures(xml_path)` — iterates `<testcase>` nodes, detects `<failure>` first then falls back to `<error>`, reconstructs nodeid via `classname::name`
- `main(argv)` — argparse with `--junit-xml` (required), `--artifacts-dir`, `--output-dir`, `--execution-summary`; resolves & existence-checks the XML (returns exit code 2 if missing); returns 0 with `[OK] 无失败用例` when no failures; calls `render_failure_analysis` placeholder otherwise
- `render_failure_analysis(...)` — placeholder that raises `NotImplementedError("render_failure_analysis 由 Task 7-10 实现")` to be implemented by Tasks 7-10
- `if __name__ == "__main__": sys.exit(main())` guard

## Smoke test evidence

Command run:

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py \
    --junit-xml test-results/report.xml \
    --artifacts-dir test-results/artifacts \
    --output-dir test-results
echo "exit=$?"
```

Output:

```
[INFO] 检测到 1 个失败用例，开始生成 failure_analysis.md
Traceback (most recent call last):
  File "/Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py", line 131, in <module>
    sys.exit(main())
  File "/Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py", line 112, in main
    md = render_failure_analysis(
        failures=failures,
        artifacts_dir=Path(args.artifacts_dir).resolve(),
        execution_summary=args.execution_summary,
    )
  File "/Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py", line 127, in render_failure_analysis
    raise NotImplementedError("render_failure_analysis 由 Task 7-10 实现")
NotImplementedError: render_failure_analysis 由 Task 7-10 实现
exit=1
```

The single detected failure matches the expected `test_search_valid_keyword_shows_results[chromium-小米]` case (the `<failure>` node in `tests.product.test_search.TestSearchPositive`). XML root reports `failures="1"`, script detected exactly 1.

## Files changed

- Created: `/Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py` (142 lines, verbatim transcription from brief)

## Self-review findings

All checklist items pass:

- File created at `scripts/generate_failure_analysis.py` ✓
- All imports included (argparse, sys, ET, dataclass+field, Path, `from __future__ import annotations`) ✓
- `FailureCase` dataclass has all 9 fields per brief ✓
- `parse_junit_failures` handles both `<failure>` and `<error>` (prefers `<failure>` when both present, falls back to `<error>`) ✓
- `main` does XML existence check + returns exit code 2 on missing ✓
- `main` returns 0 with `[OK] 无失败用例` when no failures ✓
- `render_failure_analysis` placeholder raises `NotImplementedError` ✓
- Smoke test shows expected `NotImplementedError` after `[INFO] 检测到 1 个失败用例` ✓
- `if __name__ == "__main__": sys.exit(main())` at bottom ✓

## Deviations

None. Code is byte-for-byte the brief's code block. Git commit (Step 3) intentionally skipped per task instructions (not a git repo).

## Concerns

None. Placeholder behavior is intentional — Tasks 7-10 will fill in `render_failure_analysis`. Exit code on `NotImplementedError` is 1 (Python's default uncaught exception), which is acceptable for the scaffold phase.
