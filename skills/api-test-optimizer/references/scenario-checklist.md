# 10维度场景补齐检查清单

本文档定义了 api-test-optimizer 执行10维度场景补齐时的详细检查清单，包含每个维度的具体检查项、常见遗漏场景示例和补齐用例代码模板。

---

## D1 - 正向场景

### 检查项

| 序号 | 检查项 | 常见遗漏 |
|------|--------|---------|
| D1-01 | 核心业务流程是否覆盖 | 只测了单一步骤，未覆盖完整流程 |
| D1-02 | 多种合法输入组合是否覆盖 | 只测了一种合法数据，未测其他合法组合 |
| D1-03 | 不同用户角色/权限下的正常流程 | 只测了管理员，未测普通用户 |
| D1-04 | 不同业务状态下的正常操作 | 只测了初始状态，未测中间状态操作 |
| D1-05 | 默认值/可选参数省略时的正常流程 | 所有参数都传了，未测省略可选参数 |

### 补齐用例模板

```python
# ===== [优化器补齐] D1-正向场景 =====
@pytest.mark.p0
@allure.title("{api_name} - 完整业务流程")
@allure.feature("{module_name}")
@allure.story("正向场景")
def test_{method_name}_full_flow(self, request_util, auth_headers):
    """测试完整业务流程：{flow_description}"""
    api = {ClassName}API(request_util)
    # Step 1: 前置操作
    {pre_step}
    # Step 2: 目标操作
    response = api.{method_name}({params}, headers=auth_headers)
    # Step 3: 结果验证
    AssertUtil.assert_all(
        response,
        expected_status=200,
        expected_code=0,
        field_checks=[{field_checks}]
    )
```

---

## D2 - 必填校验

### 检查项

| 序号 | 检查项 | 常见遗漏 |
|------|--------|---------|
| D2-01 | 每个必填参数是否有空值用例 | 只测了全部参数传空，未逐一测试 |
| D2-02 | 必填参数缺失时是否返回正确错误码 | 只断言了 status_code，未断言业务错误码 |
| D2-03 | 多个必填参数组合缺失的场景 | 未覆盖同时缺失多个必填参数 |
| D2-04 | 必填参数传 null/None 的场景 | 空字符串和 null 可能返回不同错误 |
| D2-05 | 必填参数传空白字符串（含空格）的场景 | "  " 可能绕过空值检查 |

### 补齐用例模板

```python
# ===== [优化器补齐] D2-必填校验 =====
@pytest.mark.p0
@allure.title("{api_name} - 必填参数{param_name}为空")
@allure.feature("{module_name}")
@allure.story("必填校验")
def test_{method_name}_{param_name}_empty(self, request_util, auth_headers):
    """测试必填参数 {param_name} 为空"""
    api = {ClassName}API(request_util)
    params = {default_params}
    params["{param_name}"] = ""
    response = api.{method_name}(**params, headers=auth_headers)
    AssertUtil.assert_all(
        response,
        expected_status=400,
        expected_code={error_code},
        field_checks=[
            {"field": "message", "check": "contains", "expect": "{param_name}"}
        ]
    )

@pytest.mark.p0
@allure.title("{api_name} - 必填参数{param_name}为null")
@allure.feature("{module_name}")
@allure.story("必填校验")
def test_{method_name}_{param_name}_null(self, request_util, auth_headers):
    """测试必填参数 {param_name} 为 None"""
    api = {ClassName}API(request_util)
    params = {default_params}
    params["{param_name}"] = None
    response = api.{method_name}(**params, headers=auth_headers)
    AssertUtil.assert_all(
        response,
        expected_status=400,
        expected_code={error_code}
    )
```

---

## D3 - 参数合法性

### 检查项

