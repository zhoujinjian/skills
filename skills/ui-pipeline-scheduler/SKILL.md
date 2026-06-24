---
name: ui-pipeline-scheduler
description: WEB UI 自动化测试全链路统一编排入口。负责把 ui-test-executor（执行）→ ui-failure-diagnoser（诊断修复）→ ui-test-executor（重试）→ ui-report-generator（报告）四个阶段自动串联成闭环，含失败诊断+智能重试+熔断兜底。当用户需要"一键全跑 UI 自动化"、"自动修复失败用例并重试"、"端到端 UI 测试流水线"、"全流程闭环"、"UI 自动化 pipeline"时触发本技能。本技能不替代任何子技能，仅做流程编排与参数透传，三个子技能仍可独立调用。
---

# ui-pipeline-scheduler — UI 自动化全链路统一编排入口

## 技能定位

把三个独立 skill 串成**执行 → 诊断 → 重试 → 合并 → 报告**的完整闭环：

```
ui-test-executor  →  ui-failure-diagnoser  →  ui-test-executor（重试）  →  merge_reports  →  ui-report-generator
   执行入口              仅失败时触发              循环 max_retries 次        多轮XML合并        始终生成
                                                                                  ↑
                                                                       仅发生重试时触发
```

**核心原则（硬约束）**：

1. **零侵入**：禁止修改 ui-test-executor / ui-failure-diagnoser / ui-report-generator 任何代码、入参、出参、调用方式
2. **编排含一个内部脚本**：仅 `scripts/merge_reports.py`（多轮 JUnit XML 合并），属编排层数据后处理，不调用任何子技能逻辑
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
- 进 Step 4.5 合并多轮 XML → Step 5 生成最终报告

### Step 4.5：合并多轮 JUnit XML（重试循环后必做）

**触发条件**：只要发生过 Step 3 重试（即存在 `report-round-1.xml` 及之后的留档），**必须合并**，否则 Step 5 报告会丢用例。

**问题背景**：

Step 3 重试用 `-k` 只跑失败用例，`report.xml` 被覆盖为只剩失败用例子集（如首轮 8 条 → 重试 3 条）。直接喂给 `generate_report.py` 会得到**残缺报告**（只含失败用例）。本步骤把首轮完整 XML 与各重试轮 XML 合并，恢复完整 N 条用例的最新状态。

**执行命令**：

```bash
# 收集所有 report-round-*.xml（按轮次顺序：0, 1, 2, ...）
$PYTHON ~/.claude/skills/ui-pipeline-scheduler/scripts/merge_reports.py \
    --base ./test-results/report-round-0.xml \
    --overlay ./test-results/report-round-1.xml \
    $( [ -f ./test-results/report-round-2.xml ] && echo "--overlay ./test-results/report-round-2.xml" ) \
    --output ./test-results/report.xml
```

**合并规则**（由脚本保证）：

1. 以 `report-round-0.xml`（首轮）为**基底**，保留所有 N 条用例
2. 每个 overlay（重试轮）按 `(classname, name)` 唯一键覆盖基底中的同名用例 — 参数化变体的 `name` 含 `[chromium-小米]` 后缀天然区分
3. 重新统计 `testsuite` 的 `tests/failures/errors/skipped` 属性
4. 输出到 `./test-results/report.xml`（覆盖被重试轮写残的版本）

**首轮全过场景**：未触发重试，无 `report-round-1.xml`，**跳过本步骤**（首轮 `report.xml` 本身就是完整的 N 条）。

**验证合并输出**：

```bash
$PYTHON -c "
import xml.etree.ElementTree as ET
tree = ET.parse('./test-results/report.xml')
cases = list(tree.iter('testcase'))
fails = sum(1 for c in cases if c.find('failure') is not None)
print(f'合并后用例数={len(cases)} failures={fails}')
"
# 期望：用例数 = 首轮用例数（如 P0 smoke 应为 8）
```

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

- `--junit-xml`：**用 Step 4.5 合并后的 `report.xml`**（含完整 N 条用例的最新结果）；首轮全过场景是首轮 `report.xml` 本身
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

1. **严格串行**：Step 1 → 2 → 3 → 4 → 4.5 → 5，禁止并行子技能
2. **零侵入**：禁止修改任何子技能的 SKILL.md / scripts / 入参 / 出参
3. **参数透传**：用户的 executor 参数原样传给 Step 1 + Step 3，不做转换
4. **幂等**：重复执行 pipeline 时，先清空 `./test-results/` 或用新目录
5. **日志追溯**：每轮的 report.xml 备份为 `report-round-N.xml`，可追溯每轮失败现场
6. **熔断优先**：达 `max_retries` 上限立即跳出循环，不死循环
7. **始终生成报告**：无论失败与否，Step 5 必须执行
8. **报告完整**：发生过重试时，Step 5 **必须**先用 `merge_reports.py` 合并首轮完整 XML + 各轮重试 XML，保证最终报告含完整 N 条用例（而非仅失败子集）
