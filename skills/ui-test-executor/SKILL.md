---
name: ui-test-executor
description: WEB UI 自动化测试的智能执行调度引擎。负责触发执行 Playwright + Pytest UI 测试，按标签/模块/优先级智能调度，自动检测本地浏览器环境，全程监控执行状态，自动采集截图/录屏/Trace/网络日志，输出标准化报告。当用户需要"跑一下 UI 测试"、"执行 P0 用例"、"跑登录模块测试"、"跨浏览器跑 UI 测试"、"按标签筛选执行"、"用 CI 跑 UI 测试"、"浏览器跑不了"、"需要选浏览器"、"测试失败要截图和 Trace"、"生成测试报告"等场景时应使用本技能。不要使用本技能处理接口测试（用 api-test-executor）或测试脚本编写（用 ui-testscript-generator）。
---

# ui-test-executor — UI 测试智能执行调度引擎

## 技能定位

将已编写好的 Playwright + Pytest UI 测试脚本**真正跑起来**，形成"标签筛选 → 环境检测 → 执行调度 → artifact 采集 → 报告产出"的完整执行闭环。

**与上下游技能的边界：**

| 技能 | 输入 | 输出 |
|------|------|------|
| ui-page-parser | URL / 用例描述 | `pages.yaml` |
| ui-testscript-generator | `pages.yaml` + 用例 | 基础测试脚本 |
| ui-testscript-enhancer | 基础测试脚本 | 健壮性增强脚本 |
| ui-visual-assert | 增强脚本 | 视觉回归脚本 |
| ui-test-tagger | 测试脚本目录 | 标签化脚本 + `ui_tag_statistics.md` |
| **ui-test-executor** | **标签化脚本 + 执行意图** | **执行结果 + 报告 + artifacts** |

本技能**只读**测试目录，**不修改**测试脚本，只在执行层面做调度。

---

## 触发场景

应当触发本技能的关键词：

- "跑 UI 测试"、"执行 UI 用例"、"run UI tests"
- "跑一下 P0"、"执行冒烟用例"、"smoke test"
- "跑登录模块"、"按模块跑测试"、"跑搜索场景"
- "跨浏览器跑"、"chrome firefox 一起跑"、"matrix"
- "并行执行 UI 测试"、"加速跑"
- "失败要截图"、"要 Trace"、"要录屏"
- "生成测试报告"、"出 CI 报告"
- "浏览器跑不了"、"哪个浏览器能用"、"检测浏览器"
- "打开 trace"、"看 trace"、"show trace"、"open trace"
- "最新 trace"、"trace viewer"

**不应当触发：**

- 编写新测试脚本 → ui-testscript-generator
- 调试失败用例根因 → ui-failure-diagnoser（如有）/ systematic-debugging
- 给脚本打标签 → ui-test-tagger

---

## 工作流程

### 执行流程概览：标准化执行前打印（每次必输出，已固化）

`execute_tests.py` 在调度任何 pytest 进程之前，**无条件**先在 stderr 打印两个标准化章节，让用户在 pytest 大量输出之前就能确认本次执行的运行环境和用例范围。

#### 章节格式

两个章节都使用统一的视觉规范：
- 顶部 + 底部各 86 个 `=` 分隔线包夹
- 标题前缀 `▶`，副标题用 `·` 分隔
- 章节之间空一行避免粘连
- 全部输出走 stderr（不污染 pytest stdout 报告）

#### 章节 1：浏览器环境清单

调用 `detect_browsers.py` 输出本机已安装的所有浏览器（Playwright 内置 + 系统浏览器），含版本号、Headless 支持、未安装提示。

```
======================================================================================
  ▶ 浏览器环境清单  ·  execute_tests 调度前检测
======================================================================================
  ==========================  ...
    浏览器环境检测报告
  ==========================  ...
    系统: Darwin (macOS-26.3.1-x86_64-i386-64bit)
    Playwright 版本: unknown

    ✅ 检测到 4 个可用浏览器:

    #   名称                             引擎                     版本             Headless
    --- ------------------------------ ---------------------- -------------- ----------
    1   Chromium (Playwright)          playwright_chromium    1223           ✓
    2   Google Chrome (System)         system_chromium        Google Chrome 149.0.7827.155 ✓
    3   Microsoft Edge (System)        system_chromium        Microsoft Edge 149.0.4022.69 ✓
    4   Safari (System)                system_webkit          -              ✗

    未安装的浏览器（5 个，跳过）:
      - Firefox (Playwright): 未安装，运行 `python3 -m playwright install firefox`
      ...
  ==========================  ...
======================================================================================
```