| 序号 | 检查项 | 常见遗漏 |
|------|--------|---------|
| D3-01 | 类型不匹配（字符串传数字、数字传字符串） | 后端做了隐式转换但未测试边界 |
| D3-02 | 格式不合法（邮箱/手机号/日期格式） | 只测了一种错误格式 |
| D3-03 | 长度超限（超长字符串/极短输入） | 未测试最大长度+1 |
| D3-04 | 枚举值不合法（不在枚举范围内的值） | 传了不在枚举中的值 |
| D3-05 | 特殊字符输入（中文/表情/控制字符） | 用户名字段未测特殊字符 |
| D3-06 | 数值范围不合法（负数/超大数/小数） | 金额字段传了负数 |
| D3-07 | 布尔值类型混淆（字符串"true" vs 布尔true） | 参数类型为boolean但传了字符串 |
| D3-08 | 数组类型参数异常（空数组/嵌套对象） | 传了非数组值给数组参数 |

### 补齐用例模板

```python
# ===== [优化器补齐] D3-参数合法性 =====
@pytest.mark.p0
@allure.title("{api_name} - {param_name}类型不匹配")
@allure.feature("{module_name}")
@allure.story("参数合法性")
def test_{method_name}_{param_name}_type_mismatch(self, request_util, auth_headers):
    """测试参数 {param_name} 类型不匹配：期望{expected_type}，传入{actual_type}"""
    api = {ClassName}API(request_util)
    params = {default_params}
    params["{param_name}"] = {invalid_value}
    response = api.{method_name}(**params, headers=auth_headers)
    AssertUtil.assert_status_code(response, 400)
    AssertUtil.assert_business_code(response, {error_code})

@pytest.mark.p1
@allure.title("{api_name} - {param_name}格式不合法")
@allure.feature("{module_name}")
@allure.story("参数合法性")
def test_{method_name}_{param_name}_invalid_format(self, request_util, auth_headers):
    """测试参数 {param_name} 格式不合法：传入 '{invalid_format}'"""
    api = {ClassName}API(request_util)
    params = {default_params}
    params["{param_name}"] = "{invalid_format}"
    response = api.{method_name}(**params, headers=auth_headers)
    AssertUtil.assert_status_code(response, 400)

@pytest.mark.p1
@allure.title("{api_name} - {param_name}长度超限")
@allure.feature("{module_name}")
@allure.story("参数合法性")
def test_{method_name}_{param_name}_too_long(self, request_util, auth_headers):
    """测试参数 {param_name} 长度超限：传入 {max_length}+1 个字符"""
    api = {ClassName}API(request_util)
    params = {default_params}
    params["{param_name}"] = "A" * ({max_length} + 1)
    response = api.{method_name}(**params, headers=auth_headers)
    AssertUtil.assert_status_code(response, 400)
```

---

## D4 - 边界值

### 检查项

| 序号 | 检查项 | 常见遗漏 |
|------|--------|---------|
| D4-01 | 边界内最小值 | 整数最小值1，传了1 |
| D4-02 | 边界内最大值 | 分页最大值100，传了100 |
| D4-03 | 边界外值（最小值-1、最大值+1） | 传了0或101 |
| D4-04 | 空字符串 "" | 空字符串和null行为可能不同 |
| D4-05 | null / None | 有些接口将null视为空值 |
| D4-06 | 零值 | 金额为0、数量为0 |
| D4-07 | 负值 | 金额为负数、数量为负数 |
| D4-08 | 浮点数精度 | 金额 1.00 vs 1.001 |
| D4-09 | 特殊数值 | Integer.MAX、Long.MAX |
| D4-10 | 超长字符串 | 10万字符的字符串 |

### 补齐用例模板

