# 接口依赖处理策略

本文档定义了接口间数据依赖的自动识别与处理策略，用于 `testdata_generator.py` 的依赖链分析和依赖变量标记。

---

## 1. 依赖类型识别

### 1.1 鉴权依赖

| 识别规则 | 依赖变量 | 来源接口 |
|---------|---------|---------|
| Header 含 `Authorization` | `${TOKEN}` | 登录接口 |
| 全局鉴权规则中声明 Bearer Token | `${TOKEN}` | 登录接口 |
| 接口描述中含"需登录""需鉴权" | `${TOKEN}` | 登录接口 |

### 1.2 ID 依赖

| 识别规则 | 依赖变量 | 来源接口 |
|---------|---------|---------|
| Path 参数名含 `id` 或 `Id`（如 `{id}`） | `${RESOURCE_ID}` | 对应资源的 POST 创建接口 |
| Body 参数名含 `Id` 后缀（如 `addressId`） | `${ADDRESS_ID}` | 对应资源的创建接口 |
| Body 参数名含 `code` 后缀（如 `orderCode`） | `${ORDER_CODE}` | 对应资源的创建接口 |

### 1.3 关联数据依赖

| 识别规则 | 依赖变量 | 来源接口 |
|---------|---------|---------|
| Body 参数名含 `Key`（如 `captchaKey`） | `${CAPTCHA_KEY}` | 验证码生成接口 |
| Body 参数含数组类型 ID（如 `cartIds`） | `${CART_IDS}` | 添加购物车接口 |
| Query 参数含分页（如 `page`, `size`） | 无依赖，直接生成合法值 | — |

---

## 2. 依赖链自动分析算法

### 2.1 步骤

1. **收集所有接口的参数信息**：提取 Path/Query/Header/Body 参数
2. **识别资源创建接口**：method=POST 且不含路径 ID 的接口
3. **识别资源操作接口**：method=GET/PUT/DELETE 且含路径 ID 的接口
4. **建立资源映射表**：将路径模式映射到资源类型
5. **匹配依赖关系**：将操作接口的 ID 参数关联到创建接口
6. **排序依赖链**：按拓扑排序确定执行顺序

### 2.2 路径模式匹配

| 路径模式 | 资源类型 | 创建接口 | 操作接口 |
|---------|---------|---------|---------|
| `/api/users` + `/api/users/{id}` | 用户 | POST /api/users | GET/PUT/DELETE /api/users/{id} |
| `/api/orders` + `/api/orders/{id}` | 订单 | POST /api/orders | GET/PUT/DELETE /api/orders/{id} |
| `/api/products` + `/api/products/{id}` | 商品 | POST /api/products | GET/PUT/DELETE /api/products/{id} |
| `/api/address` + `/api/address/{id}` | 地址 | POST /api/address | GET/PUT/DELETE /api/address/{id} |
| `/api/cart` + `/api/cart/{id}` | 购物车 | POST /api/cart | GET/PUT/DELETE /api/cart/{id} |

### 2.3 特殊依赖模式

| 模式 | 说明 | 示例 |
|------|------|------|
| 订单依赖地址 | 创建订单需要 addressId | POST /api/order 依赖 POST /api/address |
| 订单依赖购物车 | 创建订单需要 cartIds | POST /api/order 依赖 POST /api/cart |
| 支付依赖订单 | 支付需要 orderId | POST /api/order/pay 依赖 POST /api/order |
| 验证码依赖 | 登录/注册需要 captchaKey | POST /api/auth/login 依赖 GET /api/captcha |

---

## 3. 依赖变量标记格式

### 3.1 标记语法

在测试数据中使用 `${VARIABLE_NAME}` 格式标记依赖参数：

```yaml
parameters:
  body_params:
    addressId: "${ADDRESS_ID}"       # 地址 ID 依赖
    paymentType: 1                   # 无依赖，直接生成
    cartIds: "${CART_IDS}"           # 购物车 ID 列表依赖
  header_params:
    Authorization: "Bearer ${TOKEN}" # Token 依赖
```

### 3.2 变量命名规范

| 变量名 | 含义 | 典型来源 |
|--------|------|---------|
| `${TOKEN}` | 登录 Token | POST /api/auth/login → response.data.token |
| `${USER_ID}` | 用户 ID | POST /api/auth/register → response.data.id |
| `${ORDER_ID}` | 订单 ID | POST /api/order → response.data.id |
| `${ORDER_CODE}` | 订单编号 | POST /api/order → response.data.orderCode |
| `${ADDRESS_ID}` | 地址 ID | POST /api/address → response.data.id |
| `${PRODUCT_ID}` | 商品 ID | GET /api/product/list → response.data[0].id |
| `${CART_ID}` | 购物车项 ID | POST /api/cart → response.data.id |
| `${CART_IDS}` | 购物车项 ID 列表 | POST /api/cart（多次）→ [id1, id2] |
| `${CATEGORY_ID}` | 分类 ID | GET /api/category/list → response.data[0].id |
| `${CAPTCHA_KEY}` | 验证码 Key | GET /api/captcha → response.data.key |
| `${BANNER_ID}` | Banner ID | POST /api/admin/banner → response.data.id |

