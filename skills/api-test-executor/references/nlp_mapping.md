# 自然语言 → 执行参数映射规则

## 映射表

| 用户表述 | 解析参数 | 值 |
|---------|---------|---|
| 冒烟 / smoke / 核心链路 | `--scope` | `smoke` |
| 回归 / regression | `--scope` | `regression` |
| 全量 / 所有用例 / 全部 | `--scope` | `full` |
| dev 环境 / 开发环境 | `--env` | `dev` |
| test 环境 / 测试环境 | `--env` | `test` |
| pre 环境 / 预发环境 / 预发布 | `--env` | `pre` |
| P0 / 高优先级 / 最高优先级 | `--priority` | `P0` |
| P1 / 中优先级 | `--priority` | `P1` |
| P2 / 低优先级 | `--priority` | `P2` |
| P3 | `--priority` | `P3` |
| 正向 / 正常流程 / 成功场景 | `--tag` | `scene:positive` |
| 反向 / 异常 / 异常场景 | `--tag` | `scene:negative` |
| 边界 / 边界值 | `--tag` | `scene:boundary` |
| 排除不稳定 / 跳过 flaky / 排除 flaky | `--exclude-tag` | `flaky` |
| N 个线程 / 并发 N | `--parallel` | N |
| 重试 N 次 / 失败重试 N | `--retry` | N |
| 模拟 / 预览 / 看看哪些 / dry-run | `--dry-run` | true |

## 模块别名映射

| 中文关键词 | 映射模块 |
|-----------|---------|
| 登录 / 认证 / 鉴权 / 注册 | `auth` |
| 订单 / 下单 | `order` |
| 支付 / 付款 | `payment` |
| 商品 / 产品 | `product` |
| 用户 / 会员 | `user` |
| 购物车 | `cart` |
| 搜索 | `search` |
| 评论 / 评价 | `review` |
| 物流 / 配送 | `logistics` |
| 退款 / 售后 | `refund` |
| 地址 | `address` |
| 收藏 / 关注 | `favorite` |
| 通知 / 消息 | `notification` |
| 优惠券 | `coupon` |

## 组合语义解析示例

| 自然语言输入 | 解析结果 |
|------------|---------|
| 在 test 环境跑一下冒烟测试，只跑登录和订单模块的 P0 用例，排除 flaky | `--env test --scope smoke --module auth,order --priority P0 --exclude-tag flaky` |
| 用 8 个线程跑回归测试，失败重试 3 次 | `--scope regression --parallel 8 --retry 3` |
| 模拟执行一下，看看支付模块有哪些正向场景用例 | `--dry-run --module payment --tag scene:positive` |
| 只跑 P0 和 P1 的登录和认证模块 | `--priority P0,P1 --module auth` |

## 模糊语义容错

| 用户表述 | 处理策略 |
|---------|---------|
| 跑一下核心链路 | 解析为 `--scope smoke`，或提示用户确认是否要 `--priority P0` |
| 跑新加的用例 | 无增量检测能力，提示用户指定模块或标签 |
| 跑最近失败的 | 提示用户查看历史执行记录，或尝试 `--exclude-tag stable` 间接筛选 |

## 注意事项

- 自然语言解析后，**必须向用户展示解析结果并请求确认**，避免误执行
- 多个同类参数自动合并为逗号分隔（如"登录和订单" → `--module auth,order`）
- 中文模块名通过别名表映射为英文，映射表可在脚本中扩展
- 无法解析的部分保留原文，作为提醒信息展示给用户
