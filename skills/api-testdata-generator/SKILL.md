---
name: api-testdata-generator
description: 测试数据自动化构造技能。支持三种输入模式：传统模式（基于 api_definitions.json 接口定义）、规范模式（基于团队自定义字段规则）、自然语言模式（基于自然语言描述，Faker 驱动）。自动生成覆盖正向、边界、异常、安全四大维度的测试数据，支持 YAML/JSON/Excel/CSV 格式输出。
---

# API Test Data Generator - 测试数据自动化构造

## 概述

本技能扮演测试数据构造专家角色，核心能力是基于不同输入来源自动生成覆盖全场景、符合约束、可直接用于数据驱动测试的测试数据集。

**三种输入模式：**

| 模式 | 输入来源 | 适用场景 | 输出格式 |
|------|---------|---------|---------|
| 传统模式（API） | `api_definitions.json` | 接口测试、数据驱动测试 | YAML/JSON/Excel |
| 规范模式（Spec） | 自定义字段规则文件 | 多类型测试、团队规范驱动 | YAML/JSON/Excel/CSV |
| 自然语言模式（NL） | 自然语言描述 | 手工测试、性能测试、UI 自动化等 | CSV（主）/JSON |

**四大数据维度：**

| 维度 | 说明 | 数据量占比 |
|------|------|-----------|
| 正向合法数据 | 满足所有业务与格式规则的标准数据 | 20% |
| 边界值数据 | 最小/最大长度、数值上下限、临界合法值 | 30% |
| 异常非法数据 | 空值、Null、缺失参数、类型不匹配、格式错误、超长超短 | 35% |
| 安全与幂等数据 | 防重放、重复提交、SQL 注入、XSS 等风险场景 | 15% |

## 触发条件

以下场景自动触发本技能：

- 用户提供 `api_definitions.json` 或 `api_definitions.yaml` 文件，要求生成测试数据 → **传统模式**
- 用户提供自定义字段规则文件（含 `fields:` 定义），要求生成测试数据 → **规范模式**
- 用户用自然语言描述数据需求，如"生成 10 条身份证数据""生成手机号"等 → **自然语言模式**
- 用户要求"生成测试数据""构造测试数据""数据驱动测试数据"
- 用户提及"api-testdata-generator""/api_testdata_generator"
- 用户需要为手工测试、性能测试、UI 自动化等场景准备测试数据

## 模式识别

根据输入自动判定模式，也可通过 `--mode` 参数显式指定：

| 判定条件 | 模式 |
|---------|------|
| 输入为 `api_definitions.json/yaml`（含 `apis` 字段） | 传统模式（api） |
| 输入为自定义规则文件（含 `fields` 字段） | 规范模式（spec） |
| 使用 `--prompt` 参数传入自然语言描述 | 自然语言模式（nl） |
| 使用 `--mode api/spec/nl` | 显式指定模式 |

## 模式一：传统模式（API Schema）

### 核心流程

```
输入（api_definitions.json + 团队数据规范）
        ↓
  Step 1: 解析接口参数约束（类型、必填、长度、正则、枚举、默认值）
        ↓
  Step 2: 按场景维度生成测试数据
        ↓
  Step 3: 处理接口依赖数据（Token、用户ID、订单号等）
        ↓
  Step 4: 输出数据驱动格式文件（YAML/JSON/Excel）
```

### 输入

1. **标准化接口定义文件**（必需）：由 `api-schema-parser` 输出的 `api_definitions.json/yaml`
2. **团队测试数据构造规范**（选填）：JSON/YAML 格式
3. **目标接口/模块筛选**（选填）：接口 api_id 或模块名称

如果用户未提供团队数据规范，使用 `references/boundary-rules.md` 中的默认规则。

### 执行流程

#### Step 1: 解析接口参数约束

