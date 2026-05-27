# 标准化输出 Schema 定义

本文档定义了 `api_definitions.yaml/json` 的完整输出结构和校验规则。

---

## 1. 顶层结构

```yaml
api_definitions:
  meta: Meta          # 元信息
  apis: [Api]         # 接口列表
  global_rules: Rules # 全局规则
```

---

## 2. Meta 元信息

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| version | string | 是 | Schema 版本号，当前为 "1.0.0" |
| generated_at | string(datetime) | 是 | 生成时间，ISO 8601 格式 |
| source_type | string | 是 | 输入源类型：swagger/openapi/postman/har/yapi/apifox/text/mixed |
| source_file | string | 是 | 原始文件名 |
| total_apis | integer | 是 | 接口总数 |
| modules | [ModuleSummary] | 是 | 模块统计列表 |

**ModuleSummary**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 模块名称 |
| api_count | integer | 是 | 模块下接口数量 |

---

## 3. Api 接口定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| api_id | string | 是 | 接口唯一标识，格式：`{METHOD}_{path}` |
| name | string | 是 | 接口名称 |
| path | string | 是 | 接口路径 |
| method | string | 是 | HTTP 方法，大写 |
| module | string | 否 | 模块归属，默认 "未分类" |
| description | string | 否 | 接口描述 |
| deprecated | boolean | 否 | 是否已废弃，默认 false |
| tags | [string] | 否 | 标签列表 |
| parameters | Parameters | 是 | 参数定义 |
| responses | Responses | 是 | 响应定义 |
| business_rules | [BusinessRule] | 否 | 关联的业务规则 |

---

## 4. Parameters 参数定义

```yaml
parameters:
  path_params: [Param]
  query_params: [Param]
  header_params: [Param]
  body_params: [Param]
```

### 4.1 Param 参数字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 参数名称 |
| in | string | 是 | 参数位置：path/query/header/body |
| required | boolean | 是 | 是否必填 |
| type | string | 是 | 数据类型：string/integer/number/boolean/array/object/file |
| format | string | 否 | 格式约束：date-time/email/uri/uuid/int64/int32/float/double/binary/password |
| description | string | 否 | 参数描述 |
| default | any | 否 | 默认值 |
| enum | [any] | 否 | 枚举值列表 |
| minLength | integer | 否 | 字符串最小长度 |
| maxLength | integer | 否 | 字符串最大长度 |
| minimum | number | 否 | 数值最小值 |
| maximum | number | 否 | 数值最大值 |
| pattern | string | 否 | 正则约束 |
| example | any | 否 | 示例值 |
| ref | string | 否 | 原始引用路径（仅展开前存在时记录） |
| items | Param | 否 | 数组元素类型定义（type=array 时） |
| properties | [Param] | 否 | 对象属性列表（type=object 时） |
| minItems | integer | 否 | 数组最小元素数 |
| maxItems | integer | 否 | 数组最大元素数 |
| uniqueItems | boolean | 否 | 数组元素是否唯一 |
| additionalProperties | boolean/Param | 否 | object 的额外属性定义 |

### 4.2 嵌套结构表示

object 类型的嵌套通过 `properties` 递归表示：

```yaml
- name: "address"
  in: "body"
  required: false
  type: "object"
  description: "地址信息"
  properties:
    - name: "city"
      type: "string"
      required: true
      description: "城市"
    - name: "street"
      type: "string"
      required: false
      description: "街道"
```

array 类型的嵌套通过 `items` 表示：

```yaml
- name: "tags"
  in: "body"
  required: false
  type: "array"
  items:
    type: "string"
  description: "标签列表"
```

---

## 5. Responses 响应定义

```yaml
responses:
  success: Response
  errors: [ErrorResponse]
```

### 5.1 Response 成功响应

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status_code | integer | 是 | HTTP 状态码 |
| description | string | 是 | 响应描述 |
| content_type | string | 否 | 响应内容类型 |
| schema | [ResponseField] | 否 | 响应体字段列表 |
| example | any | 否 | 响应示例 |

### 5.2 ErrorResponse 异常响应

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status_code | integer | 是 | HTTP 状态码 |
| description | string | 是 | 错误描述 |
| error_code | string | 否 | 业务错误码 |
| schema | [ResponseField] | 否 | 错误响应体字段列表 |
| example | any | 否 | 错误响应示例 |