#### 章节 2：待执行用例清单

按 `文件名：类别：用例名` 格式打印命中的用例列表，区分前置阶段（PRE-RUN）和主筛选集（MAIN）。

```
======================================================================================
  ▶ 待执行用例清单 — 主筛选集 MAIN  ·  命中 8 个用例
======================================================================================
      1. tests/auth/test_login.py：TestLogin：test_login_with_valid_credentials_redirects_to_home[chromium]
      2. tests/auth/test_login.py：TestLogin：test_login_success_shows_user_nickname_in_header[chromium]
      3. tests/auth/test_register.py：TestRegister：test_register_with_valid_data_redirects_to_login[chromium]
      4. tests/auth/test_register.py：TestRegister：test_register_page_displays_all_required_fields[chromium]
      5. tests/product/test_search.py：TestSearchPositive：test_search_valid_keyword_shows_results[chromium-手机]
      6. tests/product/test_search.py：TestSearchPositive：test_search_result_visual_layout_consistency[chromium]
      7. tests/product/test_search.py：TestSearchPositive：test_search_valid_keyword_shows_results[chromium-小米]
      8. tests/product/test_search.py：TestSearchPositive：test_search_valid_keyword_shows_results[chromium-手表]
======================================================================================
```

**关键字段说明：**

| 字段 | 含义 | 来源 |
|------|------|------|
| `文件名` | 用例所属测试文件相对路径 | pytest nodeid 第一段 |
| `类别` | 测试类名（无类时显示 `(no_class)`） | pytest nodeid 第二段 |
| `用例名` | 测试方法名 + 参数化方括号 | pytest nodeid 第三段 |
| `命中 N 个用例` | 经 `--tags / --priority / --keyword` 筛选后的总数 | 副标题 |

#### 实现位置

| 函数 | 文件 | 作用 |
|------|------|------|
| `_print_section_header()` | `scripts/execute_tests.py` | 统一渲染章节标题块（标题+副标题+上下分隔线） |
| `_print_section_footer()` | `scripts/execute_tests.py` | 渲染章节底部封闭分隔线 |
| `detect_and_print_browsers()` | `scripts/execute_tests.py` | 章节 1 实现（调用 detect_browsers.py） |
| `print_collected_tests()` | `scripts/execute_tests.py` | 章节 2 实现（前置 + 主用例） |
| `format_nodeid()` | `scripts/execute_tests.py` | nodeid → `文件名：类别：用例名` 转换 |

#### 行为保证

无论使用何种参数组合（包括 `--list-only` / `--dry-run` / 正式执行 / 带 `--pre-run`），**这两个章节都会在 pytest 启动前打印**。用户无需任何额外参数即可获得这两份摘要。

`--list-only` 模式打印完这两章节后立即返回，不调用 pytest，可用于"只想看选了哪些用例、不实际执行"的场景。

> 下面 Step 0~7 是 Claude 在使用本技能时按顺序执行的协作步骤；标准化打印由 `execute_tests.py` 内部自动完成，**不需要** Claude 手动触发。

---

### Step 0.5：Artifact 采集策略

**核心约束**：所有 artifact 均在用例失败时生成（用户明确要求）。通过的用例不保留截图/录屏/Trace，节省磁盘与 CI 时间。

#### 6 类 Artifact 总览

| 类型 | 采集机制 | 触发条件 | 输出路径 | 命名规则 |
|------|---------|---------|---------|---------|
| screenshots | conftest hook + pytest-playwright 原生 | setup/call 失败 | `artifacts/screenshots/` | `<nodeid>-{viewport,fullpage}.png`（conftest）/ `test-failed-N.png`（原生） |
| videos | pytest-playwright `--video=retain-on-failure` | call 失败 | `artifacts/pytest-raw/<slug>/video.webm` | 由 pytest-playwright 自动命名 |
| traces | pytest-playwright `--tracing=retain-on-failure` | call 失败 | `artifacts/pytest-raw/<slug>/trace.zip` | 由 pytest-playwright 自动命名 |
| har | 默认不生成真 `.har`；用 Network 摘要替代（见下方说明） | 失败 | （写入 console-logs 的 `## Network` 段） | — |
| console-logs | conftest autouse fixture + hook | setup/call 失败 | `artifacts/console-logs/<nodeid>.log` | 5 段：Page Errors / Console ERROR|WARN / Console 其他 / Network / Performance |
| page-source | conftest hook | setup/call 失败 | `artifacts/page-source/<nodeid>.html` | HTML 快照 |