| 约束类型 | 来源字段 | 说明 |
|---------|---------|------|
| 数据类型 | `type` | string/integer/number/boolean/array/object/file |
| 必填性 | `required` | true/false |
| 长度约束 | `minLength`/`maxLength` | 字符串长度范围 |
| 数值范围 | `minimum`/`maximum` | 数值上下限 |
| 正则约束 | `pattern` | 格式验证正则 |
| 枚举约束 | `enum` | 限定取值范围 |
| 格式约束 | `format` | date-time/email/uri/uuid/int64 等 |
| 默认值 | `default` | 未传参时的默认值 |
| 数组约束 | `minItems`/`maxItems`/`uniqueItems` | 数组元素约束 |

#### Step 2: 按场景维度生成测试数据

参见下方「四大数据维度详细规则」章节。

#### Step 3: 处理接口依赖数据

参照 `references/dependency-resolution.md` 中的策略，自动处理 Token、用户 ID、订单号等依赖关系，使用 `${VARIABLE_NAME}` 格式标记。

#### Step 4: 输出数据驱动格式文件

按模块分目录输出，每个接口一个文件。支持 YAML/JSON/Excel 三种格式。

### 输出目录结构

```
test_data/
├── _dependencies.yaml          # 依赖关系配置（全局）
├── _config.yaml                # 全局配置（鉴权、基础URL等）
├── auth/                       # 认证管理模块
│   ├── user_login.yaml
│   ├── user_register.yaml
│   └── ...
├── order/
│   └── ...
└── summary.json                # 数据生成汇总报告
```

### 单个接口输出结构

```yaml
api_id: "POST_/api/auth/login"
name: "用户登录"
module: "认证管理"
test_cases:
  - case_id: "POS_001"
    name: "合法用户名和密码登录"
    category: "positive"
    priority: "P0"
    parameters:
      body_params:
        username: "testuser01"
        password: "Test1234"
        captchaKey: "${CAPTCHA_KEY}"
        captchaCode: "1234"
    expected:
      status_code: 200
  - case_id: "BND_001"
    name: "密码最小长度边界-8位密码"
    category: "boundary"
    priority: "P1"
    parameters:
      body_params:
        username: "testuser01"
        password: "Test1234"
    expected:
      status_code: 200
  - case_id: "NEG_001"
    name: "用户名为空"
    category: "negative"
    priority: "P0"
    parameters:
      body_params:
        username: ""
        password: "Test1234"
    expected:
      status_code: 400
  - case_id: "SEC_001"
    name: "SQL注入-用户名"
    category: "security"
    priority: "P1"
    parameters:
      body_params:
        username: "' OR '1'='1"
        password: "Test1234"
    expected:
      status_code: 400
```

---

## 模式二：规范模式（Spec）

### 核心流程

```
输入（自定义字段规则文件 YAML/JSON）
        ↓
  Step 1: 解析字段约束（类型、长度、正则、枚举、范围等）
        ↓
  Step 2: 按场景维度生成测试数据
        ↓
  Step 3: 输出格式文件（YAML/JSON/Excel/CSV）
```

### 输入

自定义字段规则文件，格式为 YAML 或 JSON，包含以下结构：

```yaml
# 示例：用户注册表单测试数据规则
name: "用户注册表单"
description: "用户注册场景的测试数据规则"
count: 10                          # 每个维度默认生成条数
dimensions: [positive, boundary, negative]  # 生成维度，可选

fields:
  - name: username
    type: string
    required: true
    minLength: 3
    maxLength: 20
    pattern: "^[a-zA-Z0-9_]+$"
    description: "用户名"

  - name: password
    type: string
    required: true
    minLength: 8
    maxLength: 50
    pattern: "^(?=.*[A-Za-z])(?=.*\\d).{8,}$"
    description: "密码"

  - name: email
    type: string
    required: true
    format: email
    description: "邮箱"

  - name: phone
    type: string
    required: true
    pattern: "^1[3-9]\\d{9}$"
    description: "手机号"

  - name: age
    type: integer
    required: false
    minimum: 1
    maximum: 150
    description: "年龄"

  - name: gender
    type: integer
    required: false
    enum: [0, 1, 2]
    description: "性别（0未知/1男/2女）"

  - name: address
    type: string
    required: false
    maxLength: 200
    description: "地址"
```