### 5.3 ResponseField 响应字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| field_path | string | 是 | 字段路径（如 `data.user.name`），数组用 `[]` 标记 |
| type | string | 是 | 数据类型 |
| description | string | 否 | 字段描述 |
| required | boolean | 否 | 是否必填 |
| enum | [any] | 否 | 枚举值 |
| example | any | 否 | 示例值 |
| nested_fields | [ResponseField] | 否 | 嵌套子字段（object 类型） |

---

## 6. BusinessRule 业务规则

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| rule_id | string | 是 | 规则唯一标识，格式：`BR-{NNN}` |
| category | string | 是 | 规则类别：rate_limiting/encryption/authentication/dependency/consistency/idempotency/data_masking/concurrency/other |
| description | string | 是 | 规则描述 |
| affected_apis | [string] | 是 | 受影响的接口 api_id 列表 |
| source | string | 是 | 规则来源：swagger_description/openapi_extension/postman_description/text_inference/yapi_desc/apifox_extension/manual |
| confidence | string | 是 | 置信度：high（明确声明）/ medium（强推断）/ low（弱推断） |

---

## 7. GlobalRules 全局规则

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| authentication | AuthRule | 否 | 全局鉴权规则 |
| rate_limiting | RateLimitRule | 否 | 全局限流规则 |
| error_code_pattern | ErrorCodePattern | 否 | 统一错误响应格式 |
| custom_rules | [CustomRule] | 否 | 其他自定义全局规则 |

### 7.1 AuthRule 鉴权规则

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 是 | 鉴权类型：Bearer/APIKey/OAuth2/Basic/Custom |
| header | string | 否 | 鉴权 Header 名称 |
| query | string | 否 | 鉴权 Query 参数名 |
| description | string | 否 | 鉴权说明 |

### 7.2 RateLimitRule 限流规则

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| default | string | 是 | 默认限流策略描述 |
| description | string | 否 | 限流说明 |

### 7.3 ErrorCodePattern 错误码模式

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| description | string | 是 | 格式说明 |
| schema | object | 否 | 格式定义（字段名 → 类型描述） |

### 7.4 CustomRule 自定义规则

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 规则名称 |
| description | string | 是 | 规则描述 |
| value | any | 否 | 规则值 |

---

## 8. 校验规则

### 8.1 必填校验

以下字段如果缺失，解析过程必须报错（而非静默跳过）：

- `meta.version`
- `meta.generated_at`
- `meta.source_type`
- `meta.total_apis`
- 每个 Api 的 `api_id`、`name`、`path`、`method`
- 每个 Param 的 `name`、`in`、`required`、`type`

### 8.2 格式校验

| 规则 | 说明 |
|------|------|
| api_id 格式 | 必须为 `{METHOD}_{path}` 格式 |
| method 枚举 | 必须为 GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS 之一 |
| type 枚举 | 必须为 string/integer/number/boolean/array/object/file 之一 |
| in 枚举 | 必须为 path/query/header/body 之一 |
| category 枚举 | 必须为 rate_limiting/encryption/authentication/dependency/consistency/idempotency/data_masking/concurrency/other 之一 |
| confidence 枚举 | 必须为 high/medium/low 之一 |

### 8.3 一致性校验

| 规则 | 说明 |
|------|------|
| total_apis 一致 | `meta.total_apis` 必须等于 `apis` 数组长度 |
| module 一致 | 同一路径前缀的接口应归入相同 module |
| path_params 匹配 | `path_params` 中的参数名必须在 `path` 中以 `{name}` 形式出现 |
| required_path | `path` 类型的参数 `required` 必须为 true |

---

## 9. 分片输出规则

当接口数量超过 100 个时，按模块分片输出：

- 每个文件不超过 100 个接口
- 文件命名：`api_definitions_{module_name}.json` 或 `api_definitions_{module_name}.yaml`
- 每个分片文件都有完整的 `meta` 信息
- 额外生成一个 `api_definitions_index.json`，包含所有分片的索引信息

### 9.1 Index 文件结构

```yaml
index:
  version: "1.0.0"
  generated_at: "2026-05-26T10:00:00+08:00"
  source_type: "swagger"
  total_apis: 250
  shards:
    - file: "api_definitions_用户模块.json"
      module: "用户模块"
      api_count: 80
    - file: "api_definitions_商品模块.json"
      module: "商品模块"
      api_count: 100
    - file: "api_definitions_订单模块.json"
      module: "订单模块"
      api_count: 70
  global_rules_file: "api_definitions_global_rules.json"
```