#### 双层采集架构

```
pytest-playwright 原生（命令行参数控制）
  ├─ --screenshot=only-on-failure     → test-failed-N.png
  ├─ --video=retain-on-failure         → video.webm（失败保留，通过自动删除）
  └─ --tracing=retain-on-failure       → trace.zip（失败保留，通过自动删除）

conftest hook（项目 tests/conftest.py 提供，详见 assets/conftest_template.py）
  ├─ collect_console_and_errors (autouse) → 收集 console/pageerror/network 到 item._ui_collected
  ├─ pytest_runtest_makereport (hookwrapper) → 失败时触发 _collect_failure_artifacts
  └─ _collect_failure_artifacts → 写 screenshots / page-source / console-logs（5 段合并）
```

#### HAR 等价方案

pytest-playwright 0.8.0 不支持 `--har` 命令行参数；在 `browser_context_args` 注入 `record_har_path` 会污染所有用例（包括 `registered_user` 等内部 context），违背"仅失败采集"约束。

**务实方案**：conftest 的 `collect_console_and_errors` autouse fixture 注册 `page.on("requestfinished")` 收集 `{method, url, status, resource_type}`，失败时 dump 到 `console-logs/<nodeid>.log` 的 `## Network` 段，作为 HAR 等价物。覆盖 90% 的"接口请求追溯"场景，无需额外配置。

#### 输出目录树

```
test-results/
├── report.xml                    # JUnit XML（CI 标准）
├── report-pre.xml                # 前置阶段 JUnit
├── artifacts/
│   ├── screenshots/              # 失败截图（视口 + 全页）
│   │   └── tests-auth-test-login-py-...-test-login-with-valid-credentials-viewport.png
│   ├── page-source/              # 失败时 HTML 快照
│   │   └── tests-auth-test-login-py-...-test-login-with-valid-credentials.html
│   ├── console-logs/             # 失败时合并日志（5 段）
│   │   └── tests-auth-test-login-py-...-test-login-with-valid-credentials.log
│   ├── videos/                   # （保留目录，原生 video 写在 pytest-raw/）
│   ├── traces/                   # （保留目录，原生 trace 写在 pytest-raw/）
│   ├── har/                      # （保留目录，默认空；Network 摘要替代）
│   └── pytest-raw/               # pytest-playwright 原生产物
│       └── <nodeid-slug>/
│           ├── test-failed-1.png
│           ├── video.webm
│           └── trace.zip
```

#### 关键命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--screenshot=only-on-failure` | 开 | 仅失败用例采集视口截图（pytest-playwright 原生） |
| `--video=retain-on-failure` | 开 | 失败用例保留 video.webm，通过用例自动删除 |
| `--tracing=retain-on-failure` | 开 | 失败用例保留 trace.zip，通过用例自动删除 |
| `--artifact-root <path>` | `test-results/artifacts` | 透传给 conftest，控制 6 子目录的根 |
| `--output <path>` | `test-results/artifacts/pytest-raw` | pytest-playwright 原生产物输出 |

> **无需 ffmpeg / 无需合并脚本**：因为只在失败时生成 video（每文件独立），不需要 ffmpeg 合并多个通过用例的录屏。`tools/merge_videos.py` 不再需要。

---

> 下面 Step 0~7 是 Claude 在使用本技能时按顺序执行的协作步骤；标准化打印由 `execute_tests.py` 内部自动完成，**不需要** Claude 手动触发。

---

### Step 0：定位 Python 解释器

**执行 Python 前先在用户环境中确认可用的解释器**，优先级：

1. 用户项目虚拟环境（`<project>/.venv/bin/python`、`<project>/venv/bin/python`）
2. 全局 `python3`（含 macOS Homebrew `/usr/local/bin/python3`）

执行 `python -c "import playwright; print(playwright.__version__)"` 确认 Playwright 已安装。

### Step 1：检测浏览器环境（首次必做）