### 字段规则定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 字段名 |
| type | string | 是 | 数据类型：string/integer/number/boolean/array/object |
| required | boolean | 否 | 是否必填，默认 false |
| minLength | integer | 否 | 字符串最小长度 |
| maxLength | integer | 否 | 字符串最大长度 |
| minimum | number | 否 | 数值最小值 |
| maximum | number | 否 | 数值最大值 |
| pattern | string | 否 | 正则约束 |
| enum | list | 否 | 枚举值列表 |
| format | string | 否 | 格式约束：email/uri/uuid/date-time/date/phone |
| default | any | 否 | 默认值 |
| description | string | 否 | 字段描述 |

### 输出

默认 CSV 格式（方便在手工测试、性能测试等场景直接使用），也支持 YAML/JSON/Excel。

```csv
# spec_test_data_positive.csv
username,password,email,phone,age,gender,address
testuser01,Test1234,test01@example.com,13800001234,25,1,北京市朝阳区测试街道1号
testuser02,Test5678,test02@example.com,13800001235,30,2,上海市浦东新区测试路2号
```

---

## 模式三：自然语言模式（NL）

### 核心流程

```
输入（自然语言描述）
        ↓
  Step 1: 解析自然语言，提取字段类型、数量、合法性约束
        ↓
  Step 2: 基于 Faker 库生成符合约束的数据
        ↓
  Step 3: 输出 CSV 文件
```

### 输入

直接使用自然语言描述数据需求，例如：

- "生成 10 条符合中国身份证规则的数据"
- "生成 5 个合法手机号和 2 个非法手机号"
- "生成随机用户名、邮箱、地址、公司名等测试数据"
- "生成 20 条包含姓名、手机号、身份证号、银行卡号的测试数据"
- "生成 3 个合法邮箱和 3 个格式错误的邮箱"
- "生成 100 条性能测试用的用户数据，包含用户名、密码、邮箱"

### 自然语言解析规则

#### 字段类型识别

| 关键词 | 字段类型 | Faker Provider | 说明 |
|--------|---------|---------------|------|
| 身份证/身份证号/ID号 | ssn | `faker.ssn()` | 18 位中国身份证 |
| 手机号/手机/电话/电话号码 | phone | `faker.phone_number()` | 中国手机号 |
| 用户名/账号 | username | `faker.user_name()` | 英文用户名 |
| 姓名/中文姓名/名字 | name | `faker.name()` | 中文姓名 |
| 邮箱/电子邮件/email | email | `faker.email()` | 标准邮箱 |
| 地址/收货地址/住址 | address | `faker.address()` | 中文地址 |
| 公司名/公司/企业 | company | `faker.company()` | 公司名称 |
| 密码 | password | 自定义生成 | 满足常见密码规则 |
| 日期 | date | `faker.date()` | ISO 日期 |
| 日期时间/时间戳 | datetime | `faker.date_time()` | ISO 日期时间 |
| URL/网址/链接 | url | `faker.url()` | HTTP URL |
| IP/IP地址 | ipv4 | `faker.ipv4()` | IPv4 地址 |
| 银行卡/银行卡号/信用卡 | credit_card | `faker.credit_card_number()` | 银行卡号 |
| 城市名/城市 | city | `faker.city()` | 城市名 |
| 省份 | province | `faker.province()` | 省份名 |
| 邮编/邮政编码 | postcode | `faker.postcode()` | 邮政编码 |
| 职业/职位 | job | `faker.job()` | 职业名称 |
| 车牌号/车牌 | license_plate | 自定义生成 | 中国车牌号 |

#### 数量提取

