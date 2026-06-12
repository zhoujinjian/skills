# 修复策略详解

本文档详细描述每种 SCRIPT_ERROR 子类型的修复策略，包括判定方法、修复操作和代码模板。

---

## 1. 接口变更（API_CHANGE）

### 判定方法

1. 请求返回 404/405，但服务健康检查通过（其他接口正常）
2. 如有 `--api-doc`，对比当前请求路径/参数与文档定义
3. 检查错误信息中的 URL 与 api-doc 中的路径是否匹配

### 修复操作

**路径变更：**
```python
# 修复前
url = f"{BASE_URL}/api/cart/add"
# 修复后
url = f"{BASE_URL}/api/v2/cart/items"
```

**请求方法变更：**
```python
# 修复前
res = requests.get(f"{BASE_URL}/api/order/{order_id}")
# 修复后（api-doc 指明改为 POST）
res = requests.post(f"{BASE_URL}/api/order/query", json={"orderId": order_id})
```

**参数结构变更：**
```python
# 修复前
payload = {"productId": pid, "quantity": qty}
# 修复后（接口新增必填字段）
payload = {"productId": pid, "quantity": qty, "skuId": sku_id}
```

### 注意事项
- 如果没有 `--api-doc`，仅根据错误信息推断变更内容，标记为"低置信度修复"
- 路径变更后同时检查该路径在其他用例中的引用，一并更新

---

## 2. 断言过严（OVER_STRICT_ASSERTION）

### 判定方法

1. AssertionError，但错误值与期望值差异极小（时间戳差几秒、ID格式不同）
2. 断言的字段为非核心业务字段（`createdAt`、`updatedAt`、随机生成的 `id`）
3. 断言方式为精确匹配（`==`）而非范围/格式校验

### 修复操作

**时间戳精确匹配 → 非空校验：**
```python
# 修复前
assert res['data']['createdAt'] == '2024-01-01T10:00:00'
# 修复后
assert res['data']['createdAt'] is not None
assert 'T' in res['data']['createdAt']  # 仅校验格式
```

**随机值精确匹配 → 类型/格式校验：**
```python
# 修复前
assert res['data']['orderId'] == 'ORD_20240101_001'
# 修复后
assert res['data']['orderId'].startswith('ORD_')
assert len(res['data']['orderId']) > 5
```

**数值阈值过严 → 放宽范围：**
```python
# 修复前
assert res['data']['responseTime'] < 100
# 修复后
assert res['data']['responseTime'] < 5000  # 放宽到5秒
```

**非核心字段精确匹配 → 核心字段校验：**
```python
# 修复前
assert res == {"id": 1, "name": "test", "createdAt": "2024-01-01T10:00:00", "version": 3}
# 修复后
assert res['name'] == 'test'
assert 'id' in res
```

### 注意事项
- 核心业务字段（如金额、状态）不应随意放宽，需确认是否确实是接口变更导致
- 放宽断言后仍须保证基本的业务正确性校验

---

## 3. 参数构造错误（PARAM_CONSTRUCTION_ERROR）

### 判定方法

1. TypeError/ValueError 在参数构建代码行触发
2. 接口返回 400 Bad Request，响应体提示参数校验失败（缺少必填字段、类型不匹配）
3. 与 api-doc 对比发现参数定义不匹配

### 修复操作

**缺少必填字段：**
```python
# 修复前
payload = {"productId": pid, "quantity": qty}
# 修复后（接口新增 skuId 必填）
payload = {"productId": pid, "quantity": qty, "skuId": sku_id}
```

**参数类型错误：**
```python
# 修复前
payload = {"amount": "100.00"}  # 接口要求数字类型
# 修复后
payload = {"amount": 100.00}
```

**参数格式错误：**
```python
# 修复前
payload = {"date": "2024-01-01 10:00:00"}  # 接口要求 ISO8601
# 修复后
payload = {"date": "2024-01-01T10:00:00Z"}
```

**嵌套结构错误：**
```python
# 修复前
payload = {"address": "北京市朝阳区XX路"}  # 接口要求对象
# 修复后
payload = {"address": {"province": "北京市", "city": "北京市", "detail": "朝阳区XX路"}}
```

---

## 4. 异常处理缺失（MISSING_EXCEPTION_HANDLING）

### 判定方法

1. KeyError 在访问响应字段时触发
2. TypeError 在解析响应数据时触发（如 `NoneType` 相关）
3. 错误堆栈指向响应解析代码行

### 修复操作

**直接字典访问 → 安全访问：**
```python
# 修复前
assert res['data']['orderId'] is not None
# 修复后
data = res.get('data', {})
if not data:
    pytest.fail(f"接口未返回data字段，响应: {res}")
assert data.get('orderId') is not None
```

**未处理错误响应：**
```python
# 修复前
res = requests.post(url, json=payload).json()
assert res['data']['success'] is True
# 修复后
resp = requests.post(url, json=payload)
res = resp.json()
if resp.status_code != 200 or res.get('code') != 0:
    pytest.fail(f"接口返回错误: status={resp.status_code}, body={res}")
assert res['data']['success'] is True
```

**列表为空时直接访问：**
```python
# 修复前
first_item = res['data']['items'][0]
# 修复后
items = res.get('data', {}).get('items', [])
assert len(items) > 0, "接口返回空列表"
first_item = items[0]
```

---

## 5. 数据依赖错误（DATA_DEPENDENCY_ERROR）

### 判定方法

1. NoneType 错误，且出错变量来自前置步骤的返回值
2. 前置步骤成功但后续步骤使用了错误的字段路径
3. 日志显示传递的值为 `None` 或空字符串

### 修复操作

**取错响应字段路径：**
```python
# 修复前
token = login_res['token']
# 修复后
token = login_res['data']['token']
```

**前置步骤返回值未赋值：**
```python
# 修复前
self.login()  # 返回值未接收
headers = {"Authorization": f"Bearer {self.token}"}  # token 可能为 None
# 修复后
login_res = self.login()
self.token = login_res['data']['token']
headers = {"Authorization": f"Bearer {self.token}"}
```

**fixture 依赖未正确声明：**
```python
# 修复前
def test_create_order(self):
    token = self.token  # 未通过 fixture 获取
# 修复后
def test_create_order(self, auth_token):
    token = auth_token
```

---

## 6. 时序/异步问题（TIMING_ISSUE）

### 判定方法

1. 间歇性失败——同一用例有时通过有时失败
2. 失败后立即重跑通过
3. 错误信息表明数据"未就绪"（如查询结果为空、状态未变更）

### 修复操作

**增加重试/等待：**
```python
# 修复前
res = requests.get(f"{BASE_URL}/api/order/{order_id}")
assert res.json()['data']['status'] == 'PAID'
# 修复后
import time
for i in range(5):
    res = requests.get(f"{BASE_URL}/api/order/{order_id}")
    if res.json()['data']['status'] == 'PAID':
        break
    time.sleep(1)
else:
    pytest.fail(f"订单状态未变为PAID，当前: {res.json()['data']['status']}")
```

**使用 pytest-timeout 避免死等：**
```python
@pytest.mark.timeout(10)
def test_async_callback(self):
    # 增加超时保护
    ...
```

---

## 修复验证清单

修复完成后，逐一检查：

1. [ ] 修改仅涉及失败相关代码，未改动无关逻辑
2. [ ] 修改后的代码语法正确，无缩进/语法错误
3. [ ] 修复操作有明确依据（错误信息 + 源码定位）
4. [ ] .bak 备份文件已生成（--backup=true 时）
5. [ ] 重跑验证通过（--verify=true 时）
6. [ ] repair_log.md 已记录本次修复操作