```bash
SKILL_DIR=~/.claude/skills/ui-test-executor
PYTHON=<上一步确定的解释器>

# 表格输出（人类可读）
$PYTHON "${SKILL_DIR}/scripts/detect_browsers.py"

# JSON 输出（供后续脚本消费）
$PYTHON "${SKILL_DIR}/scripts/detect_browsers.py" --json -o ./test-results/browser_env.json
```

**输出含义：**

- ✅ 至少 1 个可用浏览器 → 可以继续执行
- ⚠️ 无可用浏览器 → 引导用户安装：
  ```bash
  $PYTHON -m playwright install chromium
  ```

将检测结果**展示给用户**，并让用户选择本次执行使用哪个浏览器（如果多个可用）。

### Step 2：确认执行范围与参数

通过 `AskUserQuestion` 与用户确认以下参数（按需，能从上下文推断的不要问）：

| 参数 | 默认值 | 何时需要问 |
|------|--------|-----------|
| 测试目录 | `tests/` | 项目结构非标准时 |
| 标签筛选 | 无 | 用户提到"冒烟"、"P0"、"特定场景" |
| 模块筛选 | 无 | 用户提到"登录"、"订单"等模块 |
| 优先级 | 无 | 用户提到"P0/P1" |
| 浏览器 | 第一个可用 | 用户提到跨浏览器 |
| Headless | CI=true，本地=false | 不确定时问 |
| 并行 | 1（串行） | 用户提到"加速"、"并行" |
| 重试 | 0（无重试） | 用户提到"flaky"、"重试" |
| Artifact 模式 | retain-on-failure | 通常不需要问 |
| 输出目录 | `./test-results` | 项目自定义时 |

### Step 3：构建并预览执行命令

**强烈建议先用 `--dry-run` 预览构建出的 pytest 命令**，让用户确认调度逻辑无误：

```bash
$PYTHON "${SKILL_DIR}/scripts/execute_tests.py" tests/ \
    --priority P0 \
    --tags scene_positive \
    --browser chromium \
    --headless \
    --dry-run
```

输出会显示：

```
================================================================================
[执行计划] 构建 pytest 命令:
  /path/to/python -m pytest tests/ -m (P0) and scene_positive --browser chromium --headless ...
  工作目录: /Users/zhoujinjian/ai_project/shop-lab-ui-test
================================================================================
[DRY-RUN] 未实际执行
```

### Step 4：执行测试

去掉 `--dry-run` 实际执行：

```bash
$PYTHON "${SKILL_DIR}/scripts/execute_tests.py" tests/ \
    --priority P0 \
    --tags scene_positive \
    --browser chromium \
    --headless \
    --video retain-on-failure \
    --trace retain-on-failure \
    --output-dir ./test-results \
    --parallel 4 \
    --retry 2
```

**执行期间会发生：**

1. 实时流式输出 pytest stdout/stderr（用户能立即看到进度）
2. 失败的用例自动截图、保留 Trace、保留录屏
3. JUnit XML、HTML 报告、JSON 报告分别写入 `./test-results/`
4. 退出码：
   - `0`：全部通过
   - `1`：有失败用例
   - `2`：执行异常（找不到 pytest、超时等）
   - `130`：用户 Ctrl+C 中断

### Step 5：合并 conftest hook（首次集成时）

**如果项目 `tests/conftest.py` 还没集成失败自动采集 hook**，将 `assets/conftest_template.py` 中的内容合并到项目 conftest：

1. 读取项目现有 `tests/conftest.py`
2. 复制 `pytest_addoption` / `pytest_runtest_makereport` / `pytest_sessionfinish` 三个 hook
3. 复制 `artifact_root` fixture
4. 复制失败采集逻辑（截图 + 页面源码 + console 日志）

如果用户的项目已有这些 hook（例如 ui-testscript-enhancer 已注入），跳过此步。

### Step 6：生成统一报告

```bash
$PYTHON "${SKILL_DIR}/scripts/generate_report.py" \
    --junit-xml ./test-results/report.xml \
    --artifacts-dir ./test-results/artifacts \
    --output-dir ./test-results
```

**产出：**