```python
# ===== [优化器补齐] D4-边界值 =====
@pytest.mark.p0
@allure.title("{api_name} - {param_name}边界最小值")
@allure.feature("{module_name}")
@allure.story("边界值")
def test_{method_name}_{param_name}_min_boundary(self, request_util, auth_headers):
    """测试参数 {param_name} 边界最小值：{min_value}"""
    api = {ClassName}API(request_util)
    params = {default_params}
    params["{param_name}"] = {min_value}
    response = api.{method_name}(**params, headers=auth_headers)
    AssertUtil.assert_all(response, expected_status=200, expected_code=0,
        field_checks=[{field_checks}])

@pytest.mark.p0
@allure.title("{api_name} - {param_name}边界外值")
@allure.feature("{module_name}")
@allure.story("边界值")
def test_{method_name}_{param_name}_over_boundary(self, request_util, auth_headers):
    """测试参数 {param_name} 超出边界：{over_value}"""
    api = {ClassName}API(request_util)
    params = {default_params}
    params["{param_name}"] = {over_value}
    response = api.{method_name}(**params, headers=auth_headers)
    AssertUtil.assert_status_code(response, 400)

@pytest.mark.p1
@allure.title("{api_name} - {param_name}为零值")
@allure.feature("{module_name}")
@allure.story("边界值")
def test_{method_name}_{param_name}_zero(self, request_util, auth_headers):
    """测试参数 {param_name} 为零值"""
    api = {ClassName}API(request_util)
    params = {default_params}
    params["{param_name}"] = 0
    response = api.{method_name}(**params, headers=auth_headers)
    AssertUtil.assert_status_code(response, 400)
```

---

## D5 - 异常处理

### 检查项

| 序号 | 检查项 | 常见遗漏 |
|------|--------|---------|
| D5-01 | 网络超时/连接异常 | 服务不可达时的降级处理 |
| D5-02 | 服务端 500/502/503 错误 | 上游服务异常时的处理 |
| D5-03 | 数据不存在/已删除 | 查询已删除资源 |
| D5-04 | 数据重复/已存在 | 重复创建已存在的资源 |
| D5-05 | 并发请求冲突 | 同一资源并发修改 |
| D5-06 | 请求频率超限 | 超过接口限流阈值 |
| D5-07 | 请求体过大 | 超过服务端限制 |
| D5-08 | 请求方法不允许 | GET 接口用 POST 请求 |

### 补齐用例模板

```python
# ===== [优化器补齐] D5-异常处理 =====
@pytest.mark.p0
@allure.title("{api_name} - 资源不存在")
@allure.feature("{module_name}")
@allure.story("异常处理")
def test_{method_name}_resource_not_found(self, request_util, auth_headers):
    """测试访问不存在的资源"""
    api = {ClassName}API(request_util)
    response = api.{method_name}({non_exist_id}, headers=auth_headers)
    AssertUtil.assert_all(
        response,
        expected_status=404,
        expected_code={not_found_code},
        field_checks=[
            {"field": "message", "check": "contains", "expect": "不存在"}
        ]
    )

@pytest.mark.p1
@allure.title("{api_name} - 资源已删除")
@allure.feature("{module_name}")
@allure.story("异常处理")
def test_{method_name}_resource_deleted(self, request_util, auth_headers):
    """测试访问已删除的资源"""
    api = {ClassName}API(request_util)
    # 先删除资源
    {delete_step}
    # 再访问
    response = api.{method_name}({deleted_id}, headers=auth_headers)
    AssertUtil.assert_status_code(response, 404)

@pytest.mark.p1
@allure.title("{api_name} - 数据已存在（重复创建）")
@allure.feature("{module_name}")
@allure.story("异常处理")
def test_{method_name}_duplicate_create(self, request_util, auth_headers):
    """测试重复创建已存在的资源"""
    api = {ClassName}API(request_util)
    # 第一次创建
    response1 = api.{method_name}({params}, headers=auth_headers)
    AssertUtil.assert_status_code(response1, 200)
    # 第二次创建相同数据
    response2 = api.{method_name}({params}, headers=auth_headers)
    AssertUtil.assert_status_code(response2, 409)
```

---

## D6 - 业务规则

### 检查项

