# ui-pipeline-scheduler 设计 Spec

> **状态**：草案 · 待用户 review
> **日期**：2026-06-24
> **作者**：Claude（基于用户需求 + brainstorming）

---

## 一、技能定位

**ui-pipeline-scheduler** 是 UI 自动化测试全链路的**统一编排入口**，负责把三个独立 skill 串成闭环：

```
ui-test-executor  →  ui-failure-diagnoser  →  ui-test-executor（重试）  →  ui-report-generator
       ↑                      ↑                                              ↑
   执行入口              仅失败时触发                                    始终生成
```

**核心原则（来自用户硬约束）**：

1. **零侵入**：禁止修改 ui-test-executor / ui-failure-diagnoser / ui-report-generator 任何代码、入参、出参、调用方式
2. **纯编排**：本 skill 只负责流程串联、条件判断、循环调度、失败兜底；不实现任何业务逻辑
3. **双模式兼容**：子技能可单独手动调用，也可被本 skill 自动串联

---

## 二、关键架构决策（brainstorming 结论）

| 决策点 | 选定方案 | 理由 |
|--------|---------|------|
| **实现层级** | 纯 SKILL.md 编排（无 scripts/） | 对齐 api-pipeline-scheduler 模板；最符合「不修改子技能」原则；零代码维护 |
| **重试范围** | 只重跑上次失败的用例 | 速度快；通过 pytest `-k "nodeid1 or nodeid2"` 精准筛选 |
| **最大重试次数** | 默认 2 次（共 3 轮执行）；可 CLI 覆盖 | 平衡 flaky 修复率与总耗时 |
| **失败兜底** | 达上限仍失败时**仍然生成最终报告**，标记「修复失败」 | 用户能看到完整链路尝试过程，不丢现场 |

---

## 三、目录结构

```
~/.claude/skills/ui-pipeline-scheduler/
├── SKILL.md                          # 唯一入口：编排剧本 + 触发条件 + 参数透传表
├── docs/
│   └── specs/
│       └── 2026-06-24-ui-pipeline-scheduler-design.md   # 本 spec
└── references/
    ├── pipeline_flow.md              # 详细流程图（含重试循环 + 失败兜底分支）
    └── param_passing.md              # 参数透传契约表（executor → diagnoser → report）
```

**注意**：**没有 scripts/ 目录**。所有编排逻辑写在 SKILL.md 里，由 Claude 按剧本走。

---

## 四、编排流程

### 4.1 主流程（含重试循环）

```
┌──────────────────────────────────────────────────────────────────┐
│ STEP 1: ui-test-executor 执行（首轮）                            │
│   Bash → execute_tests.py tests/ --priority P0 --tags smoke ...  │
│   产物：test-results/{report.xml, report.json, browser_env.json, │
│         artifacts/, failure_analysis.md}                         │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
                   ┌───────────────────────┐
                   │ 解析 report.xml       │
                   │ 统计 failures + errors│
                   └───────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │ 0 个失败       │ ≥1 个失败       │
              ▼                ▼                │
   ┌──────────────────┐  ┌─────────────────────────────┐
   │ 跳过诊断重试     │  │ STEP 2: ui-failure-diagnoser│
   │ 直接进 Step 5    │  │   Bash → diagnose.py        │
   └──────────────────┘  │     --junit-xml report.xml │
                         │     --artifacts-dir ...    │
                         │     --project-dir <项目根> │
                         │   产物：                    │
                         │     test-results/ui_repair_report.md│
                         │     pages/**/*.py（AST 修复）│
                         └─────────────┬───────────────┘
                                       │
                                       ▼
                         ┌─────────────────────────────┐
                         │ STEP 3: 重试执行            │
                         │  提取失败 nodeid 列表        │
                         │  Bash → execute_tests.py    │
                         │     -k "nid1 or nid2 or ..."│
                         │     --output-dir ./test-results│
                         │     （覆盖原 report.xml）   │
                         └─────────────┬───────────────┘
                                       │
                                       ▼
                         ┌─────────────────────────────┐
                         │ 重试计数 round += 1         │
                         │ if round >= max_retries:    │
                         │   熔断 → Step 5             │
                         │ elif 仍有失败:               │
                         │   回到 Step 2               │
                         │ else (全过):                │
                         │   → Step 5                  │
                         └─────────────┬───────────────┘
                                       │
                                       ▼
              ┌────────────────────────────────────────┐
              │ STEP 5: ui-report-generator 最终报告   │
              │   Bash → generate_report.py            │
              │     --junit-xml report.xml             │
              │     --exec-json report.json            │
              │     --diagnose-md ui_repair_report.md  │
              │     --artifacts-dir ./test-results/artifacts │
              │     --browser-env-json browser_env.json│
              │     --output ./test-results/ui_test_report.html│
              │     --auto-allure                      │
              └────────────────────────────────────────┘
```

