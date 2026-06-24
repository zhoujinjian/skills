# ui-pipeline-scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 ui-pipeline-scheduler skill，作为 UI 自动化全流程统一编排入口，纯 SKILL.md 编排串联 ui-test-executor → ui-failure-diagnoser → ui-report-generator 三子技能，含失败诊断+重试循环+熔断兜底。

**Architecture:** 单文件 SKILL.md 编排（无 scripts/），对齐 api-pipeline-scheduler 模板。Claude 按 SKILL.md 剧本手动调子技能 CLI；所有子技能的 `--output-dir / --artifacts-dir` 都指向同一个 `./test-results/`，无需复制文件。

**Tech Stack:** Markdown SKILL.md（frontmatter + 章节正文）+ references/ 辅助文档；零代码；端到端验收依赖 `~/.claude/skills/shop-lab-ui-test/` 测试项目。

---

## File Structure

实施完毕后的目录树：

```
~/.claude/skills/ui-pipeline-scheduler/
├── SKILL.md                              # 唯一编排入口
├── docs/
│   ├── specs/
│   │   └── 2026-06-24-ui-pipeline-scheduler-design.md  # 已存在
│   └── plans/
│       └── 2026-06-24-implementation.md  # 本计划
└── references/
    ├── pipeline_flow.md                  # 详细流程图（含重试循环、失败兜底分支）
    └── param_passing.md                  # 参数透传契约表
```

**文件职责**：

- `SKILL.md`：核心编排剧本。章节顺序固定：frontmatter → 技能定位 → 触发场景 → 工作流程 Step 0-5 → 参数透传表 → 失败兜底 → 用户摘要模板 → 约束规则。所有 CLI 命令、路径、判断逻辑都在这里。
- `references/pipeline_flow.md`：详细流程图（ASCII art）+ 重试循环每一步的产物变化 + 失败兜底分支说明。SKILL.md 在 Step 3-4 复杂分支处引用本文件。
- `references/param_passing.md`：参数透传契约表（用户输入 → 哪个子技能消费）+ 子技能间产物路径约定。SKILL.md 在「参数透传表」章节引用本文件作为详细版。

**无 scripts/ 目录**——这是架构决策（spec 章节二），所有编排逻辑由 Claude 按 SKILL.md 执行。

---

## Task 1: 创建 SKILL.md 骨架（frontmatter + 技能定位 + 触发场景）

**Files:**
- Create: `~/.claude/skills/ui-pipeline-scheduler/SKILL.md`

- [ ] **Step 1: 写 SKILL.md 的 frontmatter + 技能定位章节**

把以下内容写入 `~/.claude/skills/ui-pipeline-scheduler/SKILL.md`：

```markdown
---
name: ui-pipeline-scheduler
description: WEB UI 自动化测试全链路统一编排入口。负责把 ui-test-executor（执行）→ ui-failure-diagnoser（诊断修复）→ ui-test-executor（重试）→ ui-report-generator（报告）四个阶段自动串联成闭环，含失败诊断+智能重试+熔断兜底。当用户需要"一键全跑 UI 自动化"、"自动修复失败用例并重试"、"端到端 UI 测试流水线"、"全流程闭环"、"UI 自动化 pipeline"时触发本技能。本技能不替代任何子技能，仅做流程编排与参数透传，三个子技能仍可独立调用。
---

# ui-pipeline-scheduler — UI 自动化全链路统一编排入口

## 技能定位

把三个独立 skill 串成**执行 → 诊断 → 重试 → 报告**的完整闭环：

```
ui-test-executor  →  ui-failure-diagnoser  →  ui-test-executor（重试）  →  ui-report-generator
   执行入口              仅失败时触发              循环 max_retries 次        始终生成
```

**核心原则（硬约束）**：

1. **零侵入**：禁止修改 ui-test-executor / ui-failure-diagnoser / ui-report-generator 任何代码、入参、出参、调用方式
2. **纯编排**：本 skill 只负责流程串联、条件判断、循环调度、失败兜底
3. **双模式兼容**：子技能可单独手动调用，也可被本 skill 自动串联

**与子技能的边界**：

| 子技能 | 调用方式 | 本 skill 是否干预内部 |
|--------|---------|----------------------|
| ui-test-executor | `execute_tests.py` CLI | 否，仅传参 + 读产物 |
| ui-failure-diagnoser | `diagnose.py` CLI | 否，仅传参 + 读产物 |
| ui-report-generator | `generate_report.py` CLI | 否，仅传参 + 读产物 |

---

## 触发场景

**应当触发本技能的关键词**：

- "一键全跑 UI 自动化"、"跑完整 UI 流程"、"UI 全流程闭环"
- "UI 自动化 pipeline"、"UI pipeline"、"编排 UI 测试"
- "自动修复失败用例并重试"、"失败自动诊断重跑"
- "跑 UI 测试 + 自动诊断 + 生成报告"
- "端到端 UI 测试流水线"

**不应当触发（应直接调子技能）**：

- 单纯跑测试不要报告 → ui-test-executor
- 单独诊断已有失败 → ui-failure-diagnoser
- 单独生成报告（已有 JUnit XML）→ ui-report-generator
- 编写新测试脚本 → ui-testscript-generator
- 给脚本打标签 → ui-test-tagger

---

## 工作流程

（后续 Task 2-6 会填充 Step 0 ~ Step 5 的具体内容）
```

