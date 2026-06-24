---
name: ui-failure-diagnoser
description: WEB UI 自动化测试（Playwright + Pytest + POM）失败用例智能诊断与全栈自动修复专家。分析 ui-test-executor 输出的执行结果（JUnit XML + sidecar JSON + page-source HTML + console-logs + trace.zip），对失败用例做 6 类分类（ENV/LOCATOR/TIMEOUT/DATA/SCRIPT/BUG）+ 14 种根因定位，自动修复 pages 层 locator 问题、注入 conftest marker、清理测试脏数据、调起 playwright install，并通过 pages.yaml 对比修复定位漂移。**核心约束：永不修改 tests/**/*.py 断言与语义**。
agent_created: true
---

# ui-failure-diagnoser — WEB UI 测试失败诊断与全栈自动修复

## 技能定位

**唯一要做的事：** 把失败用例转成可执行的修复动作。

覆盖范围（按失败类别）：

| 类别 | 子因数 | 自动修复策略 |
|------|-------|-------------|
| **TIMEOUT_ERROR** | 2 | AST rewrite（调 timeout / 加 wait_for_load_state） |
| **LOCATOR_ERROR** | 3 | AST rewrite（iframe）+ Claude 语义推断（locator drift / shadow DOM）+ pages.yaml 金标准对比 |
| **ENV_ERROR** | 4 | 自动执行 shell（playwright install / pip install / lsof）+ 审计日志 |
| **DATA_ERROR** | 2 | 调兄弟技能 api-testdata-cleaner / 提示 seed |
| **BUG** | 1 | 注入 xfail/flaky marker 到 conftest.py（不改断言语义） |
| **SCRIPT_ERROR** | 3 | AST rewrite（method typo / deprecated API / async list wait） |

**硬约束（永不违反）：**
- 🚫 不改 `tests/**/*.py` 的断言与业务语义
- 🟢 可以改 `pages/**/*.py`（locator / timeout / iframe）
- 🟢 可以改 `tests/conftest.py`（只加 marker hook，不改 fixture / 不改 setup 语义）
- 🟢 可以跑 shell（playwright install / pip install / lsof）—— 所有副作用操作都走 AuditLogger

**与上下游 Skill 边界：**

| Skill | 输入 | 输出 |
|-------|------|------|
| ui-test-executor | 标签化脚本 + 执行意图 | JUnit XML + artifacts + sidecar JSON |
| **ui-failure-diagnoser** | **JUnit XML + sidecar + page-source + console-log** | **ui_repair_report.md + .bak + audit.log + 修改后的 pages/conftest** |
| api-testdata-cleaner | 脏数据清理请求 | 清理报告（被本技能 sibling-skill 方式调起） |

---

## 触发场景

**应当触发：**
- "诊断 UI 测试失败"、"分析失败用例根因"、"为什么挂了"
- "修一下这个 locator"、"元素找不到了"、"测试又挂了"
- "自动修复 UI 测试"、"auto fix failing UI tests"
- "page error 怎么处理"、"console 有 5xx"
- "fixture 找不到了"、"user 已被消费"
- "playwright 浏览器没装"、"包没装"

**不应当触发：**
- 跑 UI 测试 → ui-test-executor
- 写新测试脚本 → ui-testscript-generator
- 通用调试方法论 → systematic-debugging
- 视觉回归分析 → ui-visual-assert

---

## 工作流程

### Step 1：定位 Python 解释器 + 确认输入

优先级：
1. 项目虚拟环境（`<project>/.venv/bin/python` / `<project>/venv/bin/python`）
2. 全局 `python3`（含 macOS Homebrew `/usr/local/bin/python3`）

**必需输入**：
- `--junit-xml`：JUnit XML 路径
- `--artifacts-dir`：artifacts 根目录
- `--project-dir`：项目根（含 `pages/`）

