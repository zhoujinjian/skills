# 失败类型分类规则

## 分类优先级

判定顺序：**ENV_ERROR → DATA_ERROR → BUG → SCRIPT_ERROR**

优先排除环境、数据、产品缺陷后，剩余均归为脚本问题。

---

## ENV_ERROR（环境问题）

### 判定信号

从错误信息中检测以下模式：

**连接层异常：**
- `ConnectTimeout` / `ConnectionTimeout`
- `ConnectionRefusedError` / `Connection refused`
- `Max retries exceeded`
- `NameResolutionError` / `DNS resolution failed` / `getaddrinfo failed`
- `Network is unreachable`

**服务层异常（非业务）：**
- HTTP 502 Bad Gateway（上游服务不可用）
- HTTP 503 Service Unavailable（服务过载/维护中）
- HTTP 504 Gateway Timeout（上游响应超时）

**关键区分点：** 如果部分接口正常返回但某些接口超时，且超时的接口是核心接口，可能是环境问题；如果是边缘接口偶发超时，可能需要重新判定。

### 输出标记

```json
{
  "failure_type": "ENV_ERROR",
  "suggestion": "检查目标服务是否启动，网络配置是否正确，服务端口是否可达"
}
```

---

## DATA_ERROR（数据问题）

### 判定信号

**认证/授权类（非脚本逻辑）：**
- HTTP 401 Unauthorized（Token 过期或未设置——但 Token 获取逻辑正确时）
- HTTP 403 Forbidden（权限不足——非脚本构造错误时）

**资源不存在（服务正常但数据缺失）：**
- HTTP 404 Not Found（服务健康检查通过，但请求的资源 ID 不存在）
- `RecordNotFound` / `Resource not found`

**数据校验冲突：**
- `IntegrityError` / `UniqueViolation` / `DuplicateKeyError`（唯一性约束冲突）
- `ForeignKeyViolation`（外键约束，依赖数据不存在）
- `DataValidationError`（数据格式不符合约束，非脚本构造错误）

**关键区分点：**
- 401/403：如果 Token 获取步骤本身逻辑正确但 Token 过期，归为 DATA_ERROR；如果 Token 传递代码写错了（如取错字段），归为 SCRIPT_ERROR
- 404：如果接口路径正确但资源 ID 对应的数据已被清理，归为 DATA_ERROR；如果接口路径本身就写错了，归为 SCRIPT_ERROR

### 输出标记

```json
{
  "failure_type": "DATA_ERROR",
  "suggestion": "检查测试数据是否有效，Token是否过期，依赖资源是否存在"
}
```

---

## BUG（产品缺陷）

### 判定信号

**服务端逻辑错误：**
- HTTP 500 Internal Server Error（排除环境问题后，确认是业务代码异常）
- 响应体中包含服务端异常堆栈（`NullPointerException`、`IndexOutOfBoundsException` 等）

**业务规则违反：**
- 返回数据与业务规则不符（如库存扣减后为负数、订单状态流转异常）
- 接口返回成功但数据不正确（如金额计算错误、状态码不符合预期）

**接口契约违反（服务端侧）：**
- 接口文档定义返回 400 但实际返回 500
- 响应结构与接口文档定义不符（但脚本的请求参数完全正确）

**关键区分点：**
- 500：需要排除 ENV_ERROR（如 Nginx 返回的 502 不是 BUG）。如果业务代码抛异常导致 500，是 BUG
- 数据错误：如果是脚本传了错误参数导致服务端返回异常，归为 SCRIPT_ERROR；如果脚本参数完全正确但服务端返回错误数据，归为 BUG

### 输出标记

```json
{
  "failure_type": "BUG",
  "bug_id": "BUG_{date}_{seq}",
  "suggestion": "生成Bug报告，建议提交给开发团队"
}
```

---

## SCRIPT_ERROR（脚本问题）

### 判定信号

**断言类：**
- `AssertionError` / `AssertionError`（断言条件不满足）
- 断言字段值不匹配（非业务逻辑错误）

**响应解析类：**
- `KeyError`（访问响应 JSON 中不存在的字段）
- `TypeError`（响应类型不匹配，如期望 dict 但得到 list）
- `IndexError`（访问列表越界）

**参数构造类：**
- `TypeError`（参数类型错误）
- `ValueError`（参数值不合法）
- `JSONDecodeError`（请求体序列化失败）

**接口路径类：**
- HTTP 404（服务健康检查通过，但该路径不存在——路径写错或接口已迁移）
- HTTP 405 Method Not Allowed（请求方法与接口定义不匹配）

**数据传递类：**
- 前置步骤返回值未正确传递到后续步骤
- `NoneType` 错误（变量为 None 但未被处理）

### SCRIPT_ERROR 子分类

| 子类型 | 判定特征 | 示例 |
|-------|---------|------|
| 接口变更 | 请求404/405 + 服务正常 + api-doc 确认路径已变 | `/api/cart/add` → `/api/v2/cart/items` |
| 断言过严 | 断言时间戳/随机值精确匹配，或非核心字段严格校验 | `assert created_at == "2024-01-01T00:00:00"` |
| 参数构造错误 | TypeError/ValueError 在参数构建代码中触发 | `int(None)` 或缺少必填参数 |
| 异常处理缺失 | KeyError/TypeError 在响应解析代码中触发 | `res['data']['field']` 但 data 不存在 |
| 数据依赖错误 | NoneType 错误 + 变量来自前置步骤返回值 | `token = login_res['token']` 但实际在 `data.token` |
| 时序/异步问题 | 间歇性失败 + 重跑可通过 + 无明显环境异常 | 断言执行时接口数据尚未写入完成 |

### 输出标记

```json
{
  "failure_type": "SCRIPT_ERROR",
  "root_cause": "api_change|over_strict_assertion|param_error|missing_exception_handling|data_dependency|timing_issue",
  "fixable": true
}
```

---

## 边界情况处理

### 多重错误叠加
如果同一用例同时出现多种错误信号，按优先级取最高级别：
- 连接超时 + KeyError → ENV_ERROR（环境问题优先）
- 401 Token过期 + 断言失败 → DATA_ERROR（认证问题优先，Token有效才能验证断言）

### 无法明确分类
如果错误信号不足以判定，默认归为 SCRIPT_ERROR，在报告中标注为"待人工确认"。

### 批量失败模式
如果大量用例出现相同模式的失败（如同一个接口全部404），合并为一个问题条目，不重复报告。