- [ ] **Step 2: 自检文件已创建**

Run: `head -10 ~/.claude/skills/ui-pipeline-scheduler/SKILL.md`
Expected: 看到 frontmatter `name: ui-pipeline-scheduler` 和章节标题

---

## Task 2: SKILL.md 工作流程 Step 0-1（解释器定位 + 首轮执行）

**Files:**
- Modify: `~/.claude/skills/ui-pipeline-scheduler/SKILL.md`（替换"工作流程"占位段为真正的 Step 0-1）

- [ ] **Step 1: 在 SKILL.md 末尾追加工作流程 Step 0-1 内容**

把 SKILL.md 末尾的 `（后续 Task 2-6 会填充 Step 0 ~ Step 5 的具体内容）` 占位行替换为以下完整内容：

```markdown
### Step 0：定位 Python 解释器 + 检查项目结构

**Python 解释器优先级**：

1. 项目虚拟环境：`<project>/.venv/bin/python` 或 `<project>/venv/bin/python`
2. 已知内部环境：`/Users/zhoujinjian/.workbuddy/binaries/python/envs/default/bin/python3`
3. 全局 `python3`

**项目结构检查**（必做）：

- 确认 `<project>/tests/` 目录存在
- 确认 `<project>/pages/` 目录存在（POM 项目，diagnoser 需要）
- 确认 `<project>/pages.yaml` 存在（diagnoser 的 LOCATOR 金标准）
- 确认 `<project>/tests/conftest.py` 存在（pytest-playwright 配置）

如缺失，提示用户先调对应子技能初始化。

### Step 1：ui-test-executor 首轮执行

**输入**：用户参数（priority/tags/modules/browser/headless/parallel/base-url/output-dir）+ Step 0 确认的 Python 解释器。

**执行命令模板**（参数按用户输入填充，未指定的跳过）：

```bash
$PYTHON ~/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
    --priority <P0|P1|P2> \
    --tags <tag1,tag2,...> \
    --modules <module1,module2,...> \
    --browser <chromium|firefox|webkit> \
    --headless \
    --parallel <N> \
    --base-url <URL> \
    --output-dir ./test-results \
    --allure
```

**首轮产物**（统一在 `./test-results/`）：

| 文件 | 用途 | 后续消费方 |
|------|------|-----------|
| `report.xml` | JUnit XML | Step 2 解析 + diagnoser + report-generator |
| `report.json` | 结构化结果 | report-generator（--exec-json） |
| `browser_env.json` | 浏览器清单 | report-generator（--browser-env-json） |
| `artifacts/screenshots/` | 失败截图 | report-generator（内联 base64） |
| `artifacts/page-source/` | DOM 快照 | report-generator（外链） |
| `artifacts/console-logs/` | 浏览器日志 | report-generator（外链） |
| `artifacts/pytest-raw/<slug>/{trace.zip,video.webm}` | 录屏+Trace | report-generator（外链） |
| `failure_analysis.md` | 失败初步分析 | 可读但不传递 |

**首轮备份**（避免后续重试覆盖首轮现场）：

```bash
cp ./test-results/report.xml ./test-results/report-round-0.xml
```

**首轮失败统计**（从 report.xml 提取）：

- 用 Python 解析 `<testsuite failures="N" errors="M">`，得到首轮失败数 `first_round_failures = N + M`
- 若 `first_round_failures == 0`：跳过 Step 2-4，直接进 Step 5（生成报告）
- 若 `first_round_failures > 0`：进入 Step 2 诊断循环

```

- [ ] **Step 2: 自检 Step 0-1 已追加**

Run: `grep -c "Step 0\|Step 1" ~/.claude/skills/ui-pipeline-scheduler/SKILL.md`
Expected: 至少 2（Step 0 + Step 1 各一处章节标题）

---

## Task 3: SKILL.md 工作流程 Step 2（失败诊断循环启动 + JUnit XML 解析）

**Files:**
- Modify: `~/.claude/skills/ui-pipeline-scheduler/SKILL.md`（在 Step 1 后追加 Step 2）

- [ ] **Step 1: 在 Step 1 章节后追加 Step 2 内容**

在 SKILL.md 的 Step 1 章节末尾（"进入 Step 2 诊断循环" 那行之后）追加：

```markdown
### Step 2：调用 ui-failure-diagnoser 诊断 + 自动修复

**触发条件**：首轮或上一轮重试后 `report.xml` 的 `failures + errors > 0`。

**执行命令**：

```bash
$PYTHON ~/.claude/skills/ui-failure-diagnoser/scripts/diagnose.py \
    --junit-xml ./test-results/report.xml \
    --artifacts-dir ./test-results/artifacts \
    --project-dir <项目根> \
    --pages-yaml <项目根>/pages.yaml \
    --output ./test-results/ui_repair_report.md \
    --verify \
    --base-url <同 Step 1> \
    --browser <同 Step 1>
