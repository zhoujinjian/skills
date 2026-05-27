# 各输入源解析规则

本文档定义了每种输入源到标准化输出的详细字段映射规则。

---

## 1. Swagger 2.0 解析规则

### 1.1 顶层结构识别

```json
{
  "swagger": "2.0",
  "info": { "title": "...", "version": "..." },
  "basePath": "/api/v1",
  "paths": { ... },
  "definitions": { ... }
}
```

### 1.2 接口核心信息映射

| 标准输出字段 | Swagger 源字段 | 转换规则 |
|-------------|---------------|---------|
| api_id | `method` + `basePath` + `path` | 拼接为 `{METHOD}_{basePath}{path}`，basePath 为空时跳过 |
| name | `operationId` 或 `summary` | 优先 operationId，其次 summary |
| path | `path` key | 原始路径，保留路径参数 `{id}` |
| method | HTTP method key | 大写：GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS |
| module | `tags[0]` | 取第一个 tag，多个 tag 时取主 tag |
| description | `description` | 原始描述文本 |
| deprecated | `deprecated` | 默认 false |
| tags | `tags` | 原始 tags 列表 |

### 1.3 参数映射

Swagger 2.0 的参数定义在 `parameters` 数组中：

| 标准参数字段 | Swagger 源字段 | 转换规则 |
|-------------|---------------|---------|
| name | `parameters[].name` | 直接映射 |
| in | `parameters[].in` | 直接映射（query/path/header/body/formData） |
| required | `parameters[].required` | path 参数强制为 true |
| type | `parameters[].type` | 参见类型映射表 |
| format | `parameters[].format` | 直接映射 |
| description | `parameters[].description` | 直接映射 |
| default | `parameters[].default` | 直接映射 |
| enum | `parameters[].enum` | 直接映射 |
| minLength | `parameters[].minLength` 或 `schema.minLength` | 直接映射 |
| maxLength | `parameters[].maxLength` 或 `schema.maxLength` | 直接映射 |
| minimum | `parameters[].minimum` 或 `schema.minimum` | 直接映射 |
| maximum | `parameters[].maximum` 或 `schema.maximum` | 直接映射 |
| pattern | `parameters[].pattern` 或 `schema.pattern` | 直接映射 |
| example | `parameters[].example` 或 `x-example` | 直接映射 |

**Body 参数处理**：
- `in: "body"` + `schema`：schema 引用需展开
- `in: "formData"`：每个 formData 参数独立解析为 body 字段
- `$ref` 引用：从 `definitions` 中查找并递归展开

### 1.4 响应映射

| 标准响应字段 | Swagger 源字段 | 转换规则 |
|-------------|---------------|---------|
| status_code | responses 的 key | "default" 映射为 0 |
| description | `responses[key].description` | 直接映射 |
| schema | `responses[key].schema` | 递归展开 $ref |
| example | `responses[key].examples` | 取 application/json 的示例 |

**响应体字段展开**：
- 递归遍历 schema 的 properties
- field_path 按层级拼接（如 `data.items[].id`）
- 数组类型标记 `[]`

---

## 2. OpenAPI 3.x 解析规则

### 2.1 顶层结构识别

```json
{
  "openapi": "3.0.0",
  "info": { "title": "...", "version": "..." },
  "paths": { ... },
  "components": { "schemas": { ... }, "securitySchemes": { ... } }
}
```

### 2.2 接口核心信息映射

| 标准输出字段 | OpenAPI 源字段 | 转换规则 |
|-------------|---------------|---------|
| api_id | `method` + `path` | 拼接为 `{METHOD}_{path}` |
| name | `operationId` 或 `summary` | 优先 operationId |
| path | `path` key | 直接映射 |
| method | HTTP method key | 大写 |
| module | `tags[0]` | 同 Swagger 2.0 |
| description | `description` | 直接映射 |
| deprecated | `deprecated` | 默认 false |
| tags | `tags` | 直接映射 |

### 2.3 参数映射

OpenAPI 3.x 区分 `parameters` 和 `requestBody`：

**parameters 数组**（Path/Query/Header）：
- 映射规则与 Swagger 2.0 相同
- `schema` 对象内含 type/format/约束等

**requestBody 对象**：
| 标准参数字段 | OpenAPI 源字段 | 转换规则 |
|-------------|---------------|---------|
| name | schema 的 property name | 遍历 properties |
| in | 固定 "body" | - |
| required | `requestBody.required` 或 `property required` | 优先属性级 required |
| type | `schema.type` | 参见类型映射表 |
| ... | 其余约束字段 | 同 Swagger 2.0 |

**content 类型处理**：
- `application/json`：解析 schema
- `multipart/form-data`：解析 schema，标记文件上传字段
- `application/x-www-form-urlencoded`：解析 schema
- 多种 content-type 时，优先解析 application/json

**components/schemas 引用**：
- `#/components/schemas/Xxx` → 从 components.schemas 查找展开
- 递归展开所有嵌套引用
- 处理 allOf/anyOf/oneOf 合并逻辑

