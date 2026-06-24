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

### ui-pipeline-scheduler/scripts/merge_reports.py（Step 4.5 编排层脚本）

```bash
$PYTHON merge_reports.py \
    --base ./test-results/report-round-0.xml \
    --overlay ./test-results/report-round-1.xml \
    [--overlay ./test-results/report-round-2.xml ...] \
    --output ./test-results/report.xml
```

**合并语义**：首轮 XML（完整 N 条）为基底；每个 overlay（重试轮 XML）按 `(classname, name)` 唯一键覆盖基底同名用例；重新统计 testsuite 计数；输出到 `--output`。

**何时调用**：仅发生过 Step 3 重试（存在 `report-round-1.xml`）时；首轮全过则跳过。

## 参数透传规则

1. **首轮全量参数**：用户传给 executor 的 priority/tags/modules/browser/headless/parallel/base-url 全量透传
2. **重试精简参数**：重试时**只保留** browser/headless/parallel/base-url/output-dir，**移除** priority/tags/modules（避免和 -k 叠加漏跑）
3. **diagnoser 参数对齐**：base-url 和 browser 必须与 executor 一致（verify 重跑要用相同环境）
4. **report-generator 5 源融合**：--junit-xml 必填；--diagnose-md 仅在触发过 diagnoser 时传；其余按存在性自动判断
5. **merge_reports 仅在多轮时触发**：首轮全过（无 report-round-1.xml）直接用首轮 report.xml；否则必须先 merge 再 generate_report，保证最终报告含完整 N 条用例