**可选输入**：
- `--conftest`：项目 `tests/conftest.py`（bug_repair 注入 marker 需要，默认 `<project>/tests/conftest.py`）
- `--pages-yaml`：项目 pages.yaml（LOCATOR_ERROR 时作金标准对比，可选）
- `--audit-log`：审计日志路径（默认 `<project>/.ui-failure-diagnoser/audit.log`）

### Step 2：加载失败数据

从 `test-results/` 加载：
- `report.xml`：JUnit XML，提取每个失败用例的 nodeid / message / traceback
- `artifacts/page-source/<nodeid>.html`：失败时的 DOM 快照（LOCATOR vs TIMEOUT 的关键证据）
- `artifacts/console-logs/<nodeid>.log`：5 段合并日志（Page Errors / Console / Network）— BUG 金标准
- `artifacts/pytest-raw/<slug>/trace.zip`：失败 trace（人工排查时用）

### Step 3：失败类型分类（6 类）

| 类型 | 判定信号 | 处理 |
|------|---------|------|
| **ENV_ERROR** | `Browser closed` / `Protocol error` / `Executable doesn't exist` / `ModuleNotFoundError` / `ECONNREFUSED` / `Address already in use` | ✅ 自动修复（playwright install / pip install / lsof） |
| **LOCATOR_ERROR** | `TimeoutError` + locator 在 page-source **不存在** | ✅ AST 修复 / pages.yaml 对比 / Claude 语义推断 |
| **TIMEOUT_ERROR** | `TimeoutError` + locator 在 page-source **存在**（渲染慢） | ✅ AST rewrite（调 timeout / 加 wait_for_load_state） |
| **DATA_ERROR** | setup 阶段失败 + fixture 数据问题 + 唯一约束冲突 | ✅ 调 api-testdata-cleaner / 提示 seed |
| **SCRIPT_ERROR** | `AttributeError has no attribute` / `DeprecationWarning` | ✅ AST rewrite（method typo / deprecated api） |
| **BUG** | console-logs 含 Page Error / Uncaught / 网络 5xx | ⚠️ 注入 xfail/flaky marker（不改断言） |

判定优先级：`ENV_ERROR > BUG > LOCATOR/TIMEOUT > DATA_ERROR > SCRIPT_ERROR`
（环境挂了什么都无意义；BUG 是根因；其余按可修复性排序）

### Step 4：根因定位（14 种，全部实装）

| 类别 | 根因 | fix_strategy | 修复方式 |
|------|------|-------------|---------|
| TIMEOUT | `insufficient_wait` | ast_rewrite | `timeout=N` → `max(N*3, 30000)` |
| TIMEOUT | `page_not_loaded` | ast_rewrite | 加 `wait_for_load_state("networkidle")` |
| LOCATOR | `missing_iframe_switch` | ast_rewrite | `page.locator(X)` → `page.frame_locator(...).locator(X)` |
| LOCATOR | `shadow_dom_not_pierced` | claude_semantic | 推荐 `>>>` piercing selector |
| LOCATOR | `locator_drift` | claude_semantic | grep page-source 找候选，Claude 推断 |
| ENV | `missing_browser_binary` | category_repair | `python -m playwright install <browser>` |
| ENV | `missing_python_package` | category_repair | `pip install <package>` |
| ENV | `port_conflict` | category_repair | `lsof -i :<port>` 提示 kill |
| ENV | `service_unavailable` | category_repair | 提示启动后端服务 |
| DATA | `unique_constraint_conflict` | category_repair | 调 api-testdata-cleaner |
| DATA | `fixture_data_missing` | category_repair | 提示 seed 脚本 |
| SCRIPT | `missing_async_list_wait` | ast_rewrite | 在 `get_product_count()` 首行插入 `_wait_for_product_list_loaded()` + base_page helper |
| SCRIPT | `assertion_mismatch` | none | verify 失败升级，仅报告（建议排查后端/数据）|
| BUG | `known_bug_pattern` | category_repair | 注入 xfail/flaky marker 到 conftest |

### Step 5：自动修复（4 个修复模块各司其职）