| 文件 | 用途 |
|------|------|
| `test-results/report.json` | 结构化 JSON（CI/CD / 看板消费） |
| `test-results/report.html` | HTML 可视化报告（pytest-html 原生） |
| `test-results/report.xml` | JUnit XML（Jenkins / GitLab CI 原生） |
| `test-results/summary.md` | 人类可读 Markdown 摘要 |
| `test-results/summary.txt` | 单行 CI/CD 摘要 |
| `test-results/artifacts/screenshots/` | 失败截图（视口 + 全页） |
| `test-results/artifacts/videos/` | （空目录；原生 video 实际写到 `pytest-raw/<slug>/`） |
| `test-results/artifacts/traces/` | （空目录；原生 trace 实际写到 `pytest-raw/<slug>/`） |
| `test-results/artifacts/console-logs/` | 失败时合并日志（Page Errors / Console / Network 摘要 / Performance） |
| `test-results/artifacts/page-source/` | 失败时的 DOM 快照 |
| `test-results/artifacts/har/` | 默认空目录；Network 摘要已并入 console-logs（HAR 等价方案） |
| `test-results/artifacts/pytest-raw/` | pytest-playwright 原生产物（video.webm / trace.zip / test-failed-N.png，仅失败用例） |

### Step 6.5：自动生成失败用例深度报告

`execute_tests.py` 在 pytest 进程结束后，若 `report.xml` 显示有失败用例，**自动调用** `generate_failure_analysis.py` 生成 `test-results/failure_analysis.md`，无需任何额外参数。

```bash
# 自动触发（默认）
python3 execute_tests.py tests/ --priority P0 --tags run_smoke --browser chromium

# 关闭自动触发
python3 execute_tests.py tests/ --priority P0 --no-failure-analysis

# 手动重新生成（不重跑测试，基于已有 report.xml + artifacts）
python3 generate_failure_analysis.py \
    --junit-xml ./test-results/report.xml \
    --artifacts-dir ./test-results/artifacts \
    --output-dir ./test-results
```

**触发条件**（同时满足才会生成）：

1. 未传 `--no-failure-analysis`
2. 非 `--dry-run` / `--list-only` 模式
3. `report.xml` 中 `failures + errors > 0`（全通过时文件不生成 = 跑绿）

**failure_analysis.md vs summary.md 的区别：**

| 报告 | 字段密度 | 触发条件 | 用途 |
|------|---------|---------|------|
| `summary.md` | 低（概览统计 + 简要失败明细） | 每次执行 | CI 看板、流水线摘要、build description |
| `failure_analysis.md` | 高（每条失败一节，含 rule/assertion/playwright 字段/artifact 路径） | 仅 ≥1 失败时 | 深度故障诊断、人工排障 |

**failure_analysis.md 每条失败用例包含 7 个子章节：**

1. **判定规则** — 测试 docstring 首行（含参数化占位替换），无 docstring 时回退到函数名
2. **断言原文** — 带文件:行号的 assert 语句
3. **预期 vs 实际（pytest 内省）** — pytest 原生 `reprcrash.message`，含局部变量值
4. **页面元素校验** — URL / 定位器 / 期望 / 实际 / 推断原因（playwright expect 失败时从错误消息结构化提取；原生 assert 失败时为占位）
5. **失败截图路径** — 视口截图 + 全页截图 + Playwright 原生失败截图
6. **失败录屏与 Trace 路径** — 含 `playwright show-trace` 复现命令
7. **其他诊断材料** — page-source HTML / console-log（5 段合并）/ 失败时 URL

**降级行为**（保证永远能产出 MD）：

- conftest 未集成 `_dump_failure_context` hook / sidecar 缺失 → 退到 JUnit XML 渲染（仅 nodeid + message + traceback）
- video/trace 未生成 → 显示「（未生成，可能此用例未失败到 call 阶段）」提示
- `pytest-raw/` 下 slug 多候选 → 显示「⚠️ 多个候选目录匹配，请人工确认」警告

**数据来源**：报告依赖 conftest 在失败时落的 sidecar JSON（`<artifact-root>/failure-context/<safe_nodeid>.json`），包含 rule/assertion/expect_failure 解析结果与 artifact 路径。首次集成见 Step 5。

详见：
- 字段级 schema：`references/failure_report_schema.md`
- 使用指南（写测试的约定、降级排障）：`references/failure_analysis_guide.md`
- 设计文档：`docs/specs/2026-06-21-failure-analysis-report-design.md`

### Step 7：解读结果并给建议

读取 `summary.md` 与 `report.json`，向用户呈现：

