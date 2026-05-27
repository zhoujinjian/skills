---
name: api-schema-parser
description: 接口定义解析器技能。专门负责处理并解析来自不同来源、不同格式的接口定义数据（Swagger/OpenAPI、Postman集合、HAR抓包、YApi/Apifox导出文档、纯文本描述），统一转换成结构一致、格式标准、可被后续环节直接复用的结构化接口数据。自动识别输入源类型，提取接口核心信息、解析参数与响应、识别隐性业务规则，输出标准化 api_definitions.yaml/json。
---

# API Schema Parser - 接口定义解析器

## 概述

本技能扮演接口架构分析专家角色，核心能力是将来自不同来源、不同格式的接口定义数据，统一转换成结构一致、格式标准、可被后续所有环节直接复用的结构化接口数据。无论输入是 Swagger/OpenAPI 规范文件、Postman 集合导出、HAR 抓包文件、YApi/Apifox 导出文档，还是纯文本描述，都能通过本技能完成标准化清洗与结构化输出，为后续脚本生成、数据构造、场景分析提供统一、可靠的输入基础。

**核心流程：**
```
输入（Swagger/Postman/HAR/YApi/纯文本/混合）
        ↓
  Step 1: 自动识别输入源类型
        ↓
  Step 2: 匹配对应解析规则，提取接口核心信息
        ↓
  Step 3: 解析参数（Path/Query/Header/Body）
        ↓
  Step 4: 解析响应（成功/异常响应体）
        ↓
  Step 5: 识别隐性业务规则
        ↓
  Step 6: 输出标准化 api_definitions.yaml/json
```

## 触发条件

以下场景自动触发本技能：

- 用户提供 Swagger/OpenAPI JSON/YAML 文件，要求解析接口定义
- 用户提供 Postman 集合导出文件（.json/.postman_collection.json）
- 用户提供 HAR 抓包文件（.har）
- 用户提供 YApi/Apifox 导出的接口文档
- 用户提供纯文本格式的接口描述
- 用户要求"解析接口""标准化接口定义""提取接口信息""接口文档转结构化数据"
- 用户提及"api-schema-parser""/api_schema_parser"
- 用户需要为后续测试脚本生成、数据构造、场景分析准备统一的接口数据输入

## 输入识别

接收以下输入，按优先级处理：

1. **接口定义文件**（必需）：支持以下格式
   - **Swagger 2.0** / **OpenAPI 3.x** JSON/YAML 文件
   - **Postman 集合** v2.0/v2.1 导出文件
   - **HAR** (HTTP Archive) 抓包文件
   - **YApi** 导出 JSON 文件
   - **Apifox** 导出 JSON/YAML 文件
   - **纯文本**：自然语言描述的接口信息

2. **业务规则补充说明**（选填）：用户额外提供的业务规则、鉴权方式、限流策略等补充信息

3. **模块归属映射**（选填）：用户提供的模块划分规则，用于对接口进行模块归类

如果用户未提供业务规则补充说明和模块归属映射，对应字段标记为"待补充"，但不影响核心解析流程。

## 执行流程

### Step 1: 自动识别输入源类型

根据文件扩展名、内容结构和关键字段，自动判断输入源类型：

| 输入源 | 识别规则 |
|--------|---------|
| Swagger 2.0 | 文件含 `"swagger": "2.0"` 顶层字段，或有 `swagger` 关键字 |
| OpenAPI 3.x | 文件含 `"openapi": "3.x.x"` 顶层字段 |
| Postman 集合 | 文件含 `"info"` + `"item"` 顶层字段，或 `_postman_id` 字段 |
| HAR 文件 | 文件含 `"log"` 顶层字段，且 `log.entries` 存在 |
| YApi 导出 | 文件为 JSON 数组，元素含 `path`、`method`、`title` 等字段 |
| Apifox 导出 | 文件含 Apifox 特有的 `api` 或 `apiDetail` 结构 |
| 纯文本 | 非 JSON/YAML 格式，或无法匹配上述任何结构 |