| 序号 | 检查项 | 常见遗漏 |
|------|--------|---------|
| D6-01 | 业务互斥条件 | 优惠不可叠加、同一商品不可重复购买 |
| D6-02 | 状态约束 | 已取消订单不可支付、已发货订单不可修改 |
| D6-03 | 权限控制 | 普通用户不可访问管理接口、不可操作他人数据 |
| D6-04 | 数据一致性 | 扣款金额=订单金额、库存扣减=购买数量 |
| D6-05 | 时间约束 | 活动未开始不可参与、已过期不可退款 |
| D6-06 | 数量约束 | 超过限购数量、不足起购数量 |
| D6-07 | 条件组合 | 多个条件同时满足/不满足 |
| D6-08 | 业务计算规则 | 折扣计算、积分抵扣、税费计算 |

### 补齐用例模板

```python
# ===== [优化器补齐] D6-业务规则 =====
@pytest.mark.p0
@allure.title("{api_name} - {business_rule_violation}")
@allure.feature("{module_name}")
@allure.story("业务规则")
def test_{method_name}_{rule_name}(self, request_util, auth_headers):
    """测试业务规则：{business_rule_description}"""
    api = {ClassName}API(request_util)
    params = {default_params}
    {modify_params_to_violate_rule}
    response = api.{method_name}(**params, headers=auth_headers)
    AssertUtil.assert_all(
        response,
        expected_status=200,
        expected_code={error_code},
        field_checks=[
            {"field": "message", "check": "contains", "expect": "{error_keyword}"}
        ]
    )
```

---

## D7 - 安全风险

### 检查项

| 序号 | 检查项 | 常见遗漏 |
|------|--------|---------|
| D7-01 | SQL注入 | `' OR 1=1 --`、`"; DROP TABLE users;--` |
| D7-02 | XSS攻击 | `<script>alert(1)</script>`、`<img onerror=alert(1) src=x>` |
| D7-03 | 越权访问-无Token | 不带 Authorization 请求需鉴权接口 |
| D7-04 | 越权访问-他人Token | 使用其他用户的Token访问他人数据 |
| D7-05 | 敏感数据明文传输 | 密码未加密、手机号未脱敏 |
| D7-06 | 批量数据遍历 | 递增ID遍历获取所有用户数据 |
| D7-07 | CSRF攻击 | 缺少 CSRF Token 验证 |
| D7-08 | 命令注入 | `| rm -rf /`、`$(cat /etc/passwd)` |
| D7-09 | 路径遍历 | `../../etc/passwd`、`..\\..\\windows\\system32` |
| D7-10 | 敏感信息泄露 | 错误响应中暴露堆栈/SQL/内部地址 |

### 补齐用例模板

```python
# ===== [优化器补齐] D7-安全风险 =====
@pytest.mark.p0
@allure.title("{api_name} - SQL注入攻击")
@allure.feature("{module_name}")
@allure.story("安全风险")
def test_{method_name}_sql_injection(self, request_util, auth_headers):
    """测试SQL注入：参数 {param_name} 注入恶意SQL"""
    api = {ClassName}API(request_util)
    params = {default_params}
    params["{param_name}"] = "' OR 1=1 --"
    response = api.{method_name}(**params, headers=auth_headers)
    # 不应返回正常数据
    AssertUtil.assert_status_code(response, 400)

@pytest.mark.p0
@allure.title("{api_name} - 无Token访问")
@allure.feature("{module_name}")
@allure.story("安全风险")
def test_{method_name}_no_token(self, request_util):
    """测试无Token访问需鉴权接口"""
    api = {ClassName}API(request_util)
    response = api.{method_name}({params}, headers={"Content-Type": "application/json"})
    AssertUtil.assert_status_code(response, 401)

@pytest.mark.p1
@allure.title("{api_name} - XSS攻击")
@allure.feature("{module_name}")
@allure.story("安全风险")
def test_{method_name}_xss_attack(self, request_util, auth_headers):
    """测试XSS攻击：参数 {param_name} 注入脚本标签"""
    api = {ClassName}API(request_util)
    params = {default_params}
    params["{param_name}"] = '<script>alert("XSS")</script>'
    response = api.{method_name}(**params, headers=auth_headers)
    # 响应中不应包含未转义的脚本标签
    assert "<script>" not in response.text, "响应中包含未转义的脚本标签，存在XSS风险"

@pytest.mark.p1
@allure.title("{api_name} - 越权访问他人数据")
@allure.feature("{module_name}")
@allure.story("安全风险")
def test_{method_name}_access_others_data(self, request_util, auth_headers):
    """测试使用A用户Token访问B用户数据"""
    api = {ClassName}API(request_util)
    # 使用当前用户Token访问其他用户数据
    response = api.{method_name}({other_user_id}, headers=auth_headers)
    # 应返回403或空数据
    assert response.status_code in [403, 404], "越权访问未做限制"
```