#### 5.1 AST rewrite（TIMEOUT/LOCATOR）
- `apply_insufficient_wait_fix`：源码级 timeout 字面量替换
- `apply_iframe_switch_fix`：AST 定位 `self._x = page.locator(...)` 加 `frame_locator`
- `apply_method_typo_fix`：AST 定位 `.typo(` 调用，替换为正确方法名（不误伤字符串字面量）
- `apply_deprecated_api_fix`：`query_selector` → `locator` 等 1:1 映射
- 默认 `backup=True`，原文件写 `.bak`；`dry_run=True` 时不写

#### 5.2 ENV 自动修复（env_repair.py）
- `playwright install <browser>`：自动执行（🟢 低风险）
- `pip install <package>`：默认 `auto_run=True`（🟡 中风险，可关闭）
- `lsof -i :<port>`：默认 `auto_run=False`（🔴 需人工确认 kill）

#### 5.3 DATA 数据修复（data_repair.py）
- `sibling_skill` 调起 `api-testdata-cleaner --target <constraint> --mode duplicates`
- fixture 失败：仅输出排查建议（不自动 seed 数据库，避免污染生产共享环境）

#### 5.4 BUG 容错（bug_repair.py）
- 命中 KNOWN_BUG_SIGNATURES → conftest.py 加 `xfail` marker
- 偶发失败（历史记录 mixed pass/fail）→ 加 `flaky` marker
- 网络 5xx → 加 `flaky` marker（瞬时故障）
- 稳定 Page Error → 仅强化报告（不自动 skip，避免掩盖真实 bug）

**marker 注入机制：**
- 写到 `tests/conftest.py` 末尾，通过 `pytest_runtest_setup` hook 给指定 nodeid 加 marker
- 用 signature 注释做幂等：`# ui-failure-diagnoser: marker xfail on <nodeid>`
- 同 marker + 同 nodeid 不重复注入

### Step 6：验证闭环（`--verify` 时）

对每个 ast_rewrite 修复，subprocess 调起单用例重跑。失败的修复自动 rollback `.bak`。
category_repair 不重跑（副作用操作不验证）。

### Step 7：审计与报告

**审计日志**（JSONL）：
- 路径：`<project>/.ui-failure-diagnoser/audit.log`
- 每条记录含：时间戳、命令、退出码、stdout/stderr 尾部、trigger_nodeid、trigger_category

**Markdown 报告**（`ui_repair_report.md`）：
- 概览：分类统计 + 根因统计 + 已应用 AST 修复数 + 已应用类别修复数
- 明细：每条失败的分类、根因、修复动作、target 文件、原始错误

---

## CLI 接口

```bash
python3 scripts/diagnose.py \
    --junit-xml ./test-results/report.xml \
    --artifacts-dir ./test-results/artifacts \
    --project-dir ./shop-lab-ui-test \
    [--conftest ./tests/conftest.py] \
    [--pages-yaml ./pages.yaml] \
    [--audit-log ./.ui-failure-diagnoser/audit.log] \
    [--no-fix] \
    [--dry-run] \
    [--verify] \
    [--base-url http://localhost:3000] \
    [--browser chromium]
```

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `--junit-xml` | Path | 必填 | JUnit XML 路径 |
| `--artifacts-dir` | Path | 必填 | artifacts 根目录 |
| `--project-dir` | Path | 必填 | 项目根（含 `pages/`） |
| `--pages-subdir` | str | `pages` | pages 子目录名 |
| `--conftest` | Path | `<project>/tests/conftest.py` | conftest.py（bug marker 注入） |
| `--pages-yaml` | Path | - | pages.yaml（locator 对比金标准） |
| `--audit-log` | Path | `<project>/.ui-failure-diagnoser/audit.log` | 审计日志 |
| `--output` | Path | `<artifacts>/../ui_repair_report.md` | 报告输出 |
| `--no-fix` | flag | false | 只分类 + 定位，不应用修复 |
| `--dry-run` | flag | false | AST 修复 dry-run 模式（不写文件） |
| `--verify` | flag | false | AST 修复后重跑单用例验证 |
| `--base-url` | str | - | verify 时 base-url |
| `--browser` | str | - | verify 时浏览器 |