**混合输入**：当用户同时提供多个文件时，逐个识别类型并分别解析，最终合并输出。

### Step 2: 提取接口核心信息

参照 `references/parsing-rules.md` 中对应输入源的解析规则，提取每个接口的核心信息：

| 字段 | 说明 | 必填 |
|------|------|------|
| api_id | 接口唯一标识，格式：`{method}_{path}`（如 `GET_/api/v1/users`） | 是 |
| name | 接口名称 | 是 |
| path | 接口路径（如 `/api/v1/users/{id}`） | 是 |
| method | HTTP 请求方法（GET/POST/PUT/DELETE/PATCH 等） | 是 |
| module | 模块归属（基于路径前缀或 tags 推断） | 否 |
| description | 接口描述 | 否 |
| deprecated | 是否已废弃 | 否 |
| tags | 标签列表（来自 Swagger tags 或推断） | 否 |

**模块归属推断规则**：
1. 优先使用 Swagger/OpenAPI 的 `tags` 字段
2. 基于路径前缀推断（如 `/api/v1/users/*` → 用户模块）
3. 基于用户提供的模块归属映射
4. 无法推断时标记为 `"未分类"`

### Step 3: 解析参数

对每个接口，解析所有参数并按位置分类：

#### 3.1 参数分类

| 参数位置 | 说明 | 典型场景 |
|---------|------|---------|
| Path | 路径参数，如 `/users/{id}` 中的 `id` | 资源标识、ID |
| Query | 查询参数，如 `?page=1&size=10` | 分页、过滤、排序 |
| Header | 请求头参数 | 鉴权 Token、Content-Type、自定义头 |
| Body | 请求体参数 | JSON 表单、文件上传 |

#### 3.2 参数字段定义

每个参数必须解析以下字段：

| 字段 | 说明 | 必填 |
|------|------|------|
| name | 参数名称 | 是 |
| in | 参数位置（path/query/header/body） | 是 |
| required | 是否必填 | 是 |
| type | 数据类型（string/integer/number/boolean/array/object/file） | 是 |
| format | 格式约束（date-time/email/uri/uuid/int64 等） | 否 |
| description | 参数描述 | 否 |
| default | 默认值 | 否 |
| enum | 枚举值列表 | 否 |
| minLength / maxLength | 字符串长度约束 | 否 |
| minimum / maximum | 数值范围约束 | 否 |
| pattern | 正则约束 | 否 |
| example | 示例值 | 否 |
| ref | 引用定义（如 `$ref` 引用的 Schema） | 否 |

#### 3.3 Body 参数深度解析

对于 Body 参数，需递归解析嵌套结构：

- **object 类型**：递归解析所有属性字段
- **array 类型**：解析 items 定义
- **`$ref` 引用**：追踪引用，展开为完整定义
- **allOf/anyOf/oneOf**：合并或标记为组合类型
- **文件上传**：识别 `multipart/form-data` 和 `binary` 类型

#### 3.4 参数解析规则（按输入源）

参照 `references/parsing-rules.md` 中各输入源的具体参数映射规则：

- **Swagger 2.0**：`parameters` 数组，`in` 字段标识位置，`schema` 引用 Body
- **OpenAPI 3.x**：`parameters` 数组 + `requestBody` 对象，使用 `content` + `schema` 结构
- **Postman**：从 `item[].request.url.query`、`header`、`body` 解析
- **HAR**：从 `request.url`、`request.headers`、`request.postData` 解析
- **YApi**：从 `req_query`、`req_headers`、`req_body_type` + `req_body_other` 解析
- **纯文本**：基于语义识别参数位置和类型

### Step 4: 解析响应

对每个接口，解析成功和异常响应：

#### 4.1 响应字段定义

| 字段 | 说明 | 必填 |
|------|------|------|
| status_code | HTTP 状态码（如 200、400、401、500） | 是 |
| description | 响应描述 | 是 |
| content_type | 响应内容类型（application/json 等） | 否 |
| schema | 响应体结构定义 | 否 |
| example | 响应示例 | 否 |

