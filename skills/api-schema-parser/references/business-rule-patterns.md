# 隐性业务规则识别模式库

本文档定义了从接口文档描述和定义中识别隐性业务规则的模式和策略。

---

## 1. 规则类别概览

| 类别 | category 值 | 核心关键词 | 置信度评估 |
|------|------------|-----------|-----------|
| 限流策略 | rate_limiting | 限流、频率、QPS、限次、rate limit、throttle | 明确数值→high，模糊描述→medium |
| 加密规则 | encryption | 加密、签名、MD5、RSA、AES、SHA、encrypt、sign、crypto | 明确算法→high，仅提加密→medium |
| 鉴权方式 | authentication | Token、OAuth、Bearer、APIKey、鉴权、认证、授权、auth | 明确方式→high，仅提需鉴权→medium |
| 接口依赖 | dependency | 依赖、前置、先调用、前置条件、前置接口、需先、depend | 明确说明→high，推断→low |
| 数据一致性 | consistency | 事务、原子、一致性、回滚、transaction、atomic | 明确声明→high，推断→low |
| 幂等性 | idempotency | 幂等、重复、去重、防重、idempotent | 明确声明→high，推断→low |
| 数据脱敏 | data_masking | 脱敏、掩码、隐藏、遮盖、mask、desensitize | 明确声明→high，推断→low |
| 并发控制 | concurrency | 并发、锁、互斥、分布式锁、乐观锁、concurrent、lock | 明确声明→high，推断→low |

---

## 2. 各类别详细识别模式

### 2.1 限流策略 (rate_limiting)

**关键词模式**：

| 模式 | 正则 | 示例 |
|------|------|------|
| QPS 限制 | `(\d+)\s*[次/QPS/qps]/\s*[秒/分钟/小时/min/hour]` | "100次/分钟"、"50 QPS" |
| IP 限流 | `同一\s*IP.*?(\d+).*?[次/请求]` | "同一IP每分钟最多100次请求" |
| 用户限流 | `同一\s*用户.*?(\d+).*?[次/请求]` | "同一用户每天最多创建10个订单" |
| 接口限流 | `该接口.*?(\d+).*?[次/请求]` | "该接口限流100次/分钟" |
| Header 限流 | `X-RateLimit` | "响应头含 X-RateLimit-Remaining" |

**识别来源优先级**：
1. OpenAPI extension: `x-rate-limit`
2. Swagger/OpenAPI description 文本
3. 响应 Header 中的 Rate-Limit 相关字段
4. 纯文本描述

**输出示例**：
```yaml
business_rules:
  - rule_id: "BR-001"
    category: "rate_limiting"
    description: "同一IP每分钟最多100次请求，超过返回429状态码"
    affected_apis: ["GET_/api/v1/products"]
    source: "openapi_extension"
    confidence: "high"
```

### 2.2 加密规则 (encryption)

**关键词模式**：

| 模式 | 正则 | 示例 |
|------|------|------|
| 加密算法 | `(RSA|AES|DES|MD5|SHA[0-9]*|HMAC)\s*[-–—]\s*` | "RSA加密传输" |
| 签名算法 | `签名.*?(HMAC|SHA|MD5|RSA)` | "请求签名算法为HMAC-SHA256" |
| 加密字段 | `(密码|手机号|身份证).*?加密` | "密码字段需RSA加密" |
| 传输加密 | `(HTTPS|SSL|TLS)` | "接口必须使用HTTPS" |

**推断规则**：
- description 中含 "密码" + 无 "明文" → 推断需加密（confidence: low）
- 明确提到加密算法 → confidence: high
- 仅提到 "加密" 无算法细节 → confidence: medium

**输出示例**：
```yaml
business_rules:
  - rule_id: "BR-002"
    category: "encryption"
    description: "请求体中的password字段需使用RSA公钥加密传输"
    affected_apis: ["POST_/api/v1/users", "PUT_/api/v1/users/password"]
    source: "swagger_description"
    confidence: "high"
```

### 2.3 鉴权方式 (authentication)

**关键词模式**：

| 模式 | 识别规则 | 示例 |
|------|---------|------|
| Bearer Token | Header 含 `Authorization: Bearer` | "Authorization: Bearer {token}" |
| API Key | Header 含 `X-API-Key` 或 Query 含 `api_key` | "请求头需携带 X-API-Key" |
| OAuth2 | security 定义含 OAuth2 flows | "OAuth2 授权码模式" |
| Basic Auth | Header 含 `Authorization: Basic` | "HTTP Basic 认证" |
| 自定义 Token | Header 含 `X-Auth-Token` / `X-Access-Token` | "请求头 X-Auth-Token" |
| 无需鉴权 | 明确标注 "无需鉴权" / "公开接口" | "此接口为公开接口" |