### 2.4 响应映射

| 标准响应字段 | OpenAPI 源字段 | 转换规则 |
|-------------|---------------|---------|
| status_code | `responses` 的 key | "default" → 0，范围码（2XX）→ 列出所有 |
| description | `responses[key].description` | 直接映射 |
| schema | `responses[key].content[media].schema` | 递归展开 |
| example | `responses[key].content[media].example` | 直接映射 |

---

## 3. Postman 集合解析规则

### 3.1 结构识别

```json
{
  "info": { "name": "...", "schema": "https://schema.getpostman.com/..." },
  "item": [
    {
      "name": "文件夹名",
      "item": [ { "request": { ... } } ]
    }
  ]
}
```

### 3.2 接口核心信息映射

| 标准输出字段 | Postman 源字段 | 转换规则 |
|-------------|---------------|---------|
| api_id | `method` + URL path | 解析 `request.url.raw` 提取路径 |
| name | `name` | 直接映射 |
| path | `request.url.path` | 拼接为 `/path1/path2`，还原 `:param` 为 `{param}` |
| method | `request.method` | 大写 |
| module | 父级 `item` 的 `name` | 文件夹名即模块名 |
| description | `request.description` | 直接映射 |

### 3.3 参数映射

| 标准参数字段 | Postman 源字段 | 转换规则 |
|-------------|---------------|---------|
| name | query/header 的 `key` | 直接映射 |
| in | 根据位置推断 | url.query → query, header → header, body → body |
| required | 通常缺失 | 默认 false（除非变量名含 `required`） |
| type | 从 example 推断 | 根据示例值类型推断 |
| default | `value` | 直接映射 |
| example | `value` | 直接映射 |

**Body 解析**：
- `mode: "raw"` + `options.raw.language: "json"`：解析 JSON body
- `mode: "formdata"`：解析为独立字段
- `mode: "urlencoded"`：解析为独立字段
- `mode: "file"`：标记为 file 类型

### 3.4 响应映射

Postman 的 `response[]` 提供实际响应示例：

| 标准响应字段 | Postman 源字段 | 转换规则 |
|-------------|---------------|---------|
| status_code | `response[].code` | 直接映射 |
| description | `response[].status` | 直接映射 |
| schema | 从 `response[].body` 推断 | 解析 JSON 示例推断结构 |
| example | `response[].body` | 直接映射 |

**注意**：Postman 无 Schema 定义，响应结构需从示例推断，置信度标记为 low。

---

## 4. HAR 文件解析规则

### 4.1 结构识别

```json
{
  "log": {
    "entries": [
      {
        "request": { "method": "GET", "url": "...", "headers": [...], "postData": {...} },
        "response": { "status": 200, "content": { "text": "..." } }
      }
    ]
  }
}
```

### 4.2 接口核心信息映射

| 标准输出字段 | HAR 源字段 | 转换规则 |
|-------------|-----------|---------|
| api_id | `method` + 解析后的 path | 从 URL 提取路径部分 |
| name | 自动生成 | 格式：`{method} {path}` |
| path | URL path 部分 | 去除域名和协议，还原参数值 |
| method | `request.method` | 大写 |
| module | 路径前缀推断 | 第一级路径为模块名 |
| description | 自动生成 | "来自 HAR 抓包" |

### 4.3 参数映射

| 标准参数字段 | HAR 源字段 | 转换规则 |
|-------------|-----------|---------|
| name | queryString 的 `name` / header 的 `name` | 直接映射 |
| in | 根据位置 | URL query → query, headers → header, postData → body |
| required | 缺失 | 默认 false |
| type | 从 `value` 推断 | 根据值推断 |
| example | `value` | 直接映射 |

**路径参数还原**：
- 比较多个请求的同一路径模式
- 不同值的位置推断为路径参数（如 `/users/123` 和 `/users/456` → `/users/{id}`）

### 4.4 响应映射

| 标准响应字段 | HAR 源字段 | 转换规则 |
|-------------|-----------|---------|
| status_code | `response.status` | 直接映射 |
| description | `response.statusText` | 直接映射 |
| schema | 从 `response.content.text` 推断 | 解析 JSON 推断结构 |
| example | `response.content.text` | 直接映射 |

**注意**：HAR 为实际请求/响应快照，响应结构需从示例推断，需去重（同一接口多次请求合并）。

---

## 5. YApi 导出解析规则

### 5.1 结构识别

YApi 导出为 JSON 数组，每个元素是一个接口定义：

```json
[
  {
    "path": "/api/users",
    "method": "GET",
    "title": "获取用户列表",
    "req_query": [...],
    "req_headers": [...],
    "req_body_type": "json",
    "req_body_other": "{...}",
    "res_body_type": "json",
    "res_body": "{...}"
  }
]
```

### 5.2 接口核心信息映射

| 标准输出字段 | YApi 源字段 | 转换规则 |
|-------------|------------|---------|
| api_id | `method` + `path` | 拼接 |
| name | `title` | 直接映射 |
| path | `path` | 直接映射 |
| method | `method` | 大写 |
| module | `catid` 或推断 | 基于 catid 或路径推断 |
| description | `desc` 或 `title` | 直接映射 |