### 4.2 失败兜底（达到 max_retries 仍有失败）

- **仍然进入 Step 5 生成报告**（不退出）
- 在 SKILL.md 里指导 Claude 在用户摘要里**明确标记**：
  - `⚠️ N 个用例经 max_retries 轮修复仍未通过（标记为「修复失败」）`
  - 列出这 N 个用例的 nodeid
- 报告里这些用例的诊断记录会显示「修复尝试 N 次，仍未通过」

### 4.3 异常分支（容错）

| 异常 | 处理 |
|------|------|
| Step 1 executor 报错（非测试失败，而是脚本异常） | 立即终止，不进入诊断；提示用户检查环境 |
| Step 2 diagnoser 报错（如 pages.yaml 不存在） | 跳过本轮诊断，直接重试执行；记入日志「诊断跳过：xxx」 |
| Step 3 重试执行报错 | 累计重试计数；如达上限则进 Step 5 兜底 |
| Step 5 report-generator 报错 | 报错退出，提示用户 `--junit-xml` 路径是否正确 |

---

## 五、参数透传契约

### 5.1 用户输入参数

**完全复用 ui-test-executor 原参数 + 新增 1 个编排参数**：

| 参数 | 来源 | 默认 | 透传去向 |
|------|------|------|---------|
| `--priority P0/P1/...` | executor | 无 | executor Step1+Step3 |
| `--tags smoke,...` | executor | 无 | executor Step1+Step3 |
| `--modules login,...` | executor | 无 | executor Step1+Step3 |
| `--browser chromium firefox` | executor | 第一个可用 | executor Step1+Step3 |
| `--headless/--no-headless` | executor | CI=true 本地=false | executor Step1+Step3 |
| `--parallel N` | executor | 1 | executor Step1+Step3 |
| `--base-url URL` | executor | 项目配置 | executor Step1+Step3 |
| `--output-dir PATH` | executor | `./test-results` | 三个子技能共用 |
| `--max-retries N` | **本 skill 新增** | 2 | 重试循环熔断 |
| `--project-dir PATH` | diagnoser | cwd | diagnoser Step2 |
| `--pages-yaml PATH` | diagnoser | `<project>/pages.yaml` | diagnoser Step2 |
| `--title STR` | report-generator | "UI 自动化测试报告" | report Step5 |
| `--auto-allure` | report-generator | 开 | report Step5 |

### 5.2 子技能间产物传递（固定路径约定）

```
test-results/                         ← 所有子技能的统一工作目录
├── report.xml                        ← executor 产出，diagnoser + report-generator 消费
├── report.json                       ← executor 产出，report-generator 消费（exec-json）
├── browser_env.json                  ← executor 产出（detect_browsers），report-generator 消费
├── failure_analysis.md               ← executor 产出（自动），可读但不传递
├── ui_repair_report.md               ← diagnoser 产出，report-generator 消费（diagnose-md）
├── artifacts/                        ← executor 产出，diagnoser + report-generator 消费
│   ├── screenshots/
│   ├── page-source/
│   ├── console-logs/
│   ├── pytest-raw/<slug>/{trace.zip, video.webm}
│   └── failure-context/<slug>.json   ← diagnoser 消费（精确定位）
└── ui_test_report.html               ← report-generator 最终产出
```

**关键**：所有子技能的 `--output-dir` / `--artifacts-dir` / `--junit-xml` 等 path 参数**都指向同一个 `test-results/` 树**，无需复制或传递文件。

---

## 六、SKILL.md 章节结构

