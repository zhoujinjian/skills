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