#### 4.2 响应体结构解析

递归解析响应体的字段结构，每个字段包含：

| 字段 | 说明 | 必填 |
|------|------|------|
| field_path | 字段路径（如 `data.user.name`） | 是 |
| type | 数据类型 | 是 |
| description | 字段描述 | 否 |
| required | 是否必填 | 否 |
| enum | 枚举值 | 否 |
| example | 示例值 | 否 |
| nested_fields | 嵌套子字段列表（object 类型） | 否 |

#### 4.3 业务错误码映射提取

从响应定义和描述中提取业务错误码映射：

```yaml
error_codes:
  - code: "USER_NOT_FOUND"
    http_status: 404
    message: "用户不存在"
    description: "当查询的用户ID不存在时返回"
  - code: "INVALID_PARAMETER"
    http_status: 400
    message: "参数无效"
    description: "请求参数校验失败时返回"
```

**提取来源**：
- Swagger/OpenAPI 的响应描述和示例
- YApi/Apifox 的错误码定义
- 纯文本中的错误码描述
- 如果文档中未明确列出错误码，根据 HTTP 状态码和业务场景推断常见错误码

### Step 5: 识别隐性业务规则

参照 `references/business-rule-patterns.md` 中的识别模式，从文档描述和接口定义中提取隐性业务规则：

| 规则类别 | 识别模式 | 典型场景 |
|---------|---------|---------|
| 限流策略 | 描述中含"限流""频率""QPS""限次"等关键词 | 同一IP每分钟最多100次请求 |
| 加密规则 | 描述中含"加密""签名""MD5""RSA""AES"等 | 请求体需RSA加密，签名算法为HMAC-SHA256 |
| 鉴权方式 | Header 中含 Authorization/Token/X-Auth 等字段 | Bearer Token 鉴权，Token 有效期2小时 |
| 接口依赖 | 描述中含"依赖""前置""先调用"等 | 创建订单前需先获取用户地址列表 |
| 数据一致性 | 描述中含"事务""原子""一致性"等 | 转账操作需保证原子性 |
| 幂等性 | 描述中含"幂等""重复""去重"等 | 支付接口需保证幂等，重复请求不重复扣款 |
| 数据脱敏 | 描述中含"脱敏""掩码""隐藏"等 | 手机号返回 138****5678 格式 |
| 并发控制 | 描述中含"并发""锁""互斥"等 | 库存扣减需加分布式锁 |

每个识别出的规则输出为：

```yaml
business_rules:
  - rule_id: "BR-001"
    category: "rate_limiting"
    description: "同一IP每分钟最多100次请求"
    affected_apis: ["GET_/api/v1/products"]
    source: "swagger_description"
    confidence: "high"
```

### Step 6: 输出标准化文件

#### 6.1 输出格式

根据用户选择输出 YAML 或 JSON 格式，默认输出 JSON。输出文件命名为 `api_definitions.json` 或 `api_definitions.yaml`。

#### 6.2 输出结构

输出结构遵循 `references/output-schema.md` 中定义的完整 Schema，核心结构如下：

