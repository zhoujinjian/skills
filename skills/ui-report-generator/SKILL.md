---
name: ui-report-generator
description: WEB UI 自动化测试（Playwright + Pytest + POM）测试报告生成专家。将 ui-test-executor 的 JUnit XML + artifacts、ui-failure-diagnoser 的诊断报告、以及历史趋势数据融合为单文件 HTML 可视化报告，含状态分布图、模块通过率、浏览器矩阵、风险分级、失败详情（含内联截图/录屏/Trace 打开按钮）、根因聚类与优化建议。**核心约束：只读测试结果与诊断输出，永不修改 tests/** 与 pages/**。
agent_created: true
---

# ui-report-generator — UI 自动化测试报告生成专家

## 技能定位

**唯一要做的事：** 把 UI 测试执行结果、诊断结论、历史数据融合成可视化、可决策的单文件 HTML 报告。

覆盖范围：

| 数据源 | 来源 Skill | 关键字段 |
|---|---|---|
| JUnit XML（必需） | ui-test-executor | nodeid / status / duration / message / traceback / browser |
| 失败 artifacts | ui-test-executor conftest | screenshots / page-source / console-logs / video.webm / trace.zip |
| 诊断报告 | ui-failure-diagnoser | 分类 / 根因 / 修复策略 / 验证状态 / 升级信息 |
| 浏览器环境 | ui-test-executor/detect_browsers | 已安装浏览器清单 |
| 历史趋势 | 外部累积 | 多次执行通过率序列 |

**硬约束（永不违反）：**
- 🚫 不修改 `tests/**/*.py` 任何内容
- 🚫 不修改 `pages/**/*.py` 任何内容
- 🚫 不修改 `conftest.py`、`pytest.ini`、配置文件
- 🟢 只读 JUnit XML、JSON、Markdown 报告、artifacts 目录
- 🟢 唯一写入：HTML 报告文件（用户指定路径）

**与上下游 Skill 边界：**

| Skill | 输入 | 输出 |
|---|---|---|
| ui-test-executor | 标签化脚本 + 执行意图 | JUnit XML + artifacts + JSON |
| ui-failure-diagnoser | JUnit XML + artifacts | ui_repair_report.md + .bak |
| **ui-report-generator** | **JUnit XML + 可选 JSON/MD/artifacts/history** | **单文件 HTML 报告** |

---

## 触发场景

**应当触发：**
- "生成 UI 测试报告"、"出个 HTML 报告"、"测试总结"
- "看下执行结果"、"结果汇总"
- "查看报告"、"测试报告"、"report"
- "为什么挂这么多"、"哪些模块挂的多"
- "对比上次"、"趋势"、"历史通过率"
- 上游技能（ui-test-executor、ui-failure-diagnoser）执行完毕后联动调用

**不应当触发：**
- 跑 UI 测试 → ui-test-executor
- 调试失败用例根因 → ui-failure-diagnoser
- 写新测试脚本 → ui-testscript-generator
- 给脚本打标签 → ui-test-tagger
- 通用接口测试报告 → api-report-generator

---

## 工作流程

### Step 1：确认输入

**必需：**
- `--junit-xml`：JUnit XML（来自 ui-test-executor）

**可选：**
- `--exec-json`：`report.json`（来自 ui-test-executor/generate_report.py，提供更丰富字段）
- `--diagnose-md`：`ui_repair_report.md`（来自 ui-failure-diagnoser，含根因聚合）
- `--artifacts-dir`：失败 artifact 根目录（截图/录屏/trace）
- `--browser-env-json`：`browser_env.json`（来自 detect_browsers.py）
- `--history-json`：历史执行累积（多次执行通过率序列）

### Step 2：解析多源数据（`scripts/parsers.py`）

1. **JUnit XML** → `parse_junit_xml()` → `UISuiteSummary + list[UITestCase]`
   - 从 `<testcase>` 提取 nodeid / classname / status / duration / message
   - 从 `<system-out>[BROWSER=...]` 提取浏览器
   - 兜底：从参数化后缀 `[chromium-手机]` 提取
2. **artifacts 关联** → `attach_artifacts()` → 每个 case 挂上 screenshots/videos/traces/page_source/console_logs
3. **诊断报告** → `parse_diagnose_md()` → 解析「## 概览」表 + 「## 失败明细」每条记录
   - 提取 category / confidence / root_cause / fix_strategy / verify_status / upgraded_root_cause

### Step 3：聚合分析（`scripts/analyzer.py`）

- **by_module**：按 tests 子目录分组（auth/product/cart/...）
- **by_priority**：按 P0/P1/P2/P3 marker 分组
- **by_browser**：按 chromium/firefox/webkit 分组（**UI 特有**）
- **by_category + by_root_cause**：从诊断记录聚合
- **风险分级**：通过率 <70%=高，70-90%=中，>90%=低
- **失败聚类**：按根因 group by，找出高频根因
- **优化建议**：基于失败模式自动生成（高频根因、ENV 问题、跨浏览器不一致等）

### Step 4：HTML 渲染（`scripts/renderer.py`）

**单文件输出**：所有 CSS/JS/JSON data 内联；截图 base64 内联；Chart.js 4.4 CDN（离线降级到表格）。

**页面分区**（对齐 api-report-generator 风格 + UI 增强）：

| 区块 | 内容 | UI 增强 |
|---|---|---|
| 报告头部 | 标题 + 环境 + 时间 + 浏览器清单 | 浏览器清单 |
| 总览大盘 | 6 张 KPI 卡（总数/通过/失败/跳过/通过率/耗时） | — |
| 数据图表 | 状态饼图 + 模块柱图 + 历史折线 | — |
| **浏览器矩阵** | 多浏览器通过率对比 | ✅ UI 特有 |
| 模块统计 | 模块 × 通过率 × 风险等级 | — |
| 诊断根因聚合 | 分类表 + 根因分布表 | ✅ 集成 ui-failure-diagnoser |
| 风险与建议 | 高风险模块表 + 优先级建议清单 | ✅ 含具体修复动作 |
| **失败详情** | 节点 + 分类 + 根因 + 错误 + Traceback | ✅ **内联截图 + 录屏 + Trace 打开命令** |
| 用例明细 | 全量列表 + 筛选 + 分页 | ✅ 浏览器筛选器 |

### Step 5：文件输出

```bash
python3 scripts/generate_report.py \
    --junit-xml ./test-results/report.xml \
    --artifacts-dir ./test-results/artifacts \
    --diagnose-md ./test-results/ui_repair_report.md \
    --output ./test-results/ui_test_report.html \
    --title "ShopLab UI 测试报告"