退出码：`0` 成功；`2` 输入错误。

---

## 两阶段诊断流程（missing_async_list_wait）

当 SCRIPT_ERROR 用例匹配搜索 0 结果断言时，走特殊两阶段流程：

```
Stage 1: 初次诊断
  SCRIPT_ERROR + 三点信号匹配（搜索 + 期望>0 + 实际=0）
    → root_cause = missing_async_list_wait
    → apply_async_wait_fix()
        · 在 get_product_count() 首行插入 self._wait_for_product_list_loaded()
        · 在 base_page.py 追加 _wait_for_product_list_loaded 方法
    → verify (重跑单用例)

Stage 2: verify 后分类升级
  verify PASS → 保留修改，报告"已修复 missing_async_list_wait"
  verify FAIL → rollback + 升级为 assertion_mismatch
              → 报告"非异步加载问题，建议排查后端搜索接口/测试数据"
```

**信号三点 AND：**
- `_SEARCH_CONTEXT`: 搜索 / search / 查询 / 检索
- `_POSITIVE_EXPECTATION`: 应返回 / 应为 / should return / expected
- `_ZERO_ACTUAL`: 结果数为 0 / count is 0 / returned 0

负向断言（`搜索 'X' 应无结果，但返回 N 个`）不匹配 `_ZERO_ACTUAL`，自动排除。

---

## 关键能力详解

### pages.yaml 金标准对比（LOCATOR_ERROR）

当 page object 中的 locator 失效时，本技能会：
1. 读取 `pages.yaml`（ui-page-parser 的输出，含 `strategy` / `value` / `fallback`）
2. 提取失败 locator 的语义身份（placeholder/label/role/test_id）
3. 在 pages.yaml 中找同身份元素的 canonical locator
4. 输出推荐的新 locator（优先级：`data-testid` > `role` > `label/placeholder/text` > `id` > `css` > `xpath`）

详见 `scripts/pages_yaml_resolver.py`。

### 安全保证

- **永不改 `tests/**/*.py` 断言**：apply_fix.py 只对 `pages/**/*.py` 做 AST rewrite
- **conftest.py 只加 marker hook**：bug_repair.py 通过 signature 注释做幂等 marker 注入，不改 fixture/setup 语义
- **所有副作用走 AuditLogger**：pip install / playwright install / sibling skill 调用都有 JSONL 审计
- **AST rewrite 必 backup**：默认 `.bak`；`dry_run=True` 时不写文件
- **rollback on verify failure**：修复后重跑失败的自动恢复 `.bak`

### 风险分级（自动执行策略）

| 级别 | 操作 | 默认行为 |
|------|------|---------|
| 🟢 低风险 | `playwright install`、AST rewrite、conftest marker | 自动执行 |
| 🟡 中风险 | `pip install`、调兄弟技能清理数据 | 默认执行，可关闭 |
| 🔴 高风险 | `lsof kill`、数据库 seed | 仅输出建议，需人工确认 |
| 🚫 禁止 | 改 `tests/**` 断言、删除文件、force push | 永不执行 |

---

## 典型使用场景

### 场景 1：CI 失败后本地诊断

```bash
python3 scripts/diagnose.py \
    --junit-xml ./test-results/report.xml \
    --artifacts-dir ./test-results/artifacts \
    --project-dir ./shop-lab-ui-test \
    --dry-run
```

生成 `ui_repair_report.md`，不改任何文件。

### 场景 2：自动修复 + 验证

```bash
python3 scripts/diagnose.py \
    --junit-xml ./test-results/report.xml \
    --artifacts-dir ./test-results/artifacts \
    --project-dir ./shop-lab-ui-test \
    --conftest ./tests/conftest.py \
    --pages-yaml ./pages.yaml \
    --verify \
    --browser chromium
```

自动应用 AST 修复、注入 marker、调起 env/data 修复，AST 修复后重跑单用例验证。

### 场景 3：Claude 自然语言触发

