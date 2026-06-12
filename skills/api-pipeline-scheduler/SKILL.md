---
name: api-pipeline-scheduler
description: 接口自动化全链路流水线调度器。作为统一入口编排 api-test-executor（执行测试）、api-testdata-cleaner（清理数据）、api-report-generator（生成报告）三个技能的串行执行，实现一键完成「测试→清理→报告」全流程。支持 full_flow/only_exec/only_clean/only_report 四种执行模式，单环节失败可配置是否继续。当用户提到跑完自动生成报告、全流程执行、一键测试并出报告、流水线、pipeline时触发。
agent_created: true
---

# api-pipeline-scheduler — 接口自动化全链路流水线调度器

## 概述

接口自动化测试的统一调度入口，编排三个独立子技能按固定顺序串行执行，实现从测试执行到数据清理再到报告生成的全链路自动化。

**编排的子技能（固定顺序）：**
1. **api-test-executor** — 执行接口测试，收集结构化执行结果
2. **api-testdata-cleaner** — 清理测试产生的临时数据、脏数据
3. **api-report-generator** — 生成可视化 HTML 测试报告 + Allure 报告联动

**核心能力：**
1. 全链路编排：三个技能严格串行，上一步完成才触发下一步
2. 参数自动透传：环境、文件路径、开关等参数在子技能间自动传递，无需人工干预
3. 灵活执行模式：支持全流程、单独执行、单独清理、单独报告四种模式
4. 容错控制：单环节失败可选继续或终止
5. 统一输出：汇总所有子技能执行状态、文件路径、关键指标

**明确不做：** 测试执行、数据清理、报告生成本身 — 这些由子技能完成，本技能只负责编排调度。

## 触发条件

当用户表述包含以下意图时触发：
- "跑完自动生成报告" / "一键测试并出报告" / "全流程执行"
- "流水线执行" / "pipeline" / "完整流程"
- "跑测试然后清理数据然后出报告" / "测试全流程"
- "执行完自动清理和出报告" / "帮我跑一下完整流程"
- 上游系统或 CI/CD 流水线调用

## 输入参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| project_path | string | **是** | 接口测试项目目录绝对路径 |
| env | string | 否 | 执行环境：dev/test，默认 test |
| scope | string | 否 | 测试范围：标签表达式（如 p0）、文件路径、自然语言描述，默认执行全部 |
| run_mode | string | 否 | 执行模式，默认 full_flow |
| continue_on_error | bool | 否 | 单环节失败是否继续执行后续流程，默认 true |
| report_title | string | 否 | 报告标题，透传给 api-report-generator |
| clean_target | string | 否 | 清理目标：db/redis/file/all，透传给 api-testdata-cleaner，默认 all |
| clean_scope | string | 否 | 清理范围：all/user/cart/order/address，透传给 api-testdata-cleaner，默认 all |

### run_mode 枚举说明

| 模式 | 说明 | 执行链路 |
|------|------|----------|
| full_flow | 全链路串行执行 | executor → cleaner → report-generator |
| only_exec | 仅执行接口测试 | executor |
| only_clean | 仅执行数据清理 | cleaner |
| only_report | 仅生成测试报告 | report-generator |

## 前置条件

1. **project_path** 指向的目录必须是合法的 pytest 接口测试项目
2. 三个子技能已正确安装（api-test-executor、api-testdata-cleaner、api-report-generator）
3. 目标环境可访问（数据库、Redis、API 服务可达）

## 工作流

### Step 1: 参数校验与模式路由

1. 校验 `project_path` 是否存在且包含 `testcases/` 目录
2. 根据 `run_mode` 确定执行链路：
   - `full_flow`：执行全部三个环节
   - `only_exec`：仅执行 Step 2
   - `only_clean`：仅执行 Step 3
   - `only_report`：仅执行 Step 4
3. 记录流水线开始时间

### Step 2: 调用 api-test-executor（测试执行）

1. 构造执行参数：
   ```
   project_path: {project_path}
   env: {env}
   scope: {scope}
   ```
2. 执行 api-test-executor 技能，触发 pytest 运行
3. 收集输出：
   - execution_results.json 路径
   - 执行统计（total/passed/failed/skipped）
   - 通过率
4. 记录本环节状态到 `step_details`
5. 若执行失败且 `continue_on_error=false`，终止流程，跳至 Step 5

**参数透传规则：**
- `project_path` → executor 的项目路径
- `env` → executor 的环境参数
- `scope` → executor 的筛选条件

### Step 3: 调用 api-testdata-cleaner（数据清理）

1. 构造清理参数：
   ```
   env_type: {env}
   clean_scope: {clean_scope}
   clean_target: {clean_target}
   auto_trigger: true
   ```
2. 执行 api-testdata-cleaner 技能
3. 收集输出：
   - 清理报告路径（clean_report_{date}.md）
   - 清理统计（清理条数、保护条数）
4. 记录本环节状态到 `step_details`
5. 若清理失败且 `continue_on_error=false`，终止流程，跳至 Step 5

**参数透传规则：**
- `env` → cleaner 的 env_type
- `clean_scope` → cleaner 的清理范围
- `clean_target` → cleaner 的清理目标
- `auto_trigger: true` → 标记为联动调用