---

## 4. 依赖配置输出

### 4.1 全局依赖配置文件

生成 `_dependencies.yaml` 文件，定义所有依赖链：

```yaml
# _dependencies.yaml
global_dependencies:
  auth:
    variable: "TOKEN"
    source_api: "POST_/api/auth/login"
    source_params:
      username: "admin"
      password: "Admin1234"
    extract_path: "data.token"
    description: "管理员登录获取 Token"

dependency_chains:
  - name: "订单流程"
    description: "完整的下单支付流程依赖链"
    steps:
      - step: 1
        api_id: "POST_/api/auth/login"
        description: "登录获取 Token"
        extract:
          TOKEN: "data.token"

      - step: 2
        api_id: "POST_/api/address"
        description: "创建收货地址"
        requires: ["TOKEN"]
        extract:
          ADDRESS_ID: "data.id"

      - step: 3
        api_id: "POST_/api/cart"
        description: "添加商品到购物车"
        requires: ["TOKEN", "PRODUCT_ID"]
        extract:
          CART_ID: "data.id"

      - step: 4
        api_id: "POST_/api/order"
        description: "创建订单"
        requires: ["TOKEN", "ADDRESS_ID", "CART_IDS"]
        extract:
          ORDER_ID: "data.id"
          ORDER_CODE: "data.orderCode"

      - step: 5
        api_id: "POST_/api/order/pay"
        description: "支付订单"
        requires: ["TOKEN", "ORDER_ID"]
```

### 4.2 全局配置文件

生成 `_config.yaml` 文件，定义全局测试配置：

```yaml
# _config.yaml
base_url: "http://localhost:8080"
auth:
  type: "Bearer Token"
  header: "Authorization"
  token_variable: "TOKEN"
  default_user:
    username: "admin"
    password: "Admin1234"

test_accounts:
  - username: "admin"
    password: "Admin1234"
    role: "admin"
    description: "管理员账号"
  - username: "testuser01"
    password: "Test1234"
    role: "user"
    description: "普通用户账号"

response_format:
  success:
    code: 200
    data_path: "data"
  error:
    code_path: "code"
    message_path: "message"
```

---

## 5. 循环依赖检测

### 5.1 检测算法

使用深度优先搜索（DFS）检测循环依赖：

1. 构建依赖有向图（节点=接口，边=依赖关系）
2. 对每个节点执行 DFS
3. 如果发现回边（指向当前路径上的节点），则存在循环依赖
4. 输出循环依赖路径

### 5.2 循环依赖处理

当检测到循环依赖时：

1. 在输出中标记循环依赖
2. 提示用户手动处理
3. 尝试通过模拟数据打破循环（为循环中的某些参数生成硬编码值）

```yaml
circular_dependencies:
  - cycle: ["POST_/api/A", "GET_/api/B", "POST_/api/A"]
    description: "接口 A 依赖接口 B 的返回值，接口 B 又依赖接口 A 的返回值"
    resolution: "为接口 B 的参数手动设置固定值以打破循环"
```

---

## 6. 依赖数据预生成

### 6.1 前置数据文件

对于每个依赖链，生成一个前置数据准备文件：

```yaml
# test_data/_setup.yaml
description: "测试数据前置准备脚本"

setup_steps:
  - step: 1
    name: "管理员登录"
    api_id: "POST_/api/auth/login"
    parameters:
      username: "admin"
      password: "Admin1234"
    extract:
      TOKEN: "data.token"

  - step: 2
    name: "创建测试商品"
    api_id: "POST_/api/admin/product"
    headers:
      Authorization: "Bearer ${TOKEN}"
    parameters:
      name: "测试商品-自动化"
      price: 99.99
      stock: 1000
      categoryId: 1
    extract:
      PRODUCT_ID: "data.id"

  - step: 3
    name: "创建测试地址"
    api_id: "POST_/api/address"
    headers:
      Authorization: "Bearer ${TOKEN}"
    parameters:
      name: "测试收货人"
      phone: "13800001111"
      province: "北京市"
      city: "北京市"
      district: "朝阳区"
      detail: "测试街道1号"
    extract:
      ADDRESS_ID: "data.id"
```

### 6.2 清理脚本

```yaml
# test_data/_teardown.yaml
description: "测试数据清理脚本"

teardown_steps:
  - step: 1
    name: "删除测试订单"
    api_id: "DELETE_/api/admin/order/{id}"
    headers:
      Authorization: "Bearer ${TOKEN}"

  - step: 2
    name: "删除测试地址"
    api_id: "DELETE_/api/address/{id}"
    headers:
      Authorization: "Bearer ${TOKEN}"
```