```

**产物**：

| 文件 | 用途 | 后续消费方 |
|------|------|-----------|
| `test-results/ui_repair_report.md` | 诊断报告（6 类分类 + 14 种根因） | report-generator（--diagnose-md） |
| `pages/**/*.py`（含 `.bak`） | AST 修复的 locator/timeout/iframe | Step 3 重试时生效 |
| `tests/conftest.py` | bug_repair 注入的 xfail/flaky marker | Step 3 重试时生效 |

**诊断结果解析**（从 ui_repair_report.md 提取）：

- 统计本轮修复的用例数 `fixed_this_round`
- 若 `fixed_this_round == 0`：修复无效，直接熔断进 Step 5（避免无意义重试）

**容错**：

- 若 diagnoser 报错（如 pages.yaml 不存在）：跳过本轮诊断，记日志「诊断跳过：xxx」，仍进 Step 3 重试（用未修复的脚本重跑，可能因 flaky 通过）
- 若 diagnoser 退出码非 0 但有 ui_repair_report.md：按修复成功处理，进 Step 3

```

- [ ] **Step 2: 自检 Step 2 已追加**

Run: `grep -c "Step 2" ~/.claude/skills/ui-pipeline-scheduler/SKILL.md`
Expected: 至少 2（章节标题 + Step 1 末尾的引用）

---

## Task 4: SKILL.md 工作流程 Step 3-4（重试执行 + 熔断判断）

**Files:**
- Modify: `~/.claude/skills/ui-pipeline-scheduler/SKILL.md`（在 Step 2 后追加 Step 3 + Step 4）

- [ ] **Step 1: 在 Step 2 章节后追加 Step 3 + Step 4 内容**

追加：

```markdown
### Step 3：ui-test-executor 重试执行（只跑失败用例）

**触发条件**：Step 2 诊断完成（无论是否修复成功），且未达 `max_retries` 上限。

**提取失败 nodeid 列表**（从当前 report.xml）：

```bash
# 用 Python one-liner 提取失败用例的方法名（去参数化方括号内容，避免 -k 表达式过长）
$PYTHON -c "
import xml.etree.ElementTree as ET
tree = ET.parse('./test-results/report.xml')
failed = []
for tc in tree.iter('testcase'):
    if tc.find('failure') is not None or tc.find('error') is not None:
        # 取方法名最后一段，去参数化
        name = tc.get('name', '').split('[')[0]
        if name: failed.append(name)
# 去重
failed = sorted(set(failed))
print(' or '.join(failed))
"
```

输出形如：`test_login_invalid or test_register_missing_field or test_search_no_result`

**重试执行命令**（用 `-k` 精准筛选）：

```bash
$PYTHON ~/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
    --keyword "<上面提取的表达式>" \
    --browser <同 Step 1> \
    --headless <同 Step 1> \
    --base-url <同 Step 1> \
    --output-dir ./test-results \
    --allure
```

**注意**：

- 重试时**不再传 --priority / --tags / --modules**（避免和 --keyword 叠加导致漏跑）
- 重试结果**覆盖** `./test-results/report.xml`（report-generator 最终用的是最后一轮的 xml）
- 重试前备份当前 xml：`cp ./test-results/report.xml ./test-results/report-round-N.xml`（N = 当前轮次）

**重试后判断**：

- 解析新 report.xml 的 `failures + errors`
- 若 `== 0`：全过，跳出循环，进 Step 5
- 若 `> 0`：进入 Step 4 判断是否继续循环

### Step 4：熔断判断 + 循环控制

**循环计数**：维护 `round = 0, 1, 2, ...`（round=0 是首轮，round≥1 是重试）

**熔断条件**（满足任一即跳出循环，进 Step 5）：

1. `round >= max_retries`（默认 max_retries=2，即最多 2 轮重试）
2. 上一轮 Step 2 诊断 `fixed_this_round == 0`（修复无效）
3. 当前轮 `failures + errors == 0`（全过）

**未熔断时**：`round += 1`，回到 Step 2 继续诊断-修复-重试。

**熔断后**：

- 若仍有失败：在用户摘要中标记 ⚠️「N 个用例经 max_retries 轮修复仍未通过」，并列出 nodeid
- 进 Step 5 生成最终报告（失败用例的诊断记录显示「修复尝试 K 次，仍未通过」）

```

- [ ] **Step 2: 自检 Step 3-4 已追加**

Run: `grep -c "Step 3\|Step 4" ~/.claude/skills/ui-pipeline-scheduler/SKILL.md`
Expected: 至少 4

---

## Task 5: SKILL.md 工作流程 Step 5（最终报告生成）

**Files:**
- Modify: `~/.claude/skills/ui-pipeline-scheduler/SKILL.md`（在 Step 4 后追加 Step 5）

- [ ] **Step 1: 在 Step 4 章节后追加 Step 5 内容**

追加：

