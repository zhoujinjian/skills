---
name: api-failure-diagnoser
description: 接口自动化测试失败用例智能诊断与自动修复专家。分析 api-test-executor 输出的执行结果，自动分类失败类型（环境问题/数据问题/脚本问题/产品缺陷），定位脚本层根因并生成修复补丁。当用户提到测试失败、用例报错、断言失败、接口变更导致脚本失败、需要修复测试脚本、分析失败原因、运行修复、修复用例、诊断测试结果时触发。也适用于用户提供了 execution_results.json 或失败日志需要排查的场景。上游承接 api-test-executor 执行结果，下游输出修复后的可执行脚本。
agent_created: true
---

# api-failure-diagnoser — 测试失败智能诊断与自动修复

## 概述

接口自动化测试失败用例的智能诊断与自动修复技能，核心定位是"测试执行闭环的修复环节"。聚焦两大能力：**失败诊断**和**脚本自动修复**。

**只做两件事：**
1. 失败诊断：分析 `api-test-executor` 输出的执行结果，自动分类失败类型（环境/数据/脚本/产品缺陷），定位根因
2. 自动修复：针对"脚本问题"类失败，生成修复补丁（更新接口路径、调整断言、同步接口变更、补充异常处理），并验证修复效果

**明确不做：** 环境修复（服务宕机等）、数据修复（测试数据污染等）、产品缺陷修复（业务逻辑错误）、代码架构级重构。

## 触发条件

当用户表述包含以下意图时触发：
- "测试失败了，帮我看看" / "分析一下失败原因" / "诊断失败用例"
- "这个用例报错了" / "断言失败怎么修" / "接口变了脚本挂了"
- "修复一下测试脚本" / "自动修复失败用例" / "跑一下修复"
- 提供了 `execution_results.json` 或失败日志需要排查
- "帮我看看 execution_results" / "失败用例太多了，批量修复"

## 前置条件

在开始工作流之前，确认以下输入已就绪：

1. **execution_results.json**：由 `api-test-executor` 输出的结构化执行结果，必须包含失败用例的详细错误信息、请求/响应快照、错误堆栈
2. **项目目录**：包含原始 pytest 测试脚本的目录，修复将在该目录进行

若用户未提供，主动询问获取路径。

## 工作流

### Step 1: 加载与解析执行结果

1. 读取 `execution_results.json`，提取所有 `status=FAIL` 的用例
2. 对每个失败用例收集：用例ID/名称、文件路径、错误类型、错误信息、请求URL/方法/参数、响应状态码/体、堆栈跟踪
3. 如果文件不存在或格式不合法，向用户报错并终止

### Step 2: 失败类型自动分类

对每个失败用例，按分类规则判定失败类型。详细规则见 `references/failure_classification.md`。

| 失败类型 | 判定信号 | 处理 |
|---------|---------|------|
| ENV_ERROR | 连接超时、拒绝连接、DNS失败、502/503/504 | 不修复，标记环境问题 |
| DATA_ERROR | 资源404（服务正常但数据不存在）、401/403 Token过期、唯一性冲突 | 不修复，标记数据问题 |
| SCRIPT_ERROR | AssertionError、KeyError、TypeError、接口路径404（服务正常）、参数构造错误 | **自动修复** |
| BUG | 500业务逻辑错误、返回数据违反业务规则 | 不修复，生成Bug报告 |

**分类判断的优先级**：先排除 ENV_ERROR（网络层异常），再排除 DATA_ERROR（认证/数据层），再排除 BUG（服务端逻辑错误），剩余归为 SCRIPT_ERROR。

若用户提供了 `--api-doc`（OpenAPI/Swagger文档路径或URL），在分类阶段额外对比接口文档，识别 API 变更类问题（路径变更、参数变更、响应结构变更）。

### Step 3: 根因定位（仅 SCRIPT_ERROR）

对每个 SCRIPT_ERROR 用例，进一步定位根因子类型。详细判定特征和修复策略见 `references/fix_strategies.md`。

| 根因类型 | 典型特征 |
|---------|---------|
| 接口变更 | 请求返回404/405，响应字段与文档不匹配 |
| 断言过严 | 断言非核心字段（时间戳、随机ID），精确匹配不可控值 |
| 参数构造错误 | TypeError/ValueError，缺少必填字段，类型不匹配 |
| 异常处理缺失 | KeyError 在访问响应字段时触发 |
| 数据依赖错误 | 前置步骤参数未传递（Token/ID 为空） |
| 时序/异步问题 | 间歇性失败，重跑可能通过 |