| 模式 | 示例 | 提取结果 |
|------|------|---------|
| 数字+量词 | "10条""5个""20组" | 数量 = 数字 |
| "若干"/"一些" | "生成若干手机号" | 数量 = 5（默认） |
| 无数量词 | "生成手机号" | 数量 = 5（默认） |

#### 合法性识别

| 关键词 | 数据类型 | 说明 |
|--------|---------|------|
| 合法/有效/正确/正常 | 合法数据 | 满足格式规则的数据 |
| 非法/无效/错误/异常 | 非法数据 | 不满足格式规则的数据 |
| 符合...规则 | 合法数据 | 满足特定规则的数据 |
| 边界/临界 | 边界数据 | 极限合法值 |

### 非法数据生成规则

参照 `references/nl-patterns.md` 中的详细规则，为每种字段类型生成对应的非法数据：

| 字段类型 | 非法变体 |
|---------|---------|
| 身份证 | 17位（少校验位）、19位（多1位）、含字母、校验位错误、空字符串 |
| 手机号 | 10位（少1位）、12位（多1位）、含字母、非1开头、含特殊字符 |
| 邮箱 | 缺@、缺域名、缺用户名、连续..、含空格 |
| URL | 缺协议、含空格、非HTTP协议 |
| IP | 超过255段、含字母、缺段 |
| 密码 | 少于8位、纯数字、纯字母、无特殊字符 |

### 输出

默认 CSV 格式，首行为字段名，后续为数据行：

```csv
# nl_test_data_20260526_113000.csv
身份证号
110101199001011234
110101199002022345
440305199103033456
...

# 含多字段的输出
姓名,手机号,邮箱,地址
张伟,13800001234,zhangwei@example.com,北京市朝阳区建国路1号
李娜,13800001235,lina@example.com,上海市浦东新区陆家嘴路2号
...
```

---

## 四大数据维度详细规则

以下规则适用于传统模式和规范模式。自然语言模式的维度由描述中的合法性关键词决定。

### 正向合法数据（Positive）

| 策略 | 说明 | 示例 |
|------|------|------|
| 标准合法值 | 满足所有约束的典型值 | username="zhangsan", age=25 |
| 默认值填充 | 使用 default 字段的值 | page=1, size=20 |
| 枚举遍历 | 对 enum 字段每个值生成一组 | type="dog", type="cat" |
| 可选参数组合 | 必填+部分选填、必填+全部选填 | 2 组不同组合 |

### 边界值数据（Boundary）

参照 `references/boundary-rules.md`：

| 策略 | 说明 | 示例 |
|------|------|------|
| 最小长度边界 | minLength ± 1 | ""、"a"、"ab"（minLength=2） |
| 最大长度边界 | maxLength ± 1 | 49字、50字、51字（maxLength=50） |
| 数值上下限边界 | minimum/maximum ± 1 | 0、1、2（minimum=1） |
| 正则边界 | 临界合法/非法值 | 邮箱缺@、手机号少1位 |
| 枚举边界 | 枚举外的非法值 | enum=["A","B"] → "C" |

**组合策略**：单参数边界，不做笛卡尔积，必填参数优先。

### 异常非法数据（Negative）

| 策略 | 适用类型 |
|------|---------|
| 空值/缺失 | 必填参数 |
| Null 值 | 所有参数 |
| 类型不匹配 | 所有类型参数 |
| 格式错误 | 带 format 的参数 |
| 超长/超大 | string/integer |
| 特殊字符 | string 类型 |

### 安全与幂等数据（Security）

参照 `references/security-patterns.md`：

| 策略 | 注入内容 |
|------|---------|
| SQL 注入 | `' OR '1'='1`、`"; DROP TABLE users;--` |
| XSS 攻击 | `<script>alert('XSS')</script>` |
| 路径穿越 | `../../etc/passwd` |
| 命令注入 | `; ls -la`、`$(whoami)` |
| 重复提交 | 完整合法数据重复 |

---

## 生成脚本调用

### 传统模式

