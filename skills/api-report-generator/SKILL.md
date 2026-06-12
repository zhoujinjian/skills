---
name: api-report-generator
description: 接口自动化测试智能报告生成专家。将执行结果、诊断结论和历史数据转化为多维度、可视化、可驱动决策的专业HTML测试报告，集成Allure报告跳转入口实现双报告联动。支持手动调用和上下游技能联动调用（api-test-executor、api-failure-diagnoser、api-testdata-cleaner）。当用户提到生成测试报告、生成报告、测试报告、HTML报告、报告汇总、测试总结、查看报告、report时触发。
agent_created: true
---

# api-report-generator — 接口自动化测试智能报告生成专家

## 概述

将接口测试执行结果、诊断结论和历史数据转化为多维度、可视化、可驱动决策的专业HTML测试报告。集成Allure报告跳转入口，实现双报告联动。

**核心能力：**
1. 多源数据聚合：对接 api-test-executor 执行结果、api-failure-diagnoser 诊断结论、api-testdata-cleaner 清理记录
2. 可视化报告：专业HTML报告，含数据图表（饼图/柱状图/折线图）、模块统计、趋势分析
3. 智能分析：风险分级、高频失败接口识别、优化建议生成
4. Allure联动：自动检索本地Allure报告，嵌入跳转入口

**明确不做：** 测试执行、脚本修复、数据清理、环境部署。

## 触发条件

当用户表述包含以下意图时触发：
- "生成测试报告" / "生成报告" / "出个报告"
- "测试报告" / "HTML报告" / "报告汇总"
- "测试总结" / "查看报告" / "report"
- "帮我生成接口测试报告" / "分析一下执行结果"
- 上游技能（api-test-executor、api-failure-diagnoser、api-testdata-cleaner）联动调用

## 输入参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| exec_data_path | string | **是** | 测试执行结果文件路径（如 execution_results.json） |
| allure_report_path | string | 否 | Allure报告目录路径，为空则自动检索 |
| report_save_path | string | 否 | HTML报告输出目录，默认 `./reports/custom_report` |
| report_title | string | 否 | 报告标题，默认「接口自动化测试报告」 |
| show_chart | bool | 否 | 是否展示数据图表，默认 true |
| auto_link_allure | bool | 否 | 是否添加Allure跳转链接，默认 true |
| auto_trigger | bool | 否 | 是否为上游技能自动联动调用，默认 false |

## 前置条件

1. **exec_data_path** 指向的执行结果文件必须存在
2. 可选关联数据：诊断报告（failure_diagnoser输出）、清理记录（cleaner输出）、历史趋势数据
3. 若需Allure联动，需确认Allure服务已启动或报告目录存在

## 工作流

### Step 1: 数据加载与校验

1. 读取 `exec_data_path` 指向的执行结果文件
2. 校验数据完整性（必须包含：total_cases、passed、failed、时间信息）
3. 若数据缺失，标记异常，继续生成基础报告框架
4. 加载可选关联数据：
   - 诊断报告：`reports/diagnose_report_*.md` 或 `reports/diagnose_*.json`
   - 清理记录：`reports/clean_report_*.md`
   - 历史趋势：`reports/execution_results.json`（多次执行记录）

### Step 2: Allure 报告自动生成与启动

1. 若 `allure_report_path` 已提供，直接使用
2. 否则自动执行以下流程：
   a. **清理旧数据**：清空 `allure-results/` 和 `allure-report/` 目录
   b. **执行测试生成 allure 数据**：运行 `python3 -m pytest {测试命令} --alluredir=reports/allure-results --clean-alluredir`，从执行结果的 scope/filters 参数推断 pytest 命令（如 `-m p0`）
   c. **生成 Allure 报告**：运行 `allure generate reports/allure-results -o reports/allure-report --clean`
   d. **启动 Allure 服务**：在未被占用的端口（优先 8088）运行 `allure open reports/allure-report -p {port}`，后台启动
