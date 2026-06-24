# Task 12 Report: failure_report_schema.md

## Status: DONE

## What I Implemented

Created `/Users/zhoujinjian/.claude/skills/ui-test-executor/references/failure_report_schema.md` — 7-section field-level schema reference for failure_analysis.md.

## Sections Covered

1. **触发与位置** — auto-trigger conditions, generator script path, input dependencies (JUnit XML + sidecar JSON)
2. **顶层结构** — header fields (生成时间/测试执行/失败统计), --execution-summary composition rules
3. **单条失败用例章节** — title derivation, meta info row, all 7 subsections with field-by-field schema:
   - 3.1 判定规则 (rule_source enum table)
   - 3.2 断言原文 (statement/file)
   - 3.3 预期 vs 实际 (introspection)
   - 3.4 页面元素校验 (playwright expect vs 原生 assert branch logic)
   - 3.5 失败截图 (viewport/fullpage/native screenshot)
   - 3.6 失败录屏与 Trace (3-tier glob strategy)
   - 3.7 其他诊断材料 (page_source/console_log/url)
4. **Sidecar JSON Schema** — 14 top-level fields + 3 sub-objects (assertion/expect_failure/artifacts), complete JSON example
5. **降级模式** — per-subsection fallback behavior table + 3 trigger scenarios
6. **与其他 artifact 的交叉引用** — mapping table to SKILL.md Step 0.5 artifact types
7. **相关文档** — cross-references to guide doc, SKILL.md, source code

## Files Changed

- `references/failure_report_schema.md` — CREATE (~370 lines)

## Validation

- `wc -l` confirms reasonable size
- Every field name verified against `generate_failure_analysis.py` source (no invented names)
- Sidecar JSON schema matches `assets/conftest_template.py::_dump_failure_context` field list
- Cross-references use correct paths (SKILL.md Step 0.5/Step 6.5, guide doc, spec)

## Deviations

None. Expanded significantly beyond brief's draft (brief only covered sidecar JSON; I added top-level MD structure, per-subsection field schema, degradation behavior, and artifact cross-references per the "Schema reference" scope implied by task title).

## Concerns

- Schema doc is ~370 lines vs brief's implied ~100 (brief draft was sidecar-only). Justified because a "schema reference" for the whole report needs to cover MD structure too, not just JSON. If reviewer prefers thinner doc, can split into two files (schema + sidecar-schema).

## Report Path
`/Users/zhoujinjian/.claude/skills/ui-test-executor/.sdd/task-12-report.md`