```bash
# 为所有接口生成 YAML 格式测试数据
python3 <skill_path>/scripts/testdata_generator.py api_definitions.json --format yaml --output test_data/

# 为所有接口生成 JSON 格式测试数据
python3 <skill_path>/scripts/testdata_generator.py api_definitions.json --format json --output test_data/

# 为所有接口生成 Excel 格式测试数据
python3 <skill_path>/scripts/testdata_generator.py api_definitions.json --format excel --output test_data/

# 仅生成指定模块的测试数据
python3 <skill_path>/scripts/testdata_generator.py api_definitions.json --module "订单管理" --output test_data/

# 仅生成指定接口的测试数据
python3 <skill_path>/scripts/testdata_generator.py api_definitions.json --api "POST_/api/auth/login" --output test_data/

# 自定义团队数据规范
python3 <skill_path>/scripts/testdata_generator.py api_definitions.json --config custom_rules.yaml --output test_data/

# 仅生成指定维度
python3 <skill_path>/scripts/testdata_generator.py api_definitions.json --dimension positive,boundary --output test_data/
```

### 规范模式

```bash
# 基于自定义规则生成测试数据（默认 CSV 输出）
python3 <skill_path>/scripts/testdata_generator.py --mode spec --spec custom_rules.yaml --output test_data/

# 指定输出格式
python3 <skill_path>/scripts/testdata_generator.py --mode spec --spec custom_rules.yaml --format json --output test_data/

# 指定生成维度
python3 <skill_path>/scripts/testdata_generator.py --mode spec --spec custom_rules.yaml --dimension positive,negative --output test_data/
```

### 自然语言模式

```bash
# 生成符合中国身份证规则的数据
python3 <skill_path>/scripts/testdata_generator.py --mode nl --prompt "生成10条符合中国身份证规则的数据" --output test_data/

# 生成合法和非法手机号
python3 <skill_path>/scripts/testdata_generator.py --mode nl --prompt "生成5个合法手机号和2个非法手机号" --output test_data/

# 生成随机用户数据
python3 <skill_path>/scripts/testdata_generator.py --mode nl --prompt "生成随机用户名、邮箱、地址、公司名等测试数据" --output test_data/

# 指定数量
python3 <skill_path>/scripts/testdata_generator.py --mode nl --prompt "生成20条包含姓名、手机号、身份证号的测试数据" --output test_data/

# 性能测试数据
python3 <skill_path>/scripts/testdata_generator.py --mode nl --prompt "生成100条性能测试用的用户数据，包含用户名、密码、邮箱" --output test_data/
```

---

## 数据生成规则

### 字符串生成策略

| 场景 | 生成值 | 说明 |
|------|--------|------|
| 通用字符串 | `test_{random_4chars}` | 随机4位字母数字 |
| 用户名 | `testuser{NN}` | 序号递增 |
| 密码 | `Test@1234` | 满足常见密码规则 |
| 邮箱 | `test{NN}@example.com` | 标准邮箱格式 |
| 手机号 | `1380000{NNNN}` | 标准手机号格式 |
| URL | `https://example.com/test` | 标准 URL |
| UUID | `550e8400-e29b-41d4-a716-446655440000` | 标准 UUID v4 |
| 日期时间 | `2026-01-15T10:30:00+08:00` | ISO 8601 |
| 中文姓名 | Faker zh_CN | 中文真实姓名 |
| 中文地址 | Faker zh_CN | 中文真实地址 |

### 数值生成策略

| 场景 | 生成值 | 说明 |
|------|--------|------|
| 通用整数 | 中间值 | (minimum + maximum) / 2 |
| 分页参数 | page=1, size=20 | 常见分页默认值 |
| ID 类 | 自增正整数 | 1, 2, 3... |
| 金额 | 99.99 | 两位小数 |

### 布尔值生成策略

| 场景 | 生成值 |
|------|--------|
| 通用布尔 | true / false 各一组 |
| 选中状态 | 1（选中）/ 0（未选中） |

## 注意事项