```markdown
### Step 5：ui-report-generator 最终报告

**触发条件**：无论是否经过重试循环，**始终执行**（包括首轮全过的场景）。

**执行命令**（融合所有子技能产物）：

```bash
$PYTHON ~/.claude/skills/ui-report-generator/scripts/generate_report.py \
    --junit-xml ./test-results/report.xml \
    --exec-json ./test-results/report.json \
    --diagnose-md ./test-results/ui_repair_report.md \
    --artifacts-dir ./test-results/artifacts \
    --browser-env-json ./test-results/browser_env.json \
    --output ./test-results/ui_test_report.html \
    --title "<用户指定或默认 'UI 自动化测试报告'>" \
    --auto-allure
```

**参数说明**：

- `--junit-xml`：**始终用最后一轮的 report.xml**（即当前 ./test-results/report.xml，已被最后一轮覆盖）
- `--exec-json`：来自 Step 1 的 executor 产出（如多轮执行后被覆盖，用最后一轮的）
- `--diagnose-md`：来自 Step 2 的 diagnoser 产出（若首轮全过未触发 diagnoser，**省略此参数**）
- `--artifacts-dir`：累积所有轮次的 artifacts（executor 默认 append 模式）
- `--auto-allure`：自动探测 Allure 服务（由 Step 1 的 `--allure` 已启动）

**首轮全过场景的精简命令**（无 --diagnose-md）：

```bash
$PYTHON ~/.claude/skills/ui-report-generator/scripts/generate_report.py \
    --junit-xml ./test-results/report.xml \
    --artifacts-dir ./test-results/artifacts \
    --browser-env-json ./test-results/browser_env.json \
    --output ./test-results/ui_test_report.html \
    --auto-allure
```

**最终产物**：

| 文件 | 用途 |
|------|------|
| `test-results/ui_test_report.html` | 单文件可视化报告（含截图/录屏/Trace/诊断记录） |
| `test-results/report-round-0.xml ~ report-round-N.xml` | 每轮 JUnit XML 留档（追溯用） |

**报告打开**：

```bash
open ./test-results/ui_test_report.html
```

```

- [ ] **Step 2: 自检 Step 5 已追加**

Run: `grep -c "Step 5" ~/.claude/skills/ui-pipeline-scheduler/SKILL.md`
Expected: 至少 2（章节 + Step 4 末尾引用）

---

## Task 6: SKILL.md 参数透传表 + 用户摘要模板 + 约束规则

**Files:**
- Modify: `~/.claude/skills/ui-pipeline-scheduler/SKILL.md`（在 Step 5 后追加最后三个章节）

- [ ] **Step 1: 在 Step 5 章节后追加「参数透传表 + 用户摘要模板 + 约束规则」**

追加：

```markdown
---

## 参数透传表

完整契约详见 `references/param_passing.md`。简表：

| 参数 | 默认 | 透传去向 |
|------|------|---------|
| `--priority P0/P1/...` | 无 | executor Step1 + Step3 |
| `--tags smoke,...` | 无 | executor Step1 + Step3 |
| `--modules login,...` | 无 | executor Step1 + Step3 |
| `--browser chromium firefox` | 第一个可用 | executor Step1 + Step3 |
| `--headless / --no-headless` | CI=true 本地=false | executor Step1 + Step3 |
| `--parallel N` | 1 | executor Step1 + Step3 |
| `--base-url URL` | 项目配置 | executor Step1 + Step3 + diagnoser |
| `--output-dir PATH` | `./test-results` | 三个子技能共用 |
| `--max-retries N` | 2 | **本 skill 编排参数**，控制 Step 3-4 循环 |
| `--project-dir PATH` | cwd | diagnoser Step2 |
| `--pages-yaml PATH` | `<project>/pages.yaml` | diagnoser Step2 |
| `--title STR` | "UI 自动化测试报告" | report-generator Step5 |
| `--auto-allure` | 开 | report-generator Step5 |

**关键**：所有子技能的 path 参数都指向同一个 `./test-results/` 树，无需复制文件。

---

## 失败兜底逻辑

**熔断后仍生成报告**：

- 达到 `max_retries` 上限仍有失败 → **不退出**，进 Step 5 生成最终报告
- 报告里这些用例的诊断记录显示「修复尝试 K 次，仍未通过」
- 用户摘要明确标记 ⚠️ 修复失败用例 nodeid

**异常分支容错**（详见 `references/pipeline_flow.md`）：

| 异常 | 处理 |
|------|------|
| Step 1 executor 脚本异常（非测试失败） | 立即终止，不进诊断 |
| Step 2 diagnoser 报错（pages.yaml 缺失等） | 跳过本轮诊断，直接重试 |
| Step 3 重试报错 | 计入重试轮次；达上限则兜底 |
| Step 5 report-generator 报错 | 报错退出，提示 JUnit XML 路径 |

---

## 用户摘要模板

执行结束后，向用户呈现如下格式摘要：

```
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
```

**首轮全过场景的精简摘要**：

```
🎬 UI 自动化全流程执行完成 · pipeline_id=ui-<timestamp>

[Step 1] 执行测试 ✅ 10/10 通过（100%）(285.3s)
[Step 2] 生成报告 ✅ test-results/ui_test_report.html (1.2s)

