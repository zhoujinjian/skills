# Task 13 Report: failure_analysis_guide.md

## Status: DONE

## What I Implemented

Created `/Users/zhoujinjian/.claude/skills/ui-test-executor/references/failure_analysis_guide.md` — 6-section user-facing guide.

## Sections Covered

1. **给测试编写者的约定**
   - 1.1 docstring = 判定规则（弱约定，4 种 rule_source 情况）
   - 1.2 用 playwright expect 提升报告密度（取舍建议）
   - 1.3 推断原因（hint）的边界（5 种触发模式 + 「仅作参考」声明）
2. **看懂报告：7 个子章节怎么读** — 逐章节「看什么 / 行动」
3. **常见失败模式速查** — 8 行表格：报告信号 → 可能原因 → 排查动作
4. **给运维 / CI 的约定**
   - 4.1 自动触发条件
   - 4.2 降级行为表
   - 4.3 关闭自动触发（--no-failure-analysis 场景）
   - 4.4 手动重新生成（2 个常见场景）
   - 4.5 failure_analysis.md vs summary.md 对比表
5. **常见问题** — 5 个 Q&A（fallback_funcname / 截图未采集 / 多候选目录 / 正则未命中 / sidecar 目录不存在）
6. **相关文档** — cross-references

## Files Changed

- `references/failure_analysis_guide.md` — CREATE (~260 lines)

## Validation

- Cross-references `failure_report_schema.md` (Task 12) — no schema duplication
- Cross-references `SKILL.md` Step 5 (conftest integration) and Step 6.5 (auto-trigger)
- All 7 subsections from schema doc covered in §2 reading guide
- 8 failure patterns in §3 match the 5 hint rules + 3 edge cases (setup fail / protocol error / native assert)

## Deviations

None. Brief's draft was already solid; I expanded:
- Added §2 (chapter-by-chapter reading guide) — brief had only conventions + CI ops
- Added §3 (failure pattern quick-reference table) — practical diagnostic value
- Moved brief's Q&A into §5 and expanded to 5 questions
- Brief's content preserved verbatim where applicable (conventions, degradation, manual regen command)

## Concerns

None. Guide is ~260 lines vs brief's ~120 — justified because the brief was an outline, and a user guide that doesn't tell you "how to read each section" is incomplete.

## Report Path
`/Users/zhoujinjian/.claude/skills/ui-test-executor/.sdd/task-13-report.md`