---

## D8 - 接口依赖

### 检查项

| 序号 | 检查项 | 常见遗漏 |
|------|--------|---------|
| D8-01 | 前置接口失败时的降级处理 | 创建订单失败后查询订单 |
| D8-02 | 依赖数据不存在时的处理 | 查询不存在的关联ID |
| D8-03 | 接口调用顺序异常 | 未登录直接调用业务接口 |
| D8-04 | 依赖接口返回数据格式变化 | 上游接口增加了字段但未影响逻辑 |
| D8-05 | 依赖接口超时 | 上游接口响应慢导致级联超时 |
| D8-06 | 级联删除 | 删除父资源时子资源是否级联处理 |

### 补齐用例模板

```python
# ===== [优化器补齐] D8-接口依赖 =====
@pytest.mark.p0
@allure.title("{api_name} - 前置接口失败后降级")
@allure.feature("{module_name}")
@allure.story("接口依赖")
def test_{method_name}_dependency_failed(self, request_util, auth_headers):
    """测试前置接口失败后的降级处理"""
    api = {ClassName}API(request_util)
    # 模拟前置接口失败：使用不存在的依赖ID
    response = api.{method_name}({non_exist_dependency_id}, headers=auth_headers)
    AssertUtil.assert_status_code(response, 404)

@pytest.mark.p1
@allure.title("{api_name} - 未登录直接访问")
@allure.feature("{module_name}")
@allure.story("接口依赖")
def test_{method_name}_without_login(self, request_util):
    """测试未登录直接访问需鉴权接口"""
    api = {ClassName}API(request_util)
    # 不注入Token
    response = api.{method_name}({params}, headers={"Content-Type": "application/json"})
    AssertUtil.assert_status_code(response, 401)
```

---

## D9 - 兼容性

### 检查项

| 序号 | 检查项 | 常见遗漏 |
|------|--------|---------|
| D9-01 | 不同 API 版本兼容 | v1 和 v2 接口行为差异 |
| D9-02 | 不同 Content-Type | JSON/Form/Data 格式 |
| D9-03 | 不同编码 | UTF-8/GBK/ISO-8859-1 |
| D9-04 | 分页参数不同组合 | page=0 vs page=1, size=-1 vs size=0 |
| D9-05 | 排序参数组合 | 多字段排序、倒序排列 |
| D9-06 | 字段过滤 | fields 参数仅返回指定字段 |
| D9-07 | 空结果集 | 查询条件无匹配时的响应格式 |

### 补齐用例模板

```python
# ===== [优化器补齐] D9-兼容性 =====
@pytest.mark.p2
@allure.title("{api_name} - 不同Content-Type兼容")
@allure.feature("{module_name}")
@allure.story("兼容性")
def test_{method_name}_content_type_compatibility(self, request_util, auth_headers):
    """测试不同 Content-Type 请求的兼容性"""
    api = {ClassName}API(request_util)
    # JSON 格式
    headers_json = {**auth_headers, "Content-Type": "application/json"}
    response_json = api.{method_name}({params}, headers=headers_json)
    AssertUtil.assert_status_code(response_json, 200)
    # Form 格式
    headers_form = {**auth_headers, "Content-Type": "application/x-www-form-urlencoded"}
    response_form = api.{method_name}({params}, headers=headers_form)
    # 两种格式都应返回成功
    assert response_json.status_code == response_form.status_code

@pytest.mark.p2
@allure.title("{api_name} - 空结果集处理")
@allure.feature("{module_name}")
@allure.story("兼容性")
def test_{method_name}_empty_result(self, request_util, auth_headers):
    """测试查询条件无匹配时的响应格式"""
    api = {ClassName}API(request_util)
    response = api.{method_name}({no_match_params}, headers=auth_headers)
    AssertUtil.assert_all(
        response,
        expected_status=200,
        expected_code=0,
        field_checks=[
            {"field": "data.list", "check": "length", "expect": 0},
            {"field": "data.total", "check": "equals", "expect": 0}
        ]
    )
```