1. **总体结果**：通过率、耗时、最慢用例
2. **失败明细**：每个失败用例的文件位置、错误摘要、Traceback 末尾 20 行
3. **artifact 索引**：截图、Trace、录屏路径
4. **建议下一步**：
   - 全过 → 推荐接入 CI/CD（给出 GitHub Actions / Jenkins 示例）
   - 有失败 → 推荐用 `playwright show-trace` 查看 Trace，或调用 systematic-debugging
   - flaky → 调高 `--retry`，或排查时序问题

### Step 7.5：按需打开 Trace Viewer

当用户在执行后问「打开 trace」「看看最新失败的 trace」「打开小米那条 trace」时，调：

```bash
python3 scripts/open_trace.py [query] --artifacts-dir <test-results/artifacts>
```

`query` 三种形式：
- 省略 / `"latest"` / `"最新"`：打开最新一条（mtime 最大）
- 关键词（如 `"小米"`、`"test_search"`）：按 nodeid 子串匹配，中文会自动转 slug 容错（小米 ↔ u5c0f-u7c73）
- 全路径：直接用（必须 `.zip` 后缀）

**行为：** 后台启动 Trace Viewer（`start_new_session=True`），Claude 立即拿到控制权。日志写入 `<artifacts-dir>/trace-viewer.log`。

**退出码：** 0 成功 / 1 matching 错误 / 2 playwright 未装 / 3 spawn 异常。

详见 `references/trace_viewer_guide.md`。

---

## 关键能力详解

### 调度策略（marker 表达式构建）

`execute_tests.py::build_marker_expression()` 实现了如下语义：

| 参数 | 关系 | 示例输出 |
|------|------|---------|
| `--priority P1` | 累积包含（P0+P1） | `(P0 or P1)` |
| `--modules login order` | OR | `(module_login or module_order)` |
| `--tags smoke scene_positive` | AND | `smoke and scene_positive` |
| `--marker-expr "P0 and not slow"` | 覆盖 | `(...自动构建...) and (P0 and not slow)` |
| 组合 | AND 串联 | `(P0 or P1) and (module_login) and scene_positive` |

**优先级累积语义的原因**：P0 是核心链路必跑，P1 包含核心 + 重要；当用户说"跑 P1"，意思是"P1 及以上都跑"，而不是"只跑 P1 排除 P0"。

### 浏览器矩阵执行

支持 `--browser` 多次指定，pytest-playwright 会自动展开为笛卡尔积：

```bash
# 3 浏览器 × 全部用例 = 3×N 个测试运行
$PYTHON execute_tests.py tests/ --browser chromium firefox webkit --headless
```

### 跨浏览器容差（视觉测试场景）

如果项目接入了 ui-visual-assert，跨浏览器视觉测试需要不同容差（chromium 基准、firefox/webkit 字体渲染有差异）。容差由项目 `tests/conftest.py` 中的 `cross_browser_tolerance` fixture 决定，本技能不干预。

### 并行执行

```bash
# 4 进程并行，按 class 分发（同一类的用例在同一进程跑，避免 fixture 重复初始化）
$PYTHON execute_tests.py tests/ --parallel 4 --dist loadscope
```

**`--dist` 策略选择：**

| 策略 | 适用场景 |
|------|---------|
| `load`（默认）| 用例数多、独立性强（每个用例独立 setup） |
| `loadscope` | 类/模块内共享 fixture（推荐 POM 项目） |
| `loadfile` | 同文件用例必须同进程 |
| `no` | 关闭并行（用于排查并行问题） |

### 失败重试

依赖 `pytest-rerunfailures`：

```bash
# 失败后重试最多 2 次，每次间隔 2 秒
$PYTHON execute_tests.py tests/ --retry 2
```

**适用场景：**

- 网络抖动导致的偶发失败
- CI 环境资源竞争
- 验证码识别偶发失败

**不适用：**

- 确定性失败（DOM 结构错误、定位器失效）→ 重试无效，浪费时间
- 视觉回归失败 → 重试可能掩盖真实回归

---

## 典型使用场景

### 场景 1：本地开发快速验证

```bash
# 只跑 P0 + 正向场景，有头模式看效果
$PYTHON execute_tests.py tests/ --priority P0 --tags scene_positive --no-headless
```

### 场景 2：CI/CD 完整回归

```bash
$PYTHON execute_tests.py tests/ \
    --priority P2 \
    --browser chromium \
    --headless \
    --parallel 4 \
    --retry 2 \
    --video retain-on-failure \
    --trace retain-on-failure \
    --output-dir ./test-results
```

### 场景 3：跨浏览器矩阵