📊 最终结果：10/10 通过 · 耗时 286.5s
🌐 Allure 报告：http://localhost:8088
📁 完整报告：test-results/ui_test_report.html
```

---

## 约束规则

1. **严格串行**：Step 1 → 2 → 3 → 4 → 5，禁止并行子技能
2. **零侵入**：禁止修改任何子技能的 SKILL.md / scripts / 入参 / 出参
3. **参数透传**：用户的 executor 参数原样传给 Step 1 + Step 3，不做转换
4. **幂等**：重复执行 pipeline 时，先清空 `./test-results/` 或用新目录
5. **日志追溯**：每轮的 report.xml 备份为 `report-round-N.xml`，可追溯每轮失败现场
6. **熔断优先**：达 `max_retries` 上限立即跳出循环，不死循环
7. **始终生成报告**：无论失败与否，Step 5 必须执行
```

- [ ] **Step 2: 自检三个章节已追加**

Run: `grep -c "参数透传表\|用户摘要模板\|约束规则" ~/.claude/skills/ui-pipeline-scheduler/SKILL.md`
Expected: 3

---

## Task 7: 创建 references/pipeline_flow.md（详细流程图）

**Files:**
- Create: `~/.claude/skills/ui-pipeline-scheduler/references/pipeline_flow.md`

- [ ] **Step 1: 写 pipeline_flow.md**

把以下内容写入 `references/pipeline_flow.md`：

```markdown
# ui-pipeline-scheduler 详细流程图

> SKILL.md 的 Step 0-5 简化版流程，本文件提供详细分支与产物变化。

## 完整流程图（含重试循环 + 失败兜底）

```
START
  │
  ▼
Step 0: 定位 Python + 检查项目结构
  │     产物：PYTHON=<解释器路径>
  │     校验：tests/、pages/、pages.yaml、tests/conftest.py
  │
  ▼
Step 1: ui-test-executor 首轮执行（round=0）
  │     命令：execute_tests.py tests/ --priority --tags ... --output-dir ./test-results --allure
  │     产物：report.xml, report.json, browser_env.json, artifacts/, failure_analysis.md
  │     备份：cp report.xml report-round-0.xml
  │     解析：first_round_failures = failures + errors
  │
  ├── first_round_failures == 0 ──────────────────────────────┐
  │                                                           │
  │   跳过 Step 2-4                                            │
  │                                                           │
  ▼                                                           │
Step 2: ui-failure-diagnoser 诊断（仅 failures > 0 时）        │
  │     命令：diagnose.py --junit-xml --artifacts-dir          │
  │              --project-dir --pages-yaml --verify           │
  │     产物：ui_repair_report.md, pages/**/*.py（修复）       │
  │     解析：fixed_this_round                                 │
  │                                                           │
  ├── fixed_this_round == 0 ── 修复无效熔断 ──────────────────┤
  │                                                           │
  ▼                                                           │
Step 3: ui-test-executor 重试执行（只跑失败用例）              │
  │     1. Python one-liner 提取失败 nodeid                    │
  │     2. execute_tests.py tests/ -k "name1 or name2 ..."     │
  │     3. 备份：cp report.xml report-round-N.xml              │
  │     解析：current_failures = failures + errors             │
  │                                                           │
  ├── current_failures == 0 ── 全过跳出 ──────────────────────┤
  │                                                           │
  ▼                                                           │
Step 4: 熔断判断                                               │
  │     条件：round >= max_retries                             │
  │     或   current_failures == 0                             │
  │     或   fixed_this_round == 0                             │
  │                                                           │
  ├── 未熔断 ── round += 1, 回 Step 2                          │
  │                                                           │
  ▼                                                           │
Step 5: ui-report-generator 最终报告  ◀───────────────────────┘
  │     命令：generate_report.py --junit-xml --exec-json
  │              --diagnose-md --artifacts-dir --browser-env-json
  │              --output ./test-results/ui_test_report.html --auto-allure
  │     产物：ui_test_report.html
  │
  ▼
