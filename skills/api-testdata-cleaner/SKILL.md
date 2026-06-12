---
name: api-testdata-cleaner
description: 接口自动化测试数据清理工具。自动清理测试执行后产生的临时数据、重复数据、脏数据，覆盖数据库、Redis缓存、本地临时文件三层清理。支持手动独立调用、上下游技能联动调用（api-test-executor、api-failure-diagnoser）、CI定时调用三种模式。生产环境强制拦截。当用户提到清理测试数据、清除脏数据、数据重置、清理缓存、重置测试环境、测试数据清理时触发。
agent_created: true
---

# api-testdata-cleaner — 接口测试数据清理工具

## 概述

接口自动化测试专用的数据清理工具，解决测试执行后的数据堆积与数据污染问题。支持三层清理：数据库、Redis缓存、本地临时文件。

**核心能力：**
1. 数据库清理：清空测试产生的临时账号、商品、分类、订单等数据
2. 缓存清理：清理 Redis 中登录 Token、验证码、临时缓存、接口会话数据
3. 本地文件清理：清理测试过程生成的日志、报文、临时数据文件

**明确不做：** 生产环境数据操作（强制拦截）、正式业务数据删除、系统配置变更。

## 触发条件

当用户表述包含以下意图时触发：
- "清理测试数据" / "清除脏数据" / "数据重置"
- "重置测试环境" / "清理缓存" / "清理临时文件"
- "测试完清理一下" / "跑完清理数据" / "数据太多了清理"
- "testdata clean" / "clean test data"
- 上游技能（api-test-executor、api-failure-diagnoser）联动调用

## 输入参数

通过用户自然语言描述解析，或由上游技能以 JSON 格式传入：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| env_type | string | 否 | 执行环境：dev/test/prod，**prod 直接拦截**，默认 test |
| clean_scope | string | 否 | 清理范围：all/user/cart/order/address，默认 all |
| clean_target | string | 否 | 清理目标：db/redis/file/all，默认 all |
| keep_debug_data | bool | 否 | true=保留调试数据，false=强制全量清理，默认 false |
| auto_trigger | bool | 否 | 是否为其他技能自动联动调用，默认 false |
| protect_white_list | bool | 否 | true=启用白名单保护核心数据，默认 true |

## 工作流

### Step 1: 环境校验与安全拦截

1. 解析 `env_type` 参数
2. **若 env_type = prod**：立即终止执行，输出拦截警告，不执行任何清理操作
3. 记录执行开始时间

### Step 2: 加载配置与建立连接

1. 读取项目对应环境的配置文件（config/{env}.yaml）
2. 获取数据库连接信息（host/port/name/username/password）
3. 获取 Redis 连接信息（若有配置）
4. 建立连接，连接失败时记录异常并标记该数据源不可用，继续后续操作

### Step 3: 白名单加载

1. 读取白名单配置（protect_white_list=true 时启用）
2. 白名单核心保护项：
   - **admin 管理员账号**：永久保留，不参与任何清理
   - **人工预录的正式业务数据**：具备明确业务含义的数据保留
   - **系统基础配置数据**：验证码配置、系统参数等保留
3. 白名单规则详见 [references/whitelist_rules.md](references/whitelist_rules.md)

### Step 4: 分层清理执行

根据 `clean_scope` 和 `clean_target` 参数组合执行清理：

#### 4.1 数据库清理（clean_target=db/all）

按 `clean_scope` 逐模块执行，单模块失败不中断整体流程：

- **user 模块**：清理测试注册的临时用户（username 包含 test/测试/logout/pwdtest/_init 等特征）
- **cart 模块**：清理测试产生的购物车记录
- **order 模块**：清理测试产生的临时订单
- **address 模块**：清理测试产生的临时地址
- **product 模块**：清理测试创建的临时商品（name 包含 测试商品 等特征）
- **category 模块**：清理测试创建的临时分类（name 包含 测试分类 等特征）
- **banner 模块**：清理测试创建的临时轮播图
- **captcha_record 模块**：清理验证码使用记录