3. 检测 Allure 服务是否启动成功（`curl -s -o /dev/null -w "%{http_code}" http://localhost:{port}`）
4. 将 Allure 报告 URL（如 `http://localhost:8088`）嵌入 HTML 报告的跳转按钮
5. 若 Allure CLI 未安装或生成失败，标记按钮为灰色 disabled，页面提示安装方式

### Step 3: 数据分析与计算

1. **基础统计**：通过率、失败率、平均耗时、执行时长
2. **模块统计**：按 module 标签分组统计各模块通过率、失败数、平均耗时
3. **优先级统计**：按 P0/P1/P2/P3 分级统计
4. **趋势数据**：对比历史执行结果（最近10次），计算通过率趋势
5. **风险分析**：
   - 高风险模块：通过率低于 70% 的模块
   - 高频失败接口：多次执行持续失败的用例
   - Flaky测试：时而通过时而失败的用例
   - 覆盖率缺口：模块无测试覆盖的情况
6. **优化建议**：基于失败模式生成脚本重构、断言调整、场景补充、环境优化建议

### Step 4: HTML 报告生成

按照 [references/report_template_spec.md](references/report_template_spec.md) 规范生成HTML报告。

#### 页面分区（固定模块）

1. **报告头部**：标题、执行环境、执行时间、报告生成时间
2. **总览大盘**：总用例数、成功/失败/跳过数、通过率、平均响应耗时
3. **趋势图表**：多次执行通过率折线图、接口耗时趋势
4. **模块统计**：按业务模块展示饼图/柱状图，统计通过率、失败率、平均耗时
5. **用例明细**：列表展示所有用例（名称、接口路径、状态、响应时间、标签），支持筛选和分页
6. **故障详情**：失败用例分区展示（报错信息、AI诊断根因、修复建议），按P0优先
7. **数据清理记录**：本次测试后清理执行结果（清理数量、异常信息）
8. **风险分级**：高/中/低风险模块标识，高频失败接口，flaky测试
9. **优化建议**：脚本重构/断言调整/场景补充/环境优化，按优先级排序
10. **Allure跳转**：固定位置「打开Allure原生报告」按钮，新标签页跳转
11. **底部备注**：版本、技能标识、运维备注

#### UI/UX 规范

详见 [references/report_template_spec.md](references/report_template_spec.md)

### Step 5: 文件输出

1. 输出路径：`report_save_path/接口测试报告_{时间戳}.html`
2. 配套资源（CSS/JS/图表）内联到HTML中，生成单文件可独立打开
3. 图表使用 CDN 加载 Chart.js（需联网），同时提供离线降级方案

### Step 6: 结果输出

```json
{
  "status": "success",
  "custom_report_path": "/path/to/接口测试报告_20260611_153000.html",
  "allure_report_url": "http://localhost:8080",
  "report_create_time": "2026-06-11 15:30:00",
  "total_statistics": {
    "total": 83,
    "passed": 77,
    "failed": 0,
    "skipped": 1,
    "pass_rate": "97.5%"
  },
  "error_info": ""
}
```

## 联动调用规范

### 被上游技能调用

```
请调用 api-report-generator，参数如下：
- exec_data_path: /path/to/execution_results.json
- auto_trigger: true
```

### 典型联动场景

1. **api-test-executor 执行完毕** → 自动调用生成报告
2. **api-failure-diagnoser 修复完毕** → 调用生成含诊断结论的报告
3. **api-testdata-cleaner 清理完毕** → 调用生成含清理记录的报告

## 约束规则

1. **单文件输出**：HTML报告内联所有CSS/JS/图表数据，可独立打开
2. **浏览器兼容**：兼容 Chrome、Edge、Firefox 主流浏览器
3. **数据安全**：报告内不泄露敏感账号、密钥、生产数据
4. **容错性**：原始数据缺失时保留页面框架，对应模块标注「暂无数据」
5. **联动一致**：自动触发与手动调用的报告格式、路径规则保持一致
6. **文件命名**：报告文件名含项目名、时间戳，避免覆盖
7. **图表降级**：网络不可用时图表区域显示数据表格替代