END: open ./test-results/ui_test_report.html
```

## 每轮产物变化

| 轮次 | report.xml 来源 | ui_repair_report.md | report-round-N.xml |
|------|----------------|---------------------|---------------------|
| round=0 | executor 首轮 | 不存在 | report-round-0.xml 备份 |
| round=1 | executor 重试1 | diagnoser 第1次产出 | report-round-1.xml 备份 |
| round=2 | executor 重试2 | diagnoser 第2次产出（覆盖） | report-round-2.xml 备份 |
| 最终 | 最后一轮的 xml | 最后一次 diagnoser 产出 | 全部留档 |

**report-generator 用的 xml**：始终是 `./test-results/report.xml`（已被最后一轮覆盖）。

## 失败兜底分支

### 分支 A：首轮全过

```
Step 1 → 跳过 Step 2-4 → Step 5
```

精简版 Step 5 命令（无 --diagnose-md）。

### 分支 B：达 max_retries 仍有失败

```
Step 1 → Step 2 → Step 3 → Step 4 (熔断) → Step 5
```

Step 5 正常执行；用户摘要标记 ⚠️ 修复失败用例；报告里这些用例显示「修复尝试 K 次，仍未通过」。

### 分支 C：diagnoser 修复无效（fixed_this_round == 0）

```
Step 1 → Step 2 → Step 4 (熔断) → Step 5
```

跳过 Step 3 重试（修复无效，重试无意义）；直接进 Step 5。

### 分支 D：diagnoser 异常（pages.yaml 缺失等）

```
Step 1 → Step 2 (异常) → Step 3 (用未修复脚本重试) → Step 4 → ...
```

记日志「诊断跳过：xxx」；进 Step 3 用原脚本重试（可能因 flaky 通过）。

## 关键时序约束

1. **Step 2 必须在 Step 1 之后**：依赖首轮 report.xml + artifacts
2. **Step 3 必须在 Step 2 之后**：依赖 diagnoser 修复的脚本（即使修复无效也走流程）
3. **Step 5 必须在所有循环结束后**：避免多轮报告互相覆盖
4. **Allure 服务在 Step 1 启动**（通过 executor 的 `--allure`），Step 5 直接 `--auto-allure` 复用

## 边界 case

### Case 1：用户 `--max-retries 0`

等价于「不重试，只执行 + 诊断 + 报告」：
```
Step 1 → Step 2 → Step 5（跳过 Step 3-4）
```

### Case 2：首轮执行异常（非测试失败）

executor 退出码非 0 且 report.xml 不存在或为空 → 立即终止，不进 Step 2。提示用户：
- 检查 Python 解释器
- 检查 tests/ 目录
- 检查 playwright 安装

### Case 3：重试时 `-k` 表达式过长

nodeid 含 `::`、`[]` 会让 `-k` 表达式超长。**对策**：提取时只取方法名（去参数化方括号），用方法名做 `-k` 子串匹配。

### Case 4：多浏览器矩阵的重试

首轮 `--browser chromium firefox` 跑出失败时，重试**保留多浏览器**（`-k` 筛选不指定浏览器，pytest-playwright 自动展开矩阵）。
```

- [ ] **Step 2: 自检文件已创建**

Run: `head -5 ~/.claude/skills/ui-pipeline-scheduler/references/pipeline_flow.md`
Expected: 看到 `# ui-pipeline-scheduler 详细流程图` 标题

---

## Task 8: 创建 references/param_passing.md（参数透传契约表）

**Files:**
- Create: `~/.claude/skills/ui-pipeline-scheduler/references/param_passing.md`

- [ ] **Step 1: 写 param_passing.md**

把以下内容写入 `references/param_passing.md`：

```markdown
# ui-pipeline-scheduler 参数透传契约

> SKILL.md 的「参数透传表」简表，本文件提供详细版（含每子技能的完整 CLI 签名）。

## 用户输入参数 → 子技能映射

| 用户参数 | 类型 | 默认 | 透传至 | 子技能原始参数名 |
|---------|------|------|--------|-----------------|
| `--priority` | enum (P0/P1/P2/P3) | 无 | executor | `--priority` |
| `--tags` | list | 无 | executor | `--tags` |
| `--modules` | list | 无 | executor | `--modules` |
| `--keyword / -k` | str | 无 | executor（首轮） | `-k`（**重试时由 pipeline 自动覆盖**） |
| `--browser` | list | 第一个可用 | executor | `--browser` |
| `--headless / --no-headless` | flag | CI=true 本地=false | executor | `--headless` / `--no-headless` |
| `--parallel / -n` | int | 1 | executor | `--parallel` |
| `--dist` | enum | loadscope | executor | `--dist` |
| `--retry` | int | 0 | executor | `--retry`（pytest-rerunfailures 级别，**与 pipeline 的 max_retries 不同**） |
| `--base-url` | str | 项目配置 | executor + diagnoser | executor `--base-url`；diagnoser `--base-url` |
| `--output-dir` | path | `./test-results` | 三子技能 | executor `--output-dir`；diagnoser 通过 artifacts-dir 推断；report-generator 通过 --output 文件名 |
| `--max-retries` | int | 2 | **pipeline 内部** | 不透传，控制 Step 3-4 循环 |
| `--project-dir` | path | cwd | diagnoser | `--project-dir` |
| `--pages-yaml` | path | `<project>/pages.yaml` | diagnoser | `--pages-yaml` |
| `--title` | str | "UI 自动化测试报告" | report-generator | `--title` |
| `--auto-allure` | flag | 开 | report-generator | `--auto-allure` |
| `--no-auto-open-traces` | flag | 关 | report-generator | `--no-auto-open-traces` |

## 子技能间产物传递（固定路径约定）

```
./test-results/                              ← 所有子技能的统一工作目录
├── report.xml                               ← executor 产出，diagnoser + report-generator 消费
├── report-pre.xml                           ← executor 前置阶段（如有）
├── report.json                              ← executor 产出，report-generator 消费（--exec-json）
├── browser_env.json                         ← executor 产出（detect_browsers），report-generator 消费
├── failure_analysis.md                      ← executor 自动产出（可读但不传递）
├── ui_repair_report.md                      ← diagnoser 产出，report-generator 消费（--diagnose-md）
├── ui_test_report.html                      ← report-generator 最终产出
├── report-round-0.xml ~ report-round-N.xml  ← pipeline 内部备份，追溯每轮失败现场
├── allure-results/                          ← executor 产出（--allure），allure generate 消费
├── allure-report/                           ← allure generate 产出
├── allure_url.txt                           ← allure open URL，report-generator --auto-allure 消费
└── artifacts/                               ← executor 产出，diagnoser + report-generator 消费
    ├── screenshots/                         ← 失败截图（conftest flat）
    ├── page-source/                         ← 失败 DOM 快照
    ├── console-logs/                        ← 失败浏览器日志（5 段合并）
    ├── pytest-raw/<slug>/                   ← pytest-playwright 原生产物
    │   ├── trace.zip
    │   ├── video.webm
    │   └── test-failed-N.png
    ├── failure-context/<slug>.json          ← conftest 落的 sidecar，diagnoser 消费
    ├── videos/ traces/ har/                 ← 保留目录，原生实际在 pytest-raw/