**识别来源**：
1. OpenAPI `security` + `securitySchemes` 定义 → confidence: high
2. Swagger `security` 定义 → confidence: high
3. Header 参数中含 Authorization/Token 相关字段 → confidence: medium
4. 描述文本中提及 → confidence: low

**输出示例**：
```yaml
global_rules:
  authentication:
    type: "Bearer Token"
    header: "Authorization"
    description: "所有需鉴权的接口在Header中携带 Bearer Token，Token有效期为2小时"

business_rules:
  - rule_id: "BR-003"
    category: "authentication"
    description: "创建用户接口需要管理员权限，普通用户调用返回403"
    affected_apis: ["POST_/api/v1/users"]
    source: "text_inference"
    confidence: "medium"
```

### 2.4 接口依赖 (dependency)

**关键词模式**：

| 模式 | 正则 | 示例 |
|------|------|------|
| 前置调用 | `需?(要先|必须先|前置).*?调用.*?(接口|API)` | "必须先调用登录接口获取Token" |
| 依赖描述 | `依赖.*?接口` | "此接口依赖获取验证码接口" |
| ID 依赖 | `.*?ID.*?需.*?(获取|调用)` | "订单ID需通过创建订单接口获取" |
| 顺序约束 | `步骤[一二三四12].*?` | "步骤一：获取Token；步骤二：创建订单" |

**推断规则**：
- 路径参数引用其他接口返回的 ID → 推断依赖（confidence: medium）
- 明确描述依赖关系 → confidence: high
- 隐含顺序（如先登录后操作） → confidence: low

**输出示例**：
```yaml
business_rules:
  - rule_id: "BR-004"
    category: "dependency"
    description: "创建订单前需先获取用户地址列表，创建订单接口的address_id参数来自地址列表接口的返回值"
    affected_apis: ["POST_/api/v1/orders"]
    source: "text_inference"
    confidence: "medium"
```

### 2.5 数据一致性 (consistency)

**关键词模式**：

| 模式 | 正则 | 示例 |
|------|------|------|
| 事务描述 | `事务|transaction` | "转账操作需在事务中执行" |
| 原子操作 | `原子|atomic` | "扣减库存和创建订单需原子操作" |
| 一致性要求 | `一致性|consistency` | "保证数据最终一致性" |
| 回滚 | `回滚|rollback` | "支付失败需回滚订单状态" |

**输出示例**：
```yaml
business_rules:
  - rule_id: "BR-005"
    category: "consistency"
    description: "下单扣减库存和创建订单需在同一事务中，任一步骤失败则全部回滚"
    affected_apis: ["POST_/api/v1/orders"]
    source: "swagger_description"
    confidence: "high"
```

### 2.6 幂等性 (idempotency)

**关键词模式**：

| 模式 | 正则 | 示例 |
|------|------|------|
| 幂等声明 | `幂等|idempotent` | "支付接口保证幂等" |
| 防重复 | `防重|去重|防重复|dedup` | "防重复提交" |
| 重复处理 | `重复.*?(不|忽略|返回)` | "重复请求返回原结果" |
| 幂等键 | `Idempotency-Key|Request-Id` | "请求头携带 Idempotency-Key" |

**推断规则**：
- POST/PUT 接口描述含 "重复" → 推断需幂等（confidence: low）
- 明确声明幂等 → confidence: high
- Header 含 Idempotency-Key → confidence: high

### 2.7 数据脱敏 (data_masking)

**关键词模式**：

| 模式 | 正则 | 示例 |
|------|------|------|
| 脱敏描述 | `脱敏|掩码|遮盖|mask|desensitize` | "手机号脱敏返回" |
| 格式描述 | `\d+\*+\d+` | "138****5678" |
| 隐藏字段 | `隐藏|不返回|不展示` | "密码字段不返回" |

**推断规则**：
- 响应体含手机号/身份证/银行卡等敏感字段但无脱敏描述 → 标记提醒（confidence: low）
- 明确提到脱敏 → confidence: high

### 2.8 并发控制 (concurrency)

**关键词模式**：

