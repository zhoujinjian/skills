# 断言策略与模式

## 一、三层断言规范

每条测试用例必须至少包含以下 **3 层断言**，禁止只断言 `status_code` 或无意义断言。

### 第一层：状态码断言

| HTTP 状态码 | 含义 | 断言方式 |
|------------|------|---------|
| 200 | 请求成功 | `assert_status_code(response, 200)` |
| 201 | 创建成功 | `assert_status_code(response, 201)` |
| 204 | 删除成功（无返回体） | `assert_status_code(response, 204)` |
| 400 | 参数校验失败 | `assert_status_code(response, 400)` |
| 401 | 未认证 | `assert_status_code(response, 401)` |
| 403 | 无权限 | `assert_status_code(response, 403)` |
| 404 | 资源不存在 | `assert_status_code(response, 404)` |
| 409 | 资源冲突 | `assert_status_code(response, 409)` |
| 422 | 参数格式错误 | `assert_status_code(response, 422)` |
| 500 | 服务器内部错误 | `assert_status_code(response, 500)` |

### 第二层：业务码断言

| 业务码 | 含义 | 断言方式 |
|-------|------|---------|
| 0 | 成功 | `assert_business_code(response, 0)` |
| 40001 | 参数无效 | `assert_business_code(response, 40001)` |
| 40101 | Token 无效 | `assert_business_code(response, 40101)` |
| 40301 | 权限不足 | `assert_business_code(response, 40301)` |
| 40401 | 资源不存在 | `assert_business_code(response, 40401)` |
| 40901 | 资源已存在 | `assert_business_code(response, 40901)` |
| 50000 | 系统异常 | `assert_business_code(response, 50000)` |

> **注意**：业务码定义因项目而异，从 `api_definitions.json` 的 `responses.errors.error_code` 中提取。

### 第三层：业务数据断言

| 检查类型 | check 值 | 说明 | 示例 |
|---------|----------|------|------|
| 非空检查 | `not_empty` | 字段值不为 None 且不为空字符串 | `{"field": "data.id", "check": "not_empty"}` |
| 值匹配 | `equals` | 字段值等于期望值 | `{"field": "data.username", "check": "equals", "expect": "zhangsan"}` |
| 类型检查 | `type` | 字段值类型匹配 | `{"field": "data.age", "check": "type", "expect": int}` |
| 包含检查 | `contains` | 字段值包含期望内容 | `{"field": "data.email", "check": "contains", "expect": "@"}` |
| 长度检查 | `length` | 字段值长度等于期望值 | `{"field": "data.phone", "check": "length", "expect": 11}` |

## 二、响应字段路径取值规则

断言工具按 `.` 分隔的路径逐层取值：

```
json_data.data.user.name
↓
json_data["data"]["user"]["name"]
```

### 取值逻辑

```python
value = json_data
for key in field_path.split("."):
    if isinstance(value, dict):
        value = value.get(key)
    elif isinstance(value, list) and key.isdigit():
        value = value[int(key)]
    else:
        value = None
        break
```

### 路径示例

| 字段路径 | 含义 | 取值方式 |
|---------|------|---------|
| `code` | 顶层业务码 | `json_data["code"]` |
| `data.id` | 数据ID | `json_data["data"]["id"]` |
| `data.user.name` | 嵌套字段 | `json_data["data"]["user"]["name"]` |
| `data.items.0.id` | 数组首项 | `json_data["data"]["items"][0]["id"]` |

## 三、断言失败信息格式

所有断言失败必须包含：
1. **期望值** 和 **实际值**
2. **失败原因**
3. **响应体前 500 字符**（用于定位问题）

### 格式模板

```
{断言类型}断言失败: 期望={expected}, 实际={actual} | 响应={response.text[:500]}
```

### 示例

```
状态码断言失败: 期望=200, 实际=400 | 响应={"code":40001,"message":"用户名不能为空","data":null}
业务码断言失败: 期望=0, 实际=40001 | message=用户名不能为空 | 响应={"code":40001,"message":"用户名不能为空","data":null}
字段非空断言失败: data.id 值为空 | 响应={"code":0,"data":{"id":null,"username":"zhangsan"}}
字段匹配断言失败: data.username 期望=zhangsan, 实际=lisi | 响应={"code":0,"data":{"username":"lisi"}}
```

## 四、按场景的断言策略

### 正向场景断言

```python
AssertUtil.assert_all(
    response,
    expected_status=200,
    expected_code=0,
    field_checks=[
        {"field": "data.id", "check": "not_empty"},
        {"field": "data.username", "check": "equals", "expect": "zhangsan"},
        {"field": "data.email", "check": "contains", "expect": "@"},
    ]
)
```

### 异常场景断言

```python
# 参数校验失败
AssertUtil.assert_all(
    response,
    expected_status=400,
    expected_code=40001,
    field_checks=[
        {"field": "message", "check": "not_empty"},
    ]
)

# 未认证
AssertUtil.assert_all(
    response,
    expected_status=401,
    expected_code=40101,
)

# 资源不存在
AssertUtil.assert_all(
    response,
    expected_status=404,
    expected_code=40401,
)
```

### 边界场景断言

```python
# 最小长度边界
AssertUtil.assert_all(
    response,
    expected_status=200,
    expected_code=0,
    field_checks=[
        {"field": "data.username", "check": "length", "expect": 3},
    ]
)

# 最大长度边界
AssertUtil.assert_all(
    response,
    expected_status=200,
    expected_code=0,
    field_checks=[
        {"field": "data.username", "check": "length", "expect": 50},
    ]
)
```

### 安全场景断言

```python
# SQL 注入
AssertUtil.assert_all(
    response,
    expected_status=400,
    expected_code=40001,
    field_checks=[
        {"field": "message", "check": "not_empty"},
    ]
)

# XSS 攻击
AssertUtil.assert_all(
    response,
    expected_status=400,
    expected_code=40001,
)
```

## 五、数据驱动断言

数据驱动模式下，断言期望从测试数据文件的 `expected` 字段中读取：

```yaml
test_cases:
  - case_id: "POS_001"
    name: "合法请求"
    expected:
      status_code: 200
      business_code: 0
      field_checks:
        - field: "data.id"
          check: "not_empty"
        - field: "data.username"
          check: "equals"
          expect: "zhangsan"
```

对应用例代码：

```python
def test_data_driven(self, case, request_util, auth_headers):
    # ... 发送请求 ...
    AssertUtil.assert_status_code(response, case["expected"]["status_code"])
    if "business_code" in case["expected"]:
        AssertUtil.assert_business_code(response, case["expected"]["business_code"])
    if "field_checks" in case["expected"]:
        AssertUtil.assert_business_data(response, case["expected"]["field_checks"])
```

## 六、禁止断言列表

| 禁止 | 说明 |
|------|------|
| `assert True` | 无意义断言 |
| `assert response is not None` | 过于宽松，不验证任何实际内容 |
| 只断言 `status_code` | 缺少业务码和数据断言 |
| 重复冗余断言 | 同一字段多次相同检查 |
| `assert "error" not in response.text` | 过于脆弱，依赖文本匹配 |
| 断言时间戳精确值 | 时间戳不可控，应检查格式或范围 |