```

## 子技能完整 CLI 签名（透传时参考）

### ui-test-executor/scripts/execute_tests.py（首轮 + 重试）

```bash
$PYTHON execute_tests.py tests/ \
    [--priority P0|P1|P2|P3] \
    [--tags tag1,tag2] \
    [--modules mod1,mod2] \
    [--keyword EXPR] [-k EXPR] \
    [--browser chromium firefox webkit] \
    [--headless | --no-headless] \
    [--parallel N] [-n N] \
    [--dist load|loadscope|loadfile] \
    [--retry N] \
    [--timeout SEC] \
    [--base-url URL] \
    [--output-dir ./test-results] \
    [--allure] \
    [--no-allure-open] \
    [--dry-run] \
    [--list-only]
```

### ui-failure-diagnoser/scripts/diagnose.py（仅失败时触发）

```bash
$PYTHON diagnose.py \
    --junit-xml ./test-results/report.xml \
    --artifacts-dir ./test-results/artifacts \
    --project-dir <项目根> \
    [--conftest <项目根>/tests/conftest.py] \
    [--pages-yaml <项目根>/pages.yaml] \
    [--output ./test-results/ui_repair_report.md] \
    [--audit-log ./.ui-failure-diagnoser/audit.log] \
    [--no-fix] \
    [--dry-run] \
    [--verify] \
    [--base-url URL] \
    [--browser chromium]
```

### ui-report-generator/scripts/generate_report.py（最终）

```bash
$PYTHON generate_report.py \
    --junit-xml ./test-results/report.xml \
    [--exec-json ./test-results/report.json] \
    [--diagnose-md ./test-results/ui_repair_report.md] \
    [--artifacts-dir ./test-results/artifacts] \
    [--browser-env-json ./test-results/browser_env.json] \
    [--history-json history.json] \
    [--output ./test-results/ui_test_report.html] \
    [--title "..."] \
    [--trace-launch-cmd "..."] \
    [--no-inline-screenshots] \
    [--allure-url URL] \
    [--allure-url-file PATH] \
    [--auto-allure] \
    [--no-allure] \
    [--no-auto-open-traces]
```

## 参数透传规则

1. **首轮全量参数**：用户传给 executor 的 priority/tags/modules/browser/headless/parallel/base-url 全量透传
2. **重试精简参数**：重试时**只保留** browser/headless/parallel/base-url/output-dir，**移除** priority/tags/modules（避免和 -k 叠加漏跑）
3. **diagnoser 参数对齐**：base-url 和 browser 必须与 executor 一致（verify 重跑要用相同环境）
4. **report-generator 5 源融合**：--junit-xml 必填；--diagnose-md 仅在触发过 diagnoser 时传；其余按存在性自动判断
```

- [ ] **Step 2: 自检文件已创建**

Run: `head -5 ~/.claude/skills/ui-pipeline-scheduler/references/param_passing.md`
Expected: 看到 `# ui-pipeline-scheduler 参数透传契约` 标题

---

## Task 9: 端到端验收（用 shop-lab-ui-test 项目跑通完整 pipeline）

**Files:**
- 无文件修改，仅运行验证

- [ ] **Step 1: 检查被测项目可用**

Run: `curl -sS -o /dev/null -w "%{http_code}" http://localhost:3000`
Expected: `200`（shop-lab 站点在跑）

如不是 200：提示用户启动被测站点（`cd shop-lab && pnpm dev` 或类似命令）

- [ ] **Step 2: 清空旧 test-results**

Run: `cd /Users/zhoujinjian/ai_project/shop-lab-ui-test && rm -rf test-results/* && ls test-results/`
Expected: 空目录或仅有 `artifacts/` 空子目录

- [ ] **Step 3: 模拟触发 pipeline（按 SKILL.md 剧本手动走一遍）**

按 SKILL.md 工作流程 Step 0-5 顺序执行：