```yaml
# api_definitions.yaml 示例结构
meta:
  version: "1.0.0"
  generated_at: "2026-05-26T10:00:00+08:00"
  source_type: "swagger"          # 输入源类型
  source_file: "petstore.yaml"    # 原始文件名
  total_apis: 15                  # 接口总数
  modules:                        # 模块列表
    - name: "用户模块"
      api_count: 5
    - name: "商品模块"
      api_count: 10

apis:
  - api_id: "POST_/api/v1/users"
    name: "创建用户"
    path: "/api/v1/users"
    method: "POST"
    module: "用户模块"
    description: "创建新用户账号"
    deprecated: false
    tags: ["用户", "账号管理"]

    parameters:
      path_params: []
      query_params: []
      header_params:
        - name: "Authorization"
          in: "header"
          required: true
          type: "string"
          description: "Bearer Token"
      body_params:
        - name: "username"
          in: "body"
          required: true
          type: "string"
          minLength: 3
          maxLength: 50
          pattern: "^[a-zA-Z0-9_]+$"
          description: "用户名，3-50位字母数字下划线"
          example: "zhang_san"
        - name: "email"
          in: "body"
          required: true
          type: "string"
          format: "email"
          description: "邮箱地址"
          example: "zhangsan@example.com"
        - name: "age"
          in: "body"
          required: false
          type: "integer"
          minimum: 1
          maximum: 150
          default: 18
          description: "年龄"

    responses:
      success:
        status_code: 200
        description: "创建成功"
        schema:
          - field_path: "code"
            type: "integer"
            description: "业务状态码"
            example: 0
          - field_path: "data.id"
            type: "string"
            format: "uuid"
            description: "用户ID"
          - field_path: "data.username"
            type: "string"
            description: "用户名"
      errors:
        - status_code: 400
          description: "参数校验失败"
          error_code: "INVALID_PARAMETER"
          schema:
            - field_path: "code"
              type: "integer"
              example: 40001
            - field_path: "message"
              type: "string"
              example: "用户名格式不合法"
        - status_code: 409
          description: "用户名已存在"
          error_code: "USERNAME_EXISTS"

    business_rules:
      - rule_id: "BR-001"
        category: "authentication"
        description: "需要管理员权限才能创建用户"
        affected_apis: ["POST_/api/v1/users"]
        source: "description_inference"
        confidence: "medium"

global_rules:
  authentication:
    type: "Bearer Token"
    header: "Authorization"
    description: "所有接口需在Header中携带Bearer Token"
  rate_limiting:
    default: "100次/分钟/IP"
    description: "默认限流策略"
  error_code_pattern:
    description: "统一错误响应格式"
    schema:
      code: "integer - 业务错误码"
      message: "string - 错误描述"
      data: "object | null - 错误详情"
```

#### 6.3 生成脚本调用

1. 将解析结果整理为结构化 JSON 数据
2. 写入临时文件
3. 执行 `scripts/schema_parser.py` 生成标准化输出文件：

```bash
# JSON 输出
python3 <skill_path>/scripts/schema_parser.py <input_file> --format json --output api_definitions.json

# YAML 输出
python3 <skill_path>/scripts/schema_parser.py <input_file> --format yaml --output api_definitions.yaml

# 指定输入类型（跳过自动识别）
python3 <skill_path>/scripts/schema_parser.py <input_file> --type swagger --format json --output api_definitions.json

# 混合输入合并输出
python3 <skill_path>/scripts/schema_parser.py <file1> <file2> --format json --output api_definitions.json
```

4. 将生成的文件交付给用户

## 纯文本解析策略

当输入为纯文本描述时，按以下策略解析：

### 识别接口信息

从文本中提取接口信息的关键模式：

| 信息 | 识别模式 | 示例 |
|------|---------|------|
| 请求方法 | 大写的 HTTP 方法名 | `GET`、`POST`、`PUT`、`DELETE` |
| 路径 | 以 `/` 开头的 URL 路径 | `/api/v1/users/{id}` |
| 接口名称 | 方法+路径前的描述文字 | "创建用户 POST /api/v1/users" |
| 参数 | 请求参数段落中的表格或列表 | "参数：username（必填，string，3-50位）" |
| 响应 | 响应段落中的状态码和结构 | "成功返回 200 {code: 0, data: {...}}" |

### 参数推断规则

当纯文本中参数信息不完整时，按以下规则推断：

1. **必填性**：未标注时，Path 参数默认必填，其他默认选填
2. **数据类型**：根据示例值推断（数字→integer/number，布尔→boolean，数组→array）
3. **约束条件**：根据描述中的关键词推断（"最大50字符"→maxLength:50，"正整数"→minimum:1）
4. **参数位置**：根据上下文推断（URL 中 `{xxx}`→path，`?xxx=`→query，JSON 体→body）