- **模式自动识别**：当输入文件含 `apis` 字段时自动识别为传统模式，含 `fields` 字段时为规范模式，使用 `--prompt` 时为自然语言模式
- **不遗漏参数**：每个接口的所有参数都必须生成测试数据
- **约束完整覆盖**：每个参数的每个约束都必须生成对应的边界值
- **依赖变量标记**：依赖参数使用 `${VARIABLE}` 格式标记（传统模式）
- **数据可复用**：正向数据中相同参数的合法值在不同接口间保持一致
- **优先级标注**：每条测试数据标注优先级（P0/P1/P2/P3），P0 为最高
- **中文场景适配**：Faker 使用 zh_CN locale，优先生成中文合法数据
- **编码处理**：输出文件 UTF-8 编码，CSV 含 BOM 头（兼容 Excel 打开）
- **大文件分模块**：按模块分目录输出，每个接口一个文件（传统模式）
- **预期结果合理**：正向数据期望 200，异常数据期望 4xx
- **安全数据可控**：SQL 注入、XSS 等安全测试数据仅用于测试目的
- **Faker 可选依赖**：自然语言模式依赖 Faker 库，未安装时给出安装提示并回退到内置生成器

## 与其他技能的协作

```
api-schema-parser ──→ 标准化接口数据 (api_definitions.json)
        │
        ├──→ api-testdata-generator ──→ 测试数据文件
        │       │
        │       ├── [传统模式] → test_data/*.yaml → generator-testcase-xmind/excel
        │       │
        │       ├── [规范模式] → spec_test_data.csv  → 手工测试/性能测试/UI自动化
        │       │
        │       ├── [自然语言模式] → nl_test_data.csv → 手工测试/性能测试/UI自动化
        │       │
        │       ├──→ safe-testcase ──→ 基于数据补全遗漏场景
        │       │
        │       └──→ review-testcase ──→ 基于数据评审用例覆盖度
        │
        └──→ （也可直接进入测试执行）
```

**建议使用流程**：
1. 接口测试场景：先 `api-schema-parser` → 本技能（传统模式）→ `generator-testcase-xmind/excel`
2. 手工/性能/UI 测试场景：直接使用本技能（自然语言模式）生成 CSV 数据
3. 团队规范驱动：使用本技能（规范模式）基于字段规则文件生成数据

## Resources

### scripts/testdata_generator.py
Python 脚本，核心数据构造引擎，支持：
- **三种输入模式**：传统模式（api_definitions.json）、规范模式（字段规则文件）、自然语言模式（Faker 驱动）
- **四大数据维度**：正向/边界/异常/安全
- **多种输出格式**：YAML/JSON/Excel/CSV
- **智能依赖处理**：自动识别接口间依赖关系（传统模式）
- **Faker 集成**：基于成熟数据构造库生成中文场景数据（自然语言模式）
- **自然语言解析**：从用户描述中提取字段类型、数量、合法性约束
- CLI 用法：
  - 传统：`python3 testdata_generator.py <api_definitions.json> [--format yaml|json|excel] [--output <dir>] [--module <name>] [--api <api_id>] [--config <rules.yaml>] [--dimension ...]`
  - 规范：`python3 testdata_generator.py --mode spec --spec <rules.yaml> [--format csv|yaml|json|excel] [--output <dir>] [--dimension ...]`
  - 自然语言：`python3 testdata_generator.py --mode nl --prompt "生成10条手机号" [--output <dir>]`

### references/boundary-rules.md
边界值测试数据生成规则，包含各类型的边界值定义、偏移规则、组合策略。

### references/security-patterns.md
安全测试数据模式库，包含 SQL 注入、XSS、路径穿越、命令注入等模式。

### references/dependency-resolution.md
接口依赖处理策略，包含依赖类型识别、链路分析、变量标记格式。

### references/nl-patterns.md
自然语言模式参考文档，包含字段类型关键词映射、Faker Provider 配置、合法/非法数据生成规则、中文场景特殊处理。