```

**输出路径：** 用户指定的 `--output`，默认 `./ui_test_report.html`。

**Trace 打开按钮：** 失败详情区每个 case 显示 `📋 打开 Trace` 按钮，点击复制 `python -m playwright show-trace <path>` 到剪贴板，用户粘贴到终端即可。

---

## CLI 接口

```bash
python3 scripts/generate_report.py \
    --junit-xml <JUnit XML 路径> \
    [--exec-json <report.json>] \
    [--diagnose-md <ui_repair_report.md>] \
    [--artifacts-dir <artifacts 根>] \
    [--browser-env-json <browser_env.json>] \
    [--history-json <history.json>] \
    [--output <HTML 输出路径>] \
    [--title <报告标题>] \
    [--trace-launch-cmd <命令模板>] \
    [--no-inline-screenshots]
```

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `--junit-xml` | Path | 必填 | JUnit XML 路径 |
| `--exec-json` | Path | - | ui-test-executor report.json（可选，更丰富字段） |
| `--diagnose-md` | Path | - | ui-failure-diagnoser ui_repair_report.md |
| `--artifacts-dir` | Path | - | artifacts 根目录（截图/录屏/trace） |
| `--browser-env-json` | Path | - | detect_browsers.py 的 JSON |
| `--history-json` | Path | - | 历史执行累积 JSON |
| `--output` | Path | `./ui_test_report.html` | HTML 输出路径 |
| `--title` | str | `UI 自动化测试报告` | 报告标题 |
| `--trace-launch-cmd` | str | `python -m playwright show-trace {trace_path}` | Trace 打开命令模板（含 `{trace_path}` 占位） |
| `--no-inline-screenshots` | flag | false | 不内联截图 base64（生成相对路径 `<img>`，HTML 更小） |

退出码：`0` 成功；`2` 输入错误（JUnit XML 不存在）。

---

## 关键能力详解

### 多源数据融合

把 5 类输入融合为统一 ReportDocument：

```
JUnit XML (必需)        ──┐
                          ├──► parsers.py ──► analyzer.py ──► renderer.py ──► HTML