### 5.3 参数映射

| 标准参数字段 | YApi 源字段 | 转换规则 |
|-------------|------------|---------|
| name | `req_query[].name` / `req_headers[].name` | 直接映射 |
| in | 根据字段位置 | req_query → query, req_headers → header |
| required | `req_query[].required` | "1" → true, "0" → false |
| type | `req_query[].type` | 映射到标准类型 |
| description | `req_query[].desc` | 直接映射 |
| example | `req_query[].example` | 直接映射 |

**Body 参数**：
- `req_body_type: "json"` + `req_body_other`：解析 JSON Schema
- `req_body_type: "form"`：解析为 form 字段
- `req_body_type: "file"`：标记为文件上传

### 5.4 响应映射

| 标准响应字段 | YApi 源字段 | 转换规则 |
|-------------|------------|---------|
| status_code | 默认 200 | YApi 通常只定义成功响应 |
| description | 自动生成 | "成功响应" |
| schema | `res_body` | 解析 JSON Schema |
| example | 缺失时从 schema 推断 | - |

---

## 6. Apifox 导出解析规则

### 6.1 结构识别

Apifox 导出格式与 OpenAPI 3.x 兼容，额外包含 Apifox 扩展字段（`x-apifox-*`）。

### 6.2 核心映射

基本映射规则同 OpenAPI 3.x，额外处理：

| 标准输出字段 | Apifox 扩展字段 | 转换规则 |
|-------------|----------------|---------|
| name | `x-apifox-name` | 优先于 operationId |
| module | `x-apifox-folder` | 文件夹名即模块 |
| description | `x-apifox-description` | 优先 |

---

## 7. 纯文本解析规则

### 7.1 接口信息识别

从自然语言文本中提取接口信息的模式：

```
模式1: "{方法} {路径}" → GET /api/v1/users
模式2: "{接口名称}\n{方法} {路径}" → 获取用户列表\nGET /api/v1/users
模式3: "接口：{路径}\n方法：{方法}" → 中文标注格式
模式4: Markdown 表格/列表格式
```

### 7.2 参数识别

```
模式1: "参数：{name}（{必填/选填}，{type}，{约束}）"
模式2: 表格格式：| 参数名 | 类型 | 必填 | 说明 |
模式3: JSON 示例体
模式4: "请求体：{JSON}"
```

### 7.3 响应识别

```
模式1: "返回 200 {JSON结构}"
模式2: "成功响应：{JSON}"
模式3: "错误码：{code} - {message}"
模式4: Markdown 代码块中的 JSON 示例
```

### 7.4 类型推断

当纯文本中类型信息不完整时：

| 示例值 | 推断类型 |
|--------|---------|
| `123` | integer |
| `12.5` | number |
| `"hello"` | string |
| `true` / `false` | boolean |
| `[...]` | array |
| `{...}` | object |
| 无示例 + 描述含"日期" | string + format: date |
| 无示例 + 描述含"邮箱" | string + format: email |

---

## 8. 类型映射表

各输入源的类型到标准类型的统一映射：

| Swagger 2.0 | OpenAPI 3.x | Postman/HAR | YApi | 标准输出 |
|-------------|-------------|-------------|------|---------|
| string | string | string | string | string |
| integer | integer | - | integer | integer |
| number | number | - | number | number |
| boolean | boolean | - | boolean | boolean |
| array | array | - | array | array |
| object | object | - | object | object |
| file | string + format: binary | - | file | file |

---

## 9. $ref 引用展开策略

### 9.1 引用路径解析

| 规范 | 引用格式 | 查找位置 |
|------|---------|---------|
| Swagger 2.0 | `#/definitions/Xxx` | `definitions` 对象 |
| OpenAPI 3.x | `#/components/schemas/Xxx` | `components.schemas` |
| OpenAPI 3.x | `#/components/parameters/Xxx` | `components.parameters` |
| OpenAPI 3.x | `#/components/responses/Xxx` | `components.responses` |

### 9.2 展开规则

1. **递归展开**：$ref 指向的对象可能也含 $ref，需递归直到无引用
2. **循环引用检测**：维护已访问引用栈，检测到循环时标记 `circular_ref: true` 并停止
3. **allOf 合并**：将 allOf 中的所有 schema 的 properties 合并
4. **anyOf/oneOf 标记**：标记为组合类型，列出所有可能的结构
5. **展开后不保留 $ref**：输出中不包含原始引用路径

---

## 10. 去重与合并规则

### 10.1 同源去重

同一文件中相同 `{method}_{path}` 的接口定义保留最后一个（后定义覆盖前定义）。

### 10.2 多源合并

混合输入时，相同 `{method}_{path}` 的合并策略：
- **核心信息**：保留信息更完整的版本
- **参数**：取并集，相同参数名以更详细的定义覆盖
- **响应**：取并集，相同状态码以更详细的定义覆盖
- **业务规则**：取并集，去重