对齐 api-pipeline-scheduler 风格：

1. **frontmatter**：`name: ui-pipeline-scheduler` + `description`（含触发关键词：UI 自动化全流程/一键/pipeline/编排/闭环）
2. **技能定位**：编排入口 + 与三子技能边界
3. **触发场景**：应触发（"跑完整 UI 流程"、"一键全跑"、"自动修复重试"）+ 不应触发（单步调试 → 调对应子技能）
4. **工作流程**：
   - Step 0：定位 Python 解释器 + 检查被测项目结构
   - Step 1：执行首轮 + 收集产物
   - Step 2：解析 JUnit XML 判断失败数
   - Step 3：失败时进入 diagnose → 修复 → 重试循环
   - Step 4：熔断 / 全过 → 进入报告
   - Step 5：生成最终报告 + 用户摘要
5. **参数透传表**：5.1 那张表
6. **失败兜底逻辑**：4.2 + 4.3
7. **用户摘要模板**：emoji + 多行 step_details
8. **约束规则**：禁止修改子技能 / 严格串行 / 参数透传 / 幂等 / 日志追溯

---

## 七、用户摘要模板

````
🎬 UI 自动化全流程执行完成 · pipeline_id=ui-<timestamp>

[Step 1] 执行测试 ✅ 8/10 通过 · 2 失败 (285.3s)
[Step 2] 失败诊断 ✅ 2 个用例已修复（locator × 1 / timeout × 1）(45.2s)
[Step 3] 重试执行 1/2 ✅ 1/2 通过 · 1 仍失败 (62.8s)
[Step 4] 失败诊断 ✅ 0 个用例修复成功 (38.1s)
[Step 5] 重试执行 2/2 ⚠️ 1 个仍失败（已达 max_retries=2，熔断）(58.4s)
[Step 6] 生成报告 ✅ test-results/ui_test_report.html (1.2s)

📊 最终结果：9/10 通过（90%）· 累计耗时 491.0s
⚠️ 修复失败用例（1 个）：
  - tests/auth/test_login.py::TestLogin::test_invalid_password

🌐 Allure 报告：http://localhost:8088
📁 完整报告：test-results/ui_test_report.html
````

---

## 八、不做清单（明确边界）

本 skill **不做**：

- ❌ 实现任何测试执行 / 诊断 / 渲染逻辑（全部由子技能完成）
- ❌ 修改子技能的 SKILL.md / scripts / 入参 / 出参
- ❌ 自动安装依赖（pytest、playwright、allure 由用户预先准备）
- ❌ 跨项目复用配置（每次执行基于当前 cwd）
- ❌ 持久化执行历史（如需趋势图由 ui-report-generator --history-json 自行管理）

---

## 九、验收标准

- [ ] SKILL.md 编排流程能跑通 3 子技能串联（执行 → 诊断 → 报告）
- [ ] 失败用例触发自动诊断 + 重试循环
- [ ] 重试范围精准（只跑失败 nodeid）
- [ ] 熔断生效（max_retries 达上限后不再循环）
- [ ] 失败兜底（达上限仍生成报告，标记「修复失败」）
- [ ] 通过用例（首轮全过）跳过诊断直接生成报告
- [ ] 三个子技能仍可单独调用，不受影响

---

## 十、风险与权衡

| 风险 | 缓解 |
|------|------|
| `-k "nid1 or nid2"` 表达式过长（nodeid 含 `::`、`[]`） | 用 pytest 原生 `-k` 子串匹配（如 `test_login_invalid or test_register_xxx`），避免完整 nodeid |
| 重试时 report.xml 被覆盖，丢失首轮失败现场 | 实现层用 `cp report.xml report-round-N.xml` 留档；最终报告用最后一轮的 xml |
| diagnoser 修改脚本后重试仍失败（修复无效） | 不视为异常；继续下一轮或熔断 |
| 多轮重试时长膨胀 | max_retries 默认 2，CI 场景建议设为 1 |

---

## 十一、下一步

1. 用户 review 本 spec
2. 通过后 → 进入 writing-plans 阶段，写实施计划
3. 实施计划完成 → 进入 executing-plans 阶段，按 Task 落地 SKILL.md + references/