---

## D10 - 断言完整性

### 检查项

| 序号 | 检查项 | 常见遗漏 |
|------|--------|---------|
| D10-01 | 是否有三层断言（状态码+业务码+业务数据） | 只有状态码断言 |
| D10-02 | 业务数据断言是否覆盖关键字段 | 只断言了部分字段 |
| D10-03 | 错误响应是否有完整断言 | 错误场景只断言状态码 |
| D10-04 | 断言信息是否包含实际值 | 断言消息中只有"断言失败"无实际值 |
| D10-05 | 集合类型断言是否检查长度/内容 | 返回列表只断言非空，未检查内容 |
| D10-06 | 数值类型断言是否检查精度 | 金额断言未考虑浮点精度 |
| D10-07 | 时间类型断言是否检查格式/范围 | 时间字段未验证格式 |
| D10-08 | 嵌套对象断言是否检查深层次字段 | 只检查了第一层字段 |

### 补齐用例模板

```python
# ===== [优化器补齐] D10-断言完整性 =====
# 场景：原有用例只有状态码断言，补充三层断言

# 优化前：
def test_{method_name}_success(self, request_util, auth_headers):
    api = {ClassName}API(request_util)
    response = api.{method_name}({params}, headers=auth_headers)
    assert response.status_code == 200

# 优化后：
def test_{method_name}_success(self, request_util, auth_headers):
    """[优化器修复] 补充三层断言"""
    api = {ClassName}API(request_util)
    response = api.{method_name}({params}, headers=auth_headers)
    # [优化器修复] 原只有状态码断言，补充业务码+业务数据断言
    AssertUtil.assert_all(
        response,
        expected_status=200,
        expected_code=0,
        field_checks=[
            {"field": "data.{key_field}", "check": "not_empty"},
            {"field": "data.{type_field}", "check": "type", "expect": {expected_type}},
        ]
    )
```

---

## 场景补齐优先级评定规则

| 优先级 | 评定标准 | 示例 |
|--------|---------|------|
| **P0** | 必补场景：安全漏洞、数据丢失/损坏风险、核心业务流程缺失 | SQL注入、无Token访问、金额为负数 |
| **P1** | 重要场景：边界值遗漏、异常处理缺失、业务规则违反 | 最大值+1、资源不存在、状态约束 |
| **P2** | 建议场景：兼容性、性能、代码质量优化 | 不同Content-Type、空结果集、嵌套断言 |

## 场景补齐统计维度

对每个接口，按以下维度统计补齐情况：

```
接口：POST_/api/auth/login
┌──────────┬──────────┬──────────┬──────────┐
│   维度   │ 原有用例 │ 补齐数   │ 补齐率   │
├──────────┼──────────┼──────────┼──────────┤
│ D1 正向  │    2     │    1     │  +50%    │
│ D2 必填  │    1     │    3     │ +300%    │
│ D3 合法  │    0     │    4     │  新增    │
│ D4 边界  │    1     │    3     │ +300%    │
│ D5 异常  │    2     │    2     │ +100%    │
│ D6 规则  │    1     │    2     │ +200%    │
│ D7 安全  │    0     │    3     │  新增    │
│ D8 依赖  │    0     │    2     │  新增    │
│ D9 兼容  │    0     │    1     │  新增    │
│ D10 断言 │    1     │    0     │   0%     │
├──────────┼──────────┼──────────┼──────────┤
│   合计   │    8     │   21     │ +263%    │
└──────────┴──────────┴──────────┴──────────┘
```