### Step 4: 调用 api-report-generator（报告生成）

1. 构造报告参数：
   ```
   exec_data_path: {Step 2 输出的 execution_results.json 路径}
   allure_report_path: {自动从 project_path 检索}
   report_save_path: {project_path}/reports/custom_report
   report_title: {report_title}
   auto_trigger: true
   ```
2. 执行 api-report-generator 技能，该技能内部会自动：
   - 清理旧 allure-results
   - 重新运行 pytest 生成 allure 数据
   - 运行 `allure generate` 生成 Allure 报告
   - 启动 Allure 服务
   - 生成 HTML 测试报告
3. 收集输出：
   - HTML 报告路径
   - Allure 报告 URL
   - 报告生成时间
4. 记录本环节状态到 `step_details`

**参数透传规则：**
- `execution_results.json` 路径 → 从 Step 2 输出获取
- `clean_report` 路径 → 从 Step 3 输出获取（如有）
- `project_path` → 用于检索 allure-results、allure-report 目录
- `report_title` → 透传报告标题
- `auto_trigger: true` → 标记为联动调用

### Step 5: 汇总输出全链路报告

汇总所有环节的执行结果，输出标准化全链路报告：

```json
{
  "pipeline_id": "pipeline_{timestamp}",
  "run_mode": "full_flow",
  "project_path": "/path/to/project",
  "env": "test",
  "start_time": "2026-06-12 10:00:00",
  "end_time": "2026-06-12 10:02:30",
  "duration_s": 150.5,
  "full_status": "success",
  "continue_on_error": true,
  "step_details": [
    {
      "step": 1,
      "skill": "api-test-executor",
      "status": "success",
      "duration_s": 15.3,
      "output": {
        "execution_results_path": "/path/to/execution_results.json",
        "total_cases": 78,
        "passed": 77,
        "failed": 0,
        "skipped": 1,
        "pass_rate": "98.7%"
      },
      "error": ""
    },
    {
      "step": 2,
      "skill": "api-testdata-cleaner",
      "status": "success",
      "duration_s": 3.2,
      "output": {
        "clean_report_path": "/path/to/clean_report_2026-06-12.md",
        "cleaned_count": 515,
        "protected_count": 23
      },
      "error": ""
    },
    {
      "step": 3,
      "skill": "api-report-generator",
      "status": "success",
      "duration_s": 20.8,
      "output": {
        "custom_report_path": "/path/to/接口测试报告_20260612_100030.html",
        "allure_report_url": "http://localhost:8088",
        "report_create_time": "2026-06-12 10:00:30"
      },
      "error": ""
    }
  ],
  "summary": {
    "total_steps": 3,
    "success_steps": 3,
    "failed_steps": 0,
    "test_pass_rate": "98.7%",
    "cleaned_data_count": 515,
    "report_path": "/path/to/接口测试报告_20260612_100030.html",
    "allure_url": "http://localhost:8088"
  }
}
```

**状态判定规则：**
- `full_status = success`：所有环节均成功
- `full_status = partial`：部分环节成功、部分失败（continue_on_error=true 时出现）
- `full_status = failed`：任一环节失败且 continue_on_error=false 导致终止，或所有环节均失败

### Step 6: 输出全链路执行摘要

向用户展示简洁的全链路执行摘要：

```
=== 全链路流水线执行报告 ===
流水线ID: pipeline_20260612_100000
模式: full_flow | 环境: test
总耗时: 150.5s

[Step 1] api-test-executor    ✅ success (15.3s)
  → 78 用例 | 77 通过 | 0 失败 | 1 跳过 | 通过率 98.7%

[Step 2] api-testdata-cleaner  ✅ success (3.2s)
  → 清理 515 条 | 保护 23 条 | 状态 success

[Step 3] api-report-generator  ✅ success (20.8s)
  → HTML 报告: /path/to/接口测试报告_20260612_100030.html
  → Allure: http://localhost:8088

整体状态: ✅ success
```

## 联动调用规范

### 手动调用

```
请调用 api-pipeline-scheduler，参数如下：
- project_path: /path/to/shop-lab-api-test
- env: test
- scope: p0
- run_mode: full_flow
```

### 自然语言触发

- "帮我跑一下完整流程" → full_flow，使用默认参数
- "在 test 环境跑 P0 然后自动清理出报告" → full_flow，scope=p0，env=test
- "只生成报告" → only_report，需要先确认 execution_results.json 路径

### CI/CD 集成

支持通过 schedule 技能或 CronCreate 定时触发：
- 每日构建后自动执行 full_flow
- 测试环境部署后自动触发回归测试

## 约束规则

1. **严格串行**：子技能按固定顺序执行，不并行
2. **参数透传**：自动将上游输出作为下游输入，用户无需手动传递文件路径
3. **子技能独立**：三个子技能可独立调用，本技能不影响其原有功能
4. **容错控制**：continue_on_error=true 时记录失败但继续执行，false 时立即终止
5. **幂等性**：重复调用不会产生副作用（清理、报告均支持重复执行）
6. **日志追溯**：每个环节记录详细状态、耗时、异常信息，便于排查
7. **环境隔离**：仅允许 dev/test 环境，prod 环境直接拦截