```bash
$PYTHON execute_tests.py tests/ \
    --priority P1 \
    --browser chromium firefox webkit \
    --headless \
    --parallel 3 \
    --dist loadscope
```

### 场景 4：调试单个失败用例

```bash
# 关闭并行，关闭重试，开启 Trace
$PYTHON execute_tests.py tests/auth/test_login.py::TestLogin::test_invalid_password \
    --browser chromium \
    --no-headless \
    --slow-mo 200 \
    --trace on \
    --video on
```

### 场景 5：冒烟测试快速通过

```bash
$PYTHON execute_tests.py tests/ --tags run_smoke --browser chromium --headless
```

### 场景 6：仅查看构建的命令不执行

```bash
$PYTHON execute_tests.py tests/ --priority P0 --tags scene_positive --dry-run
```

---

## 输出结果解读

### summary.txt 单行摘要

```
✅ UI Test: 18/20 passed (90.0%) | 2 failed, 0 errors, 0 skipped | 156.3s
```

CI/CD 流水线可直接抓取此行作为 build description。

### summary.md Markdown 报告

包含：

- 概览表格（总数、通过率、最慢用例）
- 按模块分布的通过率矩阵
- 失败用例明细（含 Traceback 末 20 行 + artifact 路径）

### report.json 结构化数据

```json
{
  "generated_at": "2026-06-16T14:32:00",
  "suite": {
    "total": 20,
    "passed": 18,
    "failed": 2,
    "pass_rate": 90.0,
    "total_duration": 156.3
  },
  "by_module": {
    "auth": {"passed": 5, "failed": 1, "total": 6},
    "product": {"passed": 13, "failed": 1, "total": 14}
  },
  "failures": [
    {
      "nodeid": "tests/auth/test_login.py::TestLogin::test_invalid_password",
      "status": "failed",
      "duration": 3.2,
      "message": "AssertionError: 错误提示文案不匹配",
      "traceback": "...",
      "artifacts": {
        "screenshots": ["test-results/artifacts/screenshots/..."],
        "traces": ["test-results/artifacts/traces/..."]
      }
    }
  ]
}
```

---

## 常见问题排查

### 问题 1：找不到 pytest 或 playwright

```
[ERROR] 找不到 pytest，请确认环境: /path/to/python -m pytest --version
```

排查：

1. 确认 Python 解释器路径正确
2. 执行 `$PYTHON -m pip install pytest pytest-playwright`
3. 执行 `$PYTHON -m playwright install chromium`

### 问题 2：浏览器未安装

```
⚠️ 未检测到任何可用浏览器！
   请安装 Playwright 浏览器: python3 -m playwright install chromium
```

排查：

```bash
$PYTHON -m playwright install chromium  # 或 firefox / webkit / all
```

### 问题 3：跨浏览器视觉测试容差过严

跨浏览器（特别是 firefox/webkit）由于字体渲染、滚动条宽度差异，视觉回归容差需要放宽。在项目 `tests/conftest.py` 中查找 `cross_browser_tolerance` fixture，确保 firefox/webkit 容差 ≥ 0.12。

### 问题 4：并行执行后 fixture 状态污染

POM 项目推荐使用 `--dist loadscope`，确保同一类/模块的用例在同一进程跑。

### 问题 5：CI 环境 headless 失败但本地 headed 通过

通常是视口或字体差异。在 `tests/conftest.py` 的 `browser_context_args` 中显式设置 `viewport={"width": 1280, "height": 720}`。

---

## CI/CD 集成示例

### GitHub Actions

```yaml
- name: Run UI Tests
  run: |
    python3 ~/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
      --priority P2 \
      --browser chromium \
      --headless \
      --parallel 4 \
      --output-dir ./test-results

- name: Generate Report
  if: always()
  run: |
    python3 ~/.claude/skills/ui-test-executor/scripts/generate_report.py \
      --junit-xml ./test-results/report.xml \
      --artifacts-dir ./test-results/artifacts \
      --output-dir ./test-results

- name: Upload Artifacts
  if: always()
  uses: actions/upload-artifact@v3
  with:
    name: ui-test-results
    path: ./test-results/
```

### Jenkins Pipeline