**数据判定规则（重要）：**
- 明确可清理：字段中包含 test/测试/logout/pwdtest/_init/temp 等标识的测试数据
- 存疑数据：无法明确判定来源的数据，**标记为待确认，不直接删除**
- 白名单数据：admin 账号、人工预录数据，永久保留

#### 4.2 Redis 缓存清理（clean_target=redis/all）

- 清理 `captcha:*` 前缀的验证码缓存
- 清理登录 Token 相关缓存
- 清理接口会话临时数据
- 注意：不清理 captcha_config 等系统配置缓存

#### 4.3 本地文件清理（clean_target=file/all）

- 清理 logs/ 目录下的过期日志文件
- 清理 allure-results/ 目录下的历史报告文件
- 清理 .pytest_cache/ 目录
- 若 keep_debug_data=true，保留最近的日志文件（最近 1 小时内的）

### Step 5: 异常容错

- 单模块清理失败：记录错误日志，标记该模块状态为 failed，继续执行其他模块
- 连接失败：标记整个数据源为 unavailable，跳过该数据源的所有操作
- SQL 执行失败：回滚当前事务，记录异常，继续下一条

### Step 6: 结果汇总与报告

输出标准化清理报告，格式如下：

```
=== 测试数据清理报告 ===
环境: test
执行时间: 2026-06-11 15:30:00
耗时: 1.23s

【数据库清理】
- 用户表: 清理 15 条临时用户, 状态: success
- 购物车表: 清理 8 条记录, 状态: success
- 订单表: 清理 3 条临时订单, 状态: success
- 地址表: 清理 6 条临时地址, 状态: success
- 商品表: 清理 2 条测试商品, 状态: success
- 分类表: 清理 1 条测试分类, 状态: success
- 验证码记录: 清理 25 条, 状态: success

【缓存清理】
- 验证码缓存: 清理 12 项, 状态: success

【文件清理】
- 日志文件: 清理 5 个, 状态: success
- allure-results: 清理 0 个, 状态: skip

【总计】
清理数据条数: 60
清理缓存项: 12
清理文件数: 5
执行状态: success
白名单保护: 启用 (admin 账号已保护)
```

## 报告落盘

每次执行清理后，**必须**将清理报告保存到项目 `reports/` 目录下，文件名格式：`clean_report_{日期}.md`。

保存路径：`{project_dir}/reports/clean_report_{YYYY-MM-DD}.md`

报告内容包含：
1. 基本信息表（环境、执行时间、白名单状态、清理目标、清理范围）
2. 数据库清理明细表（表名、清理前/后数量、清理条数、状态、说明）
3. 缓存清理明细（如涉及）
4. 文件清理明细（如涉及）
5. 白名单保护数据清单
6. 测试数据判定依据
7. 清理总计

## 联动调用规范

### 被上游技能调用

api-test-executor 或 api-failure-diagnoser 可在执行完成后自动调用本技能：

```
请调用 api-testdata-cleaner，参数如下：
- env_type: test
- clean_scope: all
- clean_target: db
- auto_trigger: true
```

### CI 定时调用

支持通过 Claude Code 的 CronCreate 调度定时执行：
- 每日构建后自动清理测试环境数据
- 测试套件执行完毕后触发清理

## 约束规则

1. **生产环境保护**：env_type=prod 时强制拦截，输出警告，不执行任何操作
2. **白名单保护**：admin 账号、正式业务数据永久保留，不参与清理
3. **断点容错**：单模块失败不中断整体流程，记录异常继续执行
4. **编码规范**：复用项目现有工具类（utils/logger.py），统一日志格式
5. **审计留痕**：每一步清理操作都写入日志，便于后续审计追溯
6. **存疑保留**：不确定是否为测试数据时，标记待确认，不直接删除
7. **联动兼容**：支持手动调用和自动调用两种模式，auto_trigger=true 时输出更简洁