### Step 4: 生成诊断报告

输出 `repair_report.md`，包含：
- 执行摘要（各类失败数量统计）
- 脚本问题详情（每个问题的用例、失败信息、根因、修复操作、修复前后对比）
- 未修复问题清单（环境问题建议、产品缺陷Bug报告）

### Step 5: 自动修复（SCRIPT_ERROR 用例）

对每个 SCRIPT_ERROR 用例执行修复。修复策略见 `references/fix_strategies.md`。

**修复原则：**
- 最小侵入：仅修改导致失败的最小代码范围
- 备份先行：修复前备份原文件为 `.bak`（`--backup=true` 时）
- 默认安全：生成 `.patch` 文件供人工审核（`--auto-fix=false` 时）

**修复操作：**
1. 读取失败用例对应的源文件
2. 定位需要修改的代码行（基于错误堆栈和根因分析）
3. 生成修复补丁（diff格式），记录到 `.patch` 文件
4. 若 `--auto-fix=true`，直接应用修复到源文件
5. 若 `--dry-run`，仅输出修复建议，不修改任何文件

### Step 6: 验证修复效果

当 `--verify=true` 且 `--auto-fix=true` 时：

1. 提取所有已修复用例的文件路径和用例名
2. 组装 pytest 命令，仅运行受影响的用例：
   ```bash
   API_TEST_ENV={env} python3 -m pytest {file}::{class}::{method} -v --tb=short
   ```
3. 判断验证结果：
   - 通过 → 标记修复成功，更新报告
   - 失败 → 回滚到 `.bak` 备份，标记修复失败，记录失败原因到修复日志

### Step 7: 输出结果

向用户展示：
1. 诊断摘要（各类失败数量）
2. 已修复/待修复的脚本问题清单
3. 需人工处理的问题（环境/数据/产品缺陷）
4. 生成文件路径（repair_report.md、.patch 文件、bug_reports/）

## 修复操作速查

| 场景 | 修复前 | 修复后 |
|------|-------|-------|
| 接口路径变更 | `url = f"{BASE_URL}/api/cart/add"` | `url = f"{BASE_URL}/api/v2/cart/items"` |
| 断言过严 | `assert res['data']['createdAt'] == expected_time` | `assert res['data']['createdAt'] is not None` |
| 响应字段重命名 | `assert res['data']['userName']` | `assert res['data']['username']` |
| 参数传递错误 | `token = login_res['token']` | `token = login_res['data']['token']` |
| 缺少异常处理 | 直接访问 `res['data']` | `if res.get('code') != 200: pytest.skip(...)` |
| 新增必填参数 | payload 缺少 `skuId` | 补充 `"skuId": self.sku_id` |

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--auto-fix` | false | true=直接修改原文件，false=生成.patch文件 |
| `--verify` | true | 修复后自动运行受影响用例验证 |
| `--backup` | true | 修复前备份原文件为 .bak |
| `--api-doc` | - | 接口文档路径或URL，用于对比接口变更 |
| `--dry-run` | false | 仅输出诊断报告和修复建议，不修改文件 |

## 前置依赖

- **Python 环境**：Python 3.8+
- **pytest**：用于修复后验证
- **上游 Skill**：`api-test-executor` 输出的 `execution_results.json`
- **可选**：OpenAPI/Swagger 接口文档（`--api-doc`）

## 与上下游 Skill 的关系

- **上游**：`api-test-executor`（执行测试）→ 本 Skill 消费其 `execution_results.json`
- **下游**：修复后的脚本可重新提交给 `api-test-executor` 执行验证

## 注意事项

- **修复边界**：仅修复 SCRIPT_ERROR，环境/数据/产品缺陷标记后交人工处理
- **最小侵入**：每次修复仅改动最小必要代码，不做大规模重构
- **备份机制**：`--backup=true` 自动创建 `.bak` 文件，支持手动回滚
- **验证闭环**：验证失败自动回滚，不留下半成品
- **人工审核**：默认 `--auto-fix=false`，生成 `.patch` 文件降低风险
- **修复记录**：所有操作记录到 `repair_log.md`，便于追溯审计