```groovy
stage('UI Test') {
  steps {
    sh '''
      python3 ~/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
        --priority P2 --browser chromium --headless --parallel 4
    '''
  }
  post {
    always {
      junit 'test-results/report.xml'
      publishHTML(target: [
        reportDir: 'test-results',
        reportFiles: 'report.html',
        reportName: 'UI Test Report'
      ])
      archiveArtifacts artifacts: 'test-results/**', allowEmptyArchive: true
    }
  }
}
```

---

## 参考文件索引

| 文件 | 用途 | 读取时机 |
|------|------|---------|
| `references/browser_detection.md` | 浏览器检测原理、跨平台差异、自定义浏览器路径 | 浏览器检测失败 / 自定义环境时 |
| `references/scheduling_strategies.md` | 调度策略（标签表达式 / 并行分发 / 重试策略）详解 | 复杂调度场景 / 排查并行问题时 |
| `references/artifact_collection.md` | artifact 采集机制、命名规则、保留策略 | 配置 artifact 行为时 |
| `references/report_schema.md` | JSON 报告 schema、字段含义、扩展字段 | CI 集成 / 看板对接时 |
| `references/failure_report_schema.md` | failure_analysis.md 字段级 schema（含 sidecar JSON schema） | Step 6.5 排障 / 扩展字段时 |
| `references/failure_analysis_guide.md` | failure_analysis.md 用户指南（docstring 约定、降级排障） | 写测试 / 配 CI 时 |
| `references/trace_viewer_guide.md` | Trace Viewer 快捷打开使用指南（三种查询、中文匹配、排障） | Step 7.5 |
| `assets/conftest_template.py` | 项目 conftest 集成的 hook 模板 | 首次给项目接入失败采集时 |
| `scripts/detect_browsers.py` | 浏览器检测脚本 | Step 1 |
| `scripts/execute_tests.py` | 执行调度脚本（核心） | Step 4 |
| `scripts/generate_report.py` | 报告生成脚本 | Step 6 |
| `scripts/generate_failure_analysis.py` | 失败用例 MD 故障分析报告生成器 | Step 6.5 |
| `scripts/open_trace.py` | Playwright Trace Viewer 快捷打开（支持自然语言查询） | Step 7.5 |

---

## 参数完整参考

### execute_tests.py 参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `test_dir` | 位置参数 | `tests/` | 测试目录 |
| `test_files` | 可变位置 | - | 直接指定测试文件（覆盖 test_dir） |
| `--tags` | list | - | 标签筛选（AND 关系） |
| `--modules` | list | - | 模块筛选（OR 关系） |
| `--priority` | enum | - | P0/P1/P2/P3（累积包含） |
| `--keyword` / `-k` | str | - | pytest 关键字筛选 |
| `--marker-expr` / `-m` | str | - | 原始 pytest -m 表达式（覆盖自动构建） |
| `--parallel` / `-n` | int | 1 | 并行进程数（依赖 pytest-xdist） |
| `--dist` | enum | loadscope | xdist 分发策略 |
| `--retry` | int | 0 | 失败重试次数（依赖 pytest-rerunfailures） |
| `--timeout` | int | 300 | 单用例超时秒数 |
| `--fail-fast` / `-x` | flag | false | 首失败立即停止 |
| `--verbose` / `-v` | flag | false | 详细输出 |
| `--browser` | list | - | 浏览器引擎（多次指定形成矩阵） |
| `--headless` | flag | false | 无头模式 |
| `--no-headless` / `--headed` | flag | false | 有头模式 |
| `--slow-mo` | int | - | slow-mo 毫秒数（调试用） |
| `--screenshot-on-failure` | flag | true | 失败截图 |
| `--no-screenshot` | flag | false | 关闭失败截图 |
| `--video` | enum | retain-on-failure | off / on / retain-on-failure |
| `--trace` | enum | retain-on-failure | off / on / retain-on-failure |
| `--output-dir` | path | `./test-results` | 结果输出目录 |
| `--no-header` | flag | false | 不显示 pytest 头部 |
| `--dry-run` | flag | false | 只打印构建的命令，不实际执行 |

### detect_browsers.py 参数

| 参数 | 说明 |
|------|------|
| `--json` | 输出 JSON 格式 |
| `-o` / `--output` | 输出到文件 |

### generate_report.py 参数

| 参数 | 说明 |
|------|------|
| `--junit-xml` | （必需）JUnit XML 报告路径 |
| `--artifacts-dir` | artifacts 根目录 |
| `--output-dir` | 输出目录（默认当前目录） |
| `--formats` | 输出格式（json/md/summary，默认全部） |