| 模式 | 正则 | 示例 |
|------|------|------|
| 锁机制 | `锁|lock|mutex` | "分布式锁控制库存扣减" |
| 并发限制 | `并发|concurrent|同时` | "同一账户不支持并发操作" |
| 互斥 | `互斥|exclusive` | "同一订单的支付操作互斥" |
| 乐观锁 | `乐观锁|optimistic|version` | "使用乐观锁更新数据" |

---

## 3. 多规则关联识别

当一个接口的描述中同时涉及多个规则类别时，需分别识别并关联：

```
输入描述："支付接口需要Bearer Token鉴权，同一用户5分钟内最多支付3次，
         支付操作保证幂等，需在事务中执行扣款和更新订单状态"
```

识别结果：
```yaml
business_rules:
  - rule_id: "BR-006"
    category: "authentication"
    description: "支付接口需要Bearer Token鉴权"
    affected_apis: ["POST_/api/v1/payments"]
    source: "text_inference"
    confidence: "medium"
  - rule_id: "BR-007"
    category: "rate_limiting"
    description: "同一用户5分钟内最多支付3次"
    affected_apis: ["POST_/api/v1/payments"]
    source: "text_inference"
    confidence: "medium"
  - rule_id: "BR-008"
    category: "idempotency"
    description: "支付操作保证幂等"
    affected_apis: ["POST_/api/v1/payments"]
    source: "text_inference"
    confidence: "medium"
  - rule_id: "BR-009"
    category: "consistency"
    description: "扣款和更新订单状态需在事务中执行"
    affected_apis: ["POST_/api/v1/payments"]
    source: "text_inference"
    confidence: "medium"
```

---

## 4. 置信度评估规则

### 4.1 High 置信度

以下情况标记为 high：
- 规则来自 OpenAPI/Swagger 的正式扩展字段（如 `x-rate-limit`、`security`）
- 规则来自接口描述中明确声明的完整规则（含具体数值和条件）
- 规则来自 YApi/Apifox 的业务规则标注
- 规则由用户手动补充提供

### 4.2 Medium 置信度

以下情况标记为 medium：
- 规则从接口描述中推断，描述含关键信息但不够完整
- 从 Header 参数推断的鉴权规则（含 Token 相关字段但未明确类型）
- 从路径参数关联推断的接口依赖关系

### 4.3 Low 置信度

以下情况标记为 low：
- 规则从业务常识推断，文档中未明确提及
- 仅根据字段名（如 "password"）推断的加密需求
- 仅根据接口语义推断的幂等性需求
- 仅根据响应结构推断的脱敏需求

---

## 5. 规则编号规则

- 格式：`BR-{NNN}`，全局连续编号
- 按识别顺序递增，不按类别分组
- 混合输入时，合并后重新编号

---

## 6. 常见业务规则模板

### 6.1 电商系统常见规则

| 规则 | category | 典型描述 |
|------|----------|---------|
| 库存扣减原子性 | consistency | "下单扣减库存需原子操作，超卖时回滚" |
| 支付幂等性 | idempotency | "支付接口需保证幂等，重复请求不重复扣款" |
| 订单超时 | dependency | "未支付订单30分钟自动关闭，需先创建订单再支付" |
| 价格校验 | consistency | "下单时校验商品价格与当前价格一致" |
| 用户信息脱敏 | data_masking | "用户手机号、身份证号脱敏返回" |
| 秒杀限流 | rate_limiting | "秒杀接口限流1000 QPS" |

### 6.2 金融系统常见规则

| 规则 | category | 典型描述 |
|------|----------|---------|
| 转账事务性 | consistency | "转账操作需在事务中执行，保证双方账户一致性" |
| 交易防重 | idempotency | "交易请求需防重复提交" |
| 敏感信息加密 | encryption | "银行卡号、密码等敏感信息需加密传输" |
| 风控限流 | rate_limiting | "异常交易频率触发风控限流" |
| 余额一致性 | consistency | "扣款后账户余额不能为负" |

### 6.3 社交系统常见规则

| 规则 | category | 典型描述 |
|------|----------|---------|
| 发帖限频 | rate_limiting | "同一用户每分钟最多发5条动态" |
| 内容审核 | dependency | "发布内容需先经过审核接口" |
| 好友关系互斥 | concurrency | "同时添加好友需处理互斥" |
| 个人信息脱敏 | data_masking | "用户手机号仅对本人展示完整号码" |