exec.json (可选)         ──┤
diagnose.md (可选)       ──┤
artifacts-dir (可选)     ──┤
history.json (可选)      ──┘
```

**容错策略：** 任一可选输入缺失，对应区块显示「暂无数据」，不影响整体报告生成。

### 浏览器矩阵（UI 特有）

跨浏览器 UI 测试的关键场景。报告会展示：

| 浏览器 | 总数 | 通过 | 失败 | 通过率 |
|---|---|---|---|---|
| chromium | 18 | 15 | 3 | 83.3% |
| firefox | 18 | 17 | 1 | 94.4% |
| webkit | 18 | 12 | 6 | 66.7% |

通过率高低差 >10% 自动触发建议：「webkit 通过率显著偏低，排查浏览器兼容性」。

### 失败详情内嵌 artifacts

每个失败 case 显示：
1. **诊断信息**：分类 / 根因 / 修复策略 / 验证状态 / 升级信息（来自 ui-failure-diagnoser）
2. **错误堆栈**：`<failure>` message + 折叠的 traceback
3. **截图（base64 内联）**：viewport + fullpage（最多 2 张）
4. **Traceback 折叠区**：完整 traceback（max 4000 字）
5. **操作按钮**：
   - 「查看 DOM 快照」→ 打开 page-source HTML
   - 「Console 日志」→ 打开 5 段合并日志
   - 「观看录屏」→ 打开 video.webm
   - 「📋 打开 Trace」→ 复制 `playwright show-trace` 命令到剪贴板

### 趋势图（历史数据）

如果提供 `--history-json`（JSON 数组）：
```json
[
  {"timestamp": "2026-06-20", "pass_rate": 92.3},
  {"timestamp": "2026-06-21", "pass_rate": 88.5},
  {"timestamp": "2026-06-22", "pass_rate": 95.0}
]
```
报告会在「数据图表」区显示 3 次执行的通过率折线，方便观察 flakiness 和长期趋势。

### 单文件可移植

- 所有 CSS inlined（`<style>` 块）
- 所有数据 inlined（`<script>const PAYLOAD = {...}</script>`）
- 截图 base64 inlined（默认）
- 唯一外部依赖：Chart.js CDN（`cdn.jsdelivr.net`）
- 离线降级：Chart.js 加载失败时自动切换到数据表格

---

## 典型使用场景

### 场景 1：CI 流水线出报告

```bash
# 跑完测试 + 诊断后
python3 scripts/generate_report.py \
    --junit-xml ./test-results/report.xml \
    --artifacts-dir ./test-results/artifacts \
    --diagnose-md ./test-results/ui_repair_report.md \
    --browser-env-json ./test-results/browser_env.json \
    --output ./test-results/ui_test_report.html
```

### 场景 2：仅 JUnit XML（最小输入）

```bash
python3 scripts/generate_report.py \
    --junit-xml ./report.xml \
    --output ./report.html
```

报告会工作，但诊断区块、截图内联、Trace 按钮都不可用（对应区块显示「暂无数据」）。

### 场景 3：联动调用（上游 skill 自动触发）

```
请调用 ui-report-generator：
- junit-xml: ./test-results/report.xml
- artifacts-dir: ./test-results/artifacts
- diagnose-md: ./test-results/ui_repair_report.md
```

### 场景 4：历史趋势对比

```bash
# 把历次报告的通过率累积到 history.json
python3 scripts/generate_report.py \
    --junit-xml ./test-results/report.xml \
    --history-json ./reports/history.json \
    --output ./test-results/ui_test_report.html
```

---

## 输出结构

```
<project>/
├── test-results/
│   ├── report.xml                    # JUnit XML（输入）
│   ├── ui_repair_report.md           # 诊断报告（输入）
│   └── ui_test_report.html           # ★ 单文件 HTML 报告（输出）
├── reports/
│   └── history.json                  # 历史累积（输入，可选）
└── artifacts/                        # 失败 artifact（输入）
    ├── screenshots/
    ├── page-source/
    ├── console-logs/
    └── pytest-raw/<slug>/{trace.zip, video.webm}
```

---

## 依赖

- **ui-test-executor**：上游，产出 JUnit XML + artifacts
- **ui-failure-diagnoser**：上游（可选），产出诊断报告
- Python 3.10+（标准库 `xml.etree` / `json` / `pathlib`，无第三方依赖）
- 浏览器：Chart.js 4.4 CDN（无需安装，离线自动降级）

---

## 常见问题排查

### Q1：报告显示「暂无诊断数据」
未提供 `--diagnose-md`，或 ui_repair_report.md 不存在。先跑 `ui-failure-diagnoser/scripts/diagnose.py` 生成诊断报告。

### Q2：失败详情没有截图
未提供 `--artifacts-dir`，或 artifacts/screenshots/ 为空。检查 ui-test-executor 的 conftest 是否集成了失败采集 hook。

### Q3：浏览器筛选项是空的
`<system-out>` 里没有 `[BROWSER=...]` 标记。新版 pytest-playwright 默认会参数化为 `[chromium-...]` 后缀，本技能会兜底从 nodeid 提取。

### Q4：HTML 文件太大
默认内联截图 base64。使用 `--no-inline-screenshots` 切换到相对路径（HTML 移动时需带上 artifacts 目录）。

### Q5：Chart.js 不显示
离线环境。本技能已内置降级：Chart.js 加载失败时自动用表格展示。

---

## 参考文件索引

| 文件 | 用途 | 读取时机 |
|---|---|---|
| `scripts/generate_report.py` | CLI 主入口 | 每次调用 |
| `scripts/parsers.py` | JUnit XML / MD / artifacts 解析 | diagnose 内部 |
| `scripts/analyzer.py` | 聚合 + 风险 + 建议 | diagnose 内部 |
| `scripts/renderer.py` | HTML 模板 + 渲染 | diagnose 内部 |
| `scripts/trace_launcher.py` | Playwright Trace Viewer 快捷打开 | 手动打开 trace 时 |
| `references/report_template_spec.md` | 报告布局规范 | 自定义样式时 |
| `references/chart_config.md` | Chart.js 4.4 配置参考 | 调整图表时 |
| `evals/core/test_parsers.py` | 解析器单元测试 | 重构/扩展时 |
| `evals/core/test_analyzer.py` | 分析器单元测试 | 重构/扩展时 |