```bash
# Step 0：定位 Python（用已知可用解释器）
PYTHON=/Users/zhoujinjian/.workbuddy/binaries/python/envs/default/bin/python3
# 或 fallback：PYTHON=python3

# Step 1：首轮执行 P0 smoke
$PYTHON ~/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
    --priority P0 --tags run_smoke \
    --base-url http://localhost:3000 \
    --output-dir ./test-results \
    --allure

# 备份首轮 xml
cp ./test-results/report.xml ./test-results/report-round-0.xml

# Step 2：解析失败数（Python one-liner）
$PYTHON -c "
import xml.etree.ElementTree as ET
tree = ET.parse('./test-results/report.xml')
root = tree.getroot()
fails = int(root.get('failures', 0))
errs = int(root.get('errors', 0))
print(f'failures={fails} errors={errs} total={fails+errs}')
"
```

Expected: 输出形如 `failures=2 errors=0 total=2`（基于上次真实执行有 2 个 P0 smoke 失败）

- [ ] **Step 4: 触发 diagnoser（如有失败）**

```bash
$PYTHON ~/.claude/skills/ui-failure-diagnoser/scripts/diagnose.py \
    --junit-xml ./test-results/report.xml \
    --artifacts-dir ./test-results/artifacts \
    --project-dir ./ \
    --pages-yaml ./pages.yaml \
    --output ./test-results/ui_repair_report.md \
    --verify \
    --base-url http://localhost:3000 \
    --browser chromium 2>&1 | tail -20
```

Expected: 输出含「修复 N 个用例」；生成 `./test-results/ui_repair_report.md`

- [ ] **Step 5: 提取失败 nodeid + 重试执行**

```bash
KEYWORD=$($PYTHON -c "
import xml.etree.ElementTree as ET
tree = ET.parse('./test-results/report.xml')
failed = []
for tc in tree.iter('testcase'):
    if tc.find('failure') is not None or tc.find('error') is not None:
        name = tc.get('name', '').split('[')[0]
        if name: failed.append(name)
print(' or '.join(sorted(set(failed))))
")
echo "重试表达式: $KEYWORD"

$PYTHON ~/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
    --keyword "$KEYWORD" \
    --base-url http://localhost:3000 \
    --output-dir ./test-results \
    --allure 2>&1 | tail -15

cp ./test-results/report.xml ./test-results/report-round-1.xml
```

Expected: 只跑失败用例；输出「X passed, Y failed」

- [ ] **Step 6: 生成最终报告**

```bash
$PYTHON ~/.claude/skills/ui-report-generator/scripts/generate_report.py \
    --junit-xml ./test-results/report.xml \
    --exec-json ./test-results/report.json \
    --diagnose-md ./test-results/ui_repair_report.md \
    --artifacts-dir ./test-results/artifacts \
    --browser-env-json ./test-results/browser_env.json \
    --output ./test-results/ui_test_report.html \
    --auto-allure 2>&1 | tail -10
```

Expected: 输出 `[report] 已生成：./test-results/ui_test_report.html`

- [ ] **Step 7: 验证最终产物**

Run:
```bash
ls -lh ./test-results/ui_test_report.html ./test-results/ui_repair_report.md ./test-results/report-round-*.xml
```

Expected:
- `ui_test_report.html` 存在且 > 100KB
- `ui_repair_report.md` 存在
- `report-round-0.xml` 和 `report-round-1.xml` 都存在（多轮留档）

- [ ] **Step 8: 打开报告人工验证**

Run: `open ./test-results/ui_test_report.html`

Expected:
- 报告正常打开
- 失败用例区域含截图、录屏、Trace 按钮
- 诊断记录区域有内容（来自 ui_repair_report.md）
- Allure 按钮可点击（active）

---

## Self-Review

完成所有 Task 后，回头检查：

1. **Spec coverage**：
   - spec 第二章 4 个决策点（实现层级 / 重试范围 / max_retries / 失败兜底）→ Task 1-8 都已落地
   - spec 第三章目录结构 → Task 1 + 7 + 8 已创建全部文件
   - spec 第四章编排流程 → Task 2-5 覆盖 Step 0-5
   - spec 第五章参数透传 → Task 6 + 8 覆盖
   - spec 第六章 SKILL.md 章节结构 → Task 1-6 覆盖
   - spec 第九章验收标准 → Task 9 端到端覆盖

2. **Placeholder scan**：
   - 检查 SKILL.md 是否还有「（后续 Task X 会填充）」类占位 → 应已全部替换
   - 检查 references/ 是否有 TBD → 应无

3. **Type consistency**：
   - `--max-retries` 参数名在 SKILL.md / references/ / spec 是否一致
   - `round=0/1/2` 轮次编号在流程图、备份文件名、用户摘要里是否一致
   - `fixed_this_round` 变量名在 Step 2、Step 4、pipeline_flow.md 是否一致

---

## Execution Handoff

**Plan complete and saved to `~/.claude/skills/ui-pipeline-scheduler/docs/plans/2026-06-24-implementation.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - 我每个 Task 派一个新 subagent，任务间 review，迭代快

**2. Inline Execution** - 在本会话按 Task 顺序执行，每个 Task 完成后 checkpoint

**Which approach?**
