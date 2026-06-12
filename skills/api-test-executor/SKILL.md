---
name: api-test-executor
description: 接口自动化测试智能执行调度引擎。当用户需要触发执行 pytest 接口测试、按范围/模块/标签筛选测试用例、用自然语言描述执行意图、收集结构化测试结果时使用此技能。支持三种筛选模式（标签索引/文件路径/自然语言），输出标准化 JSON 和 Markdown 执行报告。典型触发：跑一下冒烟测试、执行登录模块的P0用例、在test环境跑回归、模拟执行看看有哪些用例。
agent_created: true
---

# api-test-executor — 接口测试执行调度引擎

## 概述

接口自动化测试的智能执行调度引擎，核心定位是"测试执行闭环的发动机"。聚焦三大基础能力：**触发执行**、**范围筛选**、**结果收集**，同时支持用户通过自然语言智能选择执行范围。

**只做三件事：**
1. 触发执行：一键触发 pytest，自动加载环境配置、测试数据
2. 范围筛选：标签索引 + 文件路径 + 自然语言三模式，精准圈定执行范围
3. 结果收集：结构化采集每条用例执行状态、耗时、错误信息，输出 JSON 和 Markdown

**明确不做：** 环境深度巡检、分布式调度、实时监控告警、失败根因分析（交给下游 api-failure-diagnoser）。

## 触发条件

当用户表述包含以下意图时触发：
- "跑一下XX测试" / "执行XX用例" / "运行测试"
- "在XX环境跑" / "冒烟测试" / "回归测试"
- "只跑登录模块" / "执行P0用例" / "跑正向场景"
- "模拟执行" / "预览用例" / "看看有哪些用例"
- 提供项目目录路径并要求执行测试

## 工作流

### Step 1: 确认执行参数

若用户以自然语言描述执行意图，先解析为结构化参数，再向用户确认。

解析规则详见 `references/nlp_mapping.md`。

**确认格式示例：**
> 将执行：test 环境，冒烟测试，登录模块，P0 优先级，4 线程并发，确认吗？

若用户已提供明确参数（CLI 形式），跳过此步。

### Step 2: 基础环境检查（轻量级）

执行 `scripts/test_executor.py`，自动完成以下检查：

1. 验证 `testcases/` 目录存在且含测试文件
2. 检查 `config/{env}.yaml` 环境配置是否存在
3. 检查 `tag_index.json` 标签索引是否存在
4. 尝试 HTTP GET 请求 BaseURL（超时 5s，失败不终止，仅 WARNING）

**不做深度巡检**（数据库/Redis 状态等由用户自行确认）。

### Step 3: 执行范围解析

根据项目状态自动选择筛选模式：

**模式 A — 标签索引模式（推荐）：**
- `tag_index.json` 存在时启用
- 根据 `--scope`、`--module`、`--priority`、`--tag`、`--exclude-tag` 组合筛选
- 标签结构规范详见 `references/tag_index_schema.md`

**模式 B — pytest marker 模式（常用）：**
- `tag_index.json` 不存在，但项目 `pytest.ini` 中定义了标准化 markers 时启用
- 使用 `-m "marker_expression"` 精确筛选（如 `-m "smoke and module_auth"`）
- 优先检查项目 `conftest.py` / `pytest.ini` 中的 marker 定义

**模式 C — 文件路径回退模式：**
- 既无 `tag_index.json` 也无标准化 markers 时启用
- 按 `--module` 匹配文件名（如 `test_auth.py` → `module:auth`）
- 打印 WARNING 提示建议先运行 `api-test-tagger`

**模式 D — 自然语言解析模式：**
- 用户输入为自然语言时启用
- 提取关键词映射为 CLI 参数
- 向用户确认解析结果后执行

### Step 4: 执行触发

**优先直接组装 pytest 命令执行**，而非依赖 scripts/test_executor.py 脚本（更灵活、兼容性更好）。

典型执行命令：

```bash
API_TEST_ENV={env} python3 -m pytest {testcases_dir} \
  -m "{marker_expression}" \
  -v \
  --timeout={seconds} \
  --junitxml={output_dir}/junit.xml \
  --alluredir={output_dir}/allure-results \
  --html={output_dir}/html-report/report.html \
  --self-contained-html \
  -p no:xdist \
  --tb=short
```

**关键注意事项：**
1. 使用 `-p no:xdist` 禁用并发（避免 fixture/session 级别共享问题），除非用例间完全独立
2. 项目 `pytest.ini` 中的 `addopts` 可能与命令行冲突，需先检查并临时移除（如 `--alluredir`、`--reruns`）
3. `-m` 表达式根据项目 marker 定义构建（如 `"smoke and module_auth"`、`"P0 or P1"`）
4. `--output` 目录必须指向当前 workspace 内，避免沙箱写入限制
5. 若项目不在当前 workspace，需先 `cp -r` 复制到当前 workspace

### Step 5: 结果收集与输出

从 `junit.xml` 解析结构化结果，手动生成以下文件：

**1. `execution_results.json`** — 结构化执行结果（供下游 Skill 消费）：
- execution_id、环境、范围、筛选条件
- 每条用例状态(PASS/FAIL/SKIP)、耗时、错误信息
- 总通过率统计

**2. `execution_summary.md`** — 执行摘要（供人工浏览）：
- 执行概览表（环境/范围/用例数/通过率/耗时）
- 失败用例清单（用例名/错误类型/错误摘要）

**3. pytest 原生报告：**
- `allure-results/`：Allure 原始数据
- `html-report/report.html`：HTML 测试报告
- `junit.xml`：JUnit XML 格式

### Step 6: 结果呈现

向用户展示：
1. 执行概要统计（总计/通过/失败/跳过/通过率）
2. 失败用例清单（如有）
3. 报告文件路径
4. 后续建议（如"建议运行 api-failure-diagnoser 诊断失败用例"）

## 前置依赖

- **Python 环境**：Python 3.8+
- **pytest 插件**：pytest-xdist、pytest-rerunfailures、pytest-timeout、pytest-html、allure-pytest
- **标签索引**（可选）：由 `api-test-tagger` 生成的 `tag_index.json`，提升筛选精度
- **项目结构**：目标项目须包含 `testcases/` 目录

## 注意事项

- **轻量设计**：聚焦"触发 + 筛选 + 收集"，不做环境巡检、分布式调度、实时监控
- **标签依赖**：建议先运行 `api-test-tagger` 生成标准化标签，否则范围筛选精度下降
- **自然语言确认**：解析后必须向用户确认，避免误执行
- **重试策略**：`--retry` 仅对非断言类失败生效（网络超时等），断言失败重试无意义
- **并发安全**：确保测试数据隔离（建议上游 Skill 处理）
- **Token 传递**：登录类用例优先执行，Token 通过 pytest fixture 共享
- **沙箱限制**：若项目目录在当前 workspace 之外，managed Python 可能无法写入日志/报告文件，需将项目复制到当前 workspace 或使用 `--output` 指向当前 workspace
- **allure-pytest 兼容性**：allure-pytest 2.x 已移除 `allure.environment()` 方法，若项目 conftest.py 使用了此方法，需改为写入 `environment.properties` 文件
- **pytest.ini addopts 冲突**：项目 pytest.ini 中的 `addopts` 可能与命令行参数冲突（如 `--alluredir`、`--reruns`），执行前需检查并临时清理

## 与上下游 Skill 的关系

- **上游**：`api-test-tagger`（生成标签索引）→ 本 Skill 使用标签筛选
- **下游**：`api-failure-diagnoser`（失败根因分析）→ 本 Skill 提供结构化失败数据