## 注意事项

- **不遗漏接口**：输入文件中的所有接口必须全部解析输出，不可跳过
- **$ref 完整展开**：Swagger/OpenAPI 中的 `$ref` 引用必须递归展开为完整定义，不在输出中保留引用
- **类型标准化**：不同输入源的类型定义统一映射为标准类型（string/integer/number/boolean/array/object/file）
- **模块归属一致**：相同路径前缀的接口应归入同一模块
- **隐性规则标注置信度**：从文档描述中推断的业务规则必须标注 confidence（high/medium/low），不可与明确声明的规则等同
- **错误码去重**：相同 HTTP 状态码 + 相同业务含义的错误码合并为一条
- **保留原始信息**：输出中的 description 字段尽量保留原始文档的描述文本
- **编码处理**：正确处理中文编码，确保输出文件 UTF-8 编码
- **大文件分片**：当接口数量超过 100 个时，输出文件按模块分片，每个文件不超过 100 个接口

## 与其他技能的协作

本技能是上游数据准备技能，为下游测试技能提供统一的接口数据输入：

```
api-schema-parser ──→ 标准化接口数据 (api_definitions.json/yaml)
        │
        ├──→ generator-testcase-xmind ──→ 基于接口生成 XMind 测试点
        │
        ├──→ generator-testcase-excel ──→ 基于接口生成 Excel 测试用例
        │
        ├──→ safe-testcase ──→ 基于接口参数约束补全边界/异常用例
        │
        └──→ review-testcase ──→ 基于接口定义评审用例覆盖度
```

**建议使用流程**：
1. 先使用本技能将接口文档标准化为 `api_definitions.json`
2. 将标准化数据作为输入，使用 generator-testcase-xmind/excel 生成接口级测试用例
3. 使用 safe-testcase 补全基于参数约束的边界和异常场景
4. 使用 review-testcase 评审接口用例的参数覆盖度和业务规则覆盖度

## Resources

### scripts/schema_parser.py
Python脚本，核心解析引擎，支持：
- 自动识别输入源类型（Swagger/OpenAPI/Postman/HAR/YApi/Apifox/纯文本）
- 按 `references/parsing-rules.md` 中的规则逐源解析
- 输出符合 `references/output-schema.md` 的标准化数据
- 支持混合输入合并输出
- 支持大文件按模块分片输出
- `parse_file(file_path, source_type=None)` — 主解析函数
- `detect_source_type(file_path)` — 自动识别输入源类型
- `merge_definitions(definitions_list)` — 合并多个解析结果
- `export_to_json(definition, output_path)` — 导出为 JSON
- `export_to_yaml(definition, output_path)` — 导出为 YAML
- CLI 用法：`python3 schema_parser.py <input> [--format json|yaml] [--output <path>] [--type <swagger|openapi|postman|har|yapi|apifox|text>]`

### references/parsing-rules.md
各输入源的详细解析规则，包含：
- Swagger 2.0 字段到标准输出的映射表
- OpenAPI 3.x 字段到标准输出的映射表
- Postman 集合结构到标准输出的映射表
- HAR 文件结构到标准输出的映射表
- YApi 导出结构到标准输出的映射表
- Apifox 导出结构到标准输出的映射表
- 纯文本解析的语义识别规则和推断规则
- 类型映射表（各源类型 → 标准类型）
- $ref 引用展开策略

### references/output-schema.md
标准化输出的完整 Schema 定义，包含：
- `meta` 元信息结构
- `apis` 接口定义结构
- `global_rules` 全局规则结构
- 各字段的类型、必填性、约束条件
- JSON Schema 和 YAML Schema 双格式定义
- 输出校验规则

### references/business-rule-patterns.md
隐性业务规则识别模式库，包含：
- 各规则类别（限流/加密/鉴权/依赖/一致性/幂等/脱敏/并发）的关键词模式
- 各规则类别的推断规则和置信度评估
- 常见业务规则模板
- 规则与接口的关联推断策略