用户："login 那两个用例挂了，看下为什么"
→ Claude 调 `diagnose.py`，读报告，对 LOCATOR_ERROR 给候选 selector；对 ENV_ERROR 自动跑 playwright install；对 BUG 注入 xfail marker。

---

## 输出结构

```
<project>/
├── test-results/
│   ├── report.xml                              # JUnit XML（输入）
│   ├── ui_repair_report.md                     # 主诊断报告（输出）
│   └── artifacts/
│       ├── screenshots/、page-source/、console-logs/
│       └── pytest-raw/<slug>/{trace.zip, video.webm}
├── .ui-failure-diagnoser/
│   └── audit.log                               # 副作用操作审计（JSONL）
├── pages/**/*.py                               # AST rewrite 修改 + .bak
└── tests/conftest.py                           # bug_repair 注入 marker
```

---

## 依赖

- `ui-test-executor`：上游，产出 JUnit XML + sidecar + page-source + console-log
- `api-testdata-cleaner`：sibling，被 data_repair 调起清理脏数据（可选，缺失时降级为提示）
- Python 3.10+（标准库 `ast` / `re` / `xml.etree`，无第三方依赖）

---

## 常见问题排查

### Q1：报告说 "page-source 缺失"
项目 conftest 未集成 `ui-test-executor/assets/conftest_template.py` 的失败采集 hook。按 ui-test-executor SKILL.md Step 5 合并。

### Q2：LOCATOR_ERROR 被误判为 TIMEOUT_ERROR
判定信号是「page-source 中是否存在 locator」。若 page-source 缺失，消息含 Timeout 直接归为 TIMEOUT_ERROR（走 ast_rewrite 确定性修复，比 LOCATOR 的语义推断更安全）。

### Q3：AST rewrite 未生效
检查 `pages/**/*.py` 是否符合规范：`self._xxx = page.xxx(...)`。若用 `self.xxx =` 或缺 `self.`，AST 匹配失败。

### Q4：marker 注入重复
`bug_repair._apply_conftest_marker` 用 signature 注释做幂等：`# ui-failure-diagnoser: marker xfail on <nodeid>`。同 marker + 同 nodeid 不重复加。

### Q5：pip install 卡住
`env_repair` 默认 `timeout_sec=120`。可在 `AuditLogger.run_shell` 调用时传入更大 timeout。

---

## 参考文件索引

| 文件 | 用途 | 读取时机 |
|------|------|---------|
| `references/failure_classification.md` | 6 类失败分类的完整规则 + 边界样例 | 分类判定不清时 |
| `references/fix_strategies.md` | 14 种根因的修复配方 + AST rewrite 边界 | 修复不生效 / 自定义策略时 |
| `references/locator_rewriting_guide.md` | Claude 语义修复指引（候选 selector 推断） | LOCATOR_ERROR 根因为定位失效时 |
| `scripts/diagnose.py` | 主入口（编排 Step 1-7） | 每次调用 |
| `scripts/classify_failure.py` | 6 类分类器 | diagnose 内部 |
| `scripts/locate_root_cause.py` | 14 种根因定位器 | diagnose 内部 |
| `scripts/apply_fix.py` | AST rewrite（timeout/iframe/typo/deprecated） | diagnose 内部 |
| `scripts/env_repair.py` | ENV_ERROR 4 子类修复（playwright/pip/lsof/service） | diagnose 内部 |
| `scripts/data_repair.py` | DATA_ERROR 4 子类修复（unique/fixture/user/api） | diagnose 内部 |
| `scripts/bug_repair.py` | BUG 4 子类修复（known/intermittent/5xx/stable） | diagnose 内部 |
| `scripts/pages_yaml_resolver.py` | LOCATOR_ERROR 时 pages.yaml 金标准对比 | diagnose 内部（可选） |
| `scripts/audit_log.py` | 副作用操作审计（JSONL） | 所有 env/data/bug 修复都经过 |
| `scripts/verify_fix.py` | 单用例重跑验证 | diagnose 内部（`--verify`） |
