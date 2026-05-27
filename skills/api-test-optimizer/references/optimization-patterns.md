# 自动优化策略与代码修复模式

本文档定义了 api-test-optimizer 执行自动优化时的具体策略和代码修复模式，包含常见问题与修复方案、代码精简模式和场景补齐模板。

---

## 一、语法修复模式

### 1.1 缩进修复

**问题**：Tab 与空格混用、缩进层级不一致

**修复策略**：统一为4空格缩进

```python
# 修复前（Tab缩进）
def test_login(self):
→   api = UserAPI()
→   response = api.login(username="test")
→   →   if response.status_code == 200:
→   →   →   assert True  # 无效断言

# 修复后（4空格缩进）
def test_login(self):
    api = UserAPI()
    response = api.login(username="test")
    if response.status_code == 200:
        # [优化器修复] 替换无效断言为三层断言
        AssertUtil.assert_status_code(response, 200)
        AssertUtil.assert_business_code(response, 0)
```

### 1.2 缺失符号修复

**问题**：缺少冒号、括号不匹配、引号未闭合

**修复策略**：根据上下文补全缺失符号

```python
# 修复前
class TestUserLogin  # 缺少冒号
    def test_login_success(self)  # 缺少冒号
        response = api.login(username="test"  # 缺少右括号

# 修复后
class TestUserLogin:  # [优化器修复] 补全冒号
    def test_login_success(self):  # [优化器修复] 补全冒号
        response = api.login(username="test")  # [优化器修复] 补全括号
```

### 1.3 导入修复

**问题**：使用了未导入的模块或类

**修复策略**：分析引用链，自动补充 import 语句

```python
# 修复前
def test_login(self, request_util, auth_headers):
    api = UserAPI(request_util)  # UserAPI 未导入
    response = api.login(username="test", headers=auth_headers)
    AssertUtil.assert_status_code(response, 200)  # AssertUtil 未导入

# 修复后
# [优化器修复] 补充缺失的导入
from api.user_api import UserAPI
from utils.assert_util import AssertUtil

def test_login(self, request_util, auth_headers):
    api = UserAPI(request_util)
    response = api.login(username="test", headers=auth_headers)
    AssertUtil.assert_status_code(response, 200)
```

### 1.4 变量未定义修复

**问题**：使用了未定义的变量

**修复策略**：分析上下文补充变量定义或从 fixture 注入

```python
# 修复前
def test_login(self):
    response = api.login(username="test")  # api 未定义
    assert response.status_code == 200

# 修复后
def test_login(self, request_util, auth_headers):  # [优化器修复] 注入 fixture
    api = UserAPI(request_util)  # [优化器修复] 初始化 API 实例
    response = api.login(username="test", headers=auth_headers)
    assert response.status_code == 200
```

---

## 二、规范对齐模式

### 2.1 命名重命名

**问题**：类名、方法名、变量名不符合命名规范

**修复策略**：自动重命名，保持全局引用一致

| 类型 | 修复前 | 修复后 | 规则 |
|------|--------|--------|------|
| 类名 | `userApi` | `UserAPI` | 大驼峰 |
| 方法名 | `Login` / `get_User` | `login` / `get_user` | 小写+下划线 |
| 变量名 | `userName` | `user_name` | 小写+下划线 |
| 常量名 | `base_url` | `BASE_URL` | 全大写+下划线 |
| 测试方法 | `check_login` | `test_login` | test_ 前缀 |
| 测试类 | `testUserLogin` | `TestUserLogin` | Test+大驼峰 |
| 场景类 | `TestLogin` | `TestUserLoginNormal` | Test+接口名+场景 |

### 2.2 注释生成

**问题**：缺少模块/类/方法级 docstring

**修复策略**：根据代码上下文自动生成

```python
# 修复前
import pytest
from api.user_api import UserAPI

class TestUserLogin:
    def test_login_success(self, request_util, auth_headers):
        api = UserAPI(request_util)
        response = api.login(username="test", headers=auth_headers)
        assert response.status_code == 200

# 修复后
"""
用户登录测试用例
- 接口路径：/api/auth/login
- 请求方法：POST
"""  # [优化器对齐] 补充模块 docstring
import pytest
import allure  # [优化器对齐] 补充缺失的导入
from api.user_api import UserAPI
from utils.assert_util import AssertUtil  # [优化器对齐] 补充缺失的导入

class TestUserLoginNormal:  # [优化器对齐] 类名规范+场景后缀
    """用户登录 - 正向场景"""  # [优化器对齐] 补充类 docstring

    @pytest.mark.p0  # [优化器对齐] 补充优先级标记
    @allure.title("用户登录 - 正常请求")  # [优化器对齐] 补充 Allure 标题
    @allure.feature("认证管理")  # [优化器对齐] 补充 Allure feature
    @allure.story("正向场景")  # [优化器对齐] 补充 Allure story
    def test_login_success(self, request_util, auth_headers):
        """测试正常登录"""  # [优化器对齐] 补充方法 docstring
        api = UserAPI(request_util)
        response = api.login(username="test", headers=auth_headers)
        # [优化器对齐] 补充三层断言
        AssertUtil.assert_all(
            response,
            expected_status=200,
            expected_code=0,
            field_checks=[
                {"field": "data.token", "check": "not_empty"},
            ]
        )
```

### 2.3 硬编码提取

**问题**：URL、超时、重试次数等硬编码在代码中

**修复策略**：提取为配置常量引用

```python
# 修复前
class UserAPI:
    def login(self, username, password):
        url = "https://test-api.example.com/api/auth/login"  # 硬编码
        response = requests.post(url, json={"username": username}, timeout=30)  # 硬编码
        return response

# 修复后
from config.config import BASE_URL, TIMEOUT  # [优化器对齐] 引入配置常量
from utils.request_util import RequestUtil  # [优化器对齐] 使用统一请求工具
from utils.token_util import TokenUtil

class UserAPI:
    def login(self, username, password, headers=None):
        url = BASE_URL + "/api/auth/login"  # [优化器对齐] 替换硬编码URL
        _headers = headers or TokenUtil.get_headers()  # [优化器对齐] 注入鉴权
        response = self.request_util.post(url, json={"username": username, "password": password}, headers=_headers)
        # [优化器对齐] 超时和重试由 RequestUtil 统一处理
        return response
```

### 2.4 Allure 标记补充

**问题**：测试用例缺少 Allure 装饰器

**修复策略**：根据接口和场景自动补充

```python
# 修复前
def test_login_success(self, request_util, auth_headers):
    ...

# 修复后
@pytest.mark.p0  # [优化器对齐] 补充优先级
@allure.title("用户登录 - 正常请求")  # [优化器对齐] 补充标题
@allure.feature("认证管理")  # [优化器对齐] 补充特性
@allure.story("正向场景")  # [优化器对齐] 补充故事
def test_login_success(self, request_util, auth_headers):
    ...
```

---

## 三、健壮性增强模式

### 3.1 异常捕获注入

**问题**：请求代码无 try/except

**修复策略**：替换为使用 RequestUtil（已内置统一异常捕获）

```python
# 修复前（裸 requests 调用）
import requests

class UserAPI:
    def login(self, username, password):
        url = "https://api.example.com/login"
        response = requests.post(url, json={"username": username, "password": password})
        return response

# 修复后（使用统一 RequestUtil）
from config.config import BASE_URL
from utils.request_util import RequestUtil
from utils.token_util import TokenUtil

class UserAPI:  # [优化器对齐] 类名大驼峰
    """用户登录接口封装"""  # [优化器对齐] 补充 docstring

    def __init__(self, request_util=None):
        self.request_util = request_util or RequestUtil()  # [优化器修复] 注入 RequestUtil
        self.base_url = BASE_URL

    def login(self, username, password, headers=None):
        """
        用户登录
        - 接口路径：/api/auth/login
        - 请求方法：POST
        """  # [优化器对齐] 补充方法 docstring
        url = self.base_url + "/api/auth/login"
        _headers = headers or TokenUtil.get_headers(self.request_util)  # [优化器修复] 注入鉴权
        json_data = {"username": username, "password": password}
        # [优化器修复] 使用统一请求工具（内置超时+重试+异常捕获）
        response = self.request_util.post(url, headers=_headers, json=json_data)
        return response
```

### 3.2 超时注入

**问题**：请求无超时配置

**修复策略**：注入统一超时常量

```python
# 修复前
response = requests.get(url)

# 修复后
response = self.request_util.get(url)  # [优化器修复] 使用 RequestUtil，自动带 timeout=TIMEOUT
```

### 3.3 鉴权注入

**问题**：需鉴权接口未注入 Token

**修复策略**：注入 TokenUtil.get_headers()

```python
# 修复前
def get_user_info(self, user_id):
    url = BASE_URL + f"/api/users/{user_id}"
    response = self.request_util.get(url)
    return response

# 修复后
def get_user_info(self, user_id, headers=None):
    url = BASE_URL + f"/api/users/{user_id}"
    _headers = headers or TokenUtil.get_headers(self.request_util)  # [优化器修复] 注入鉴权
    response = self.request_util.get(url, headers=_headers)
    return response
```

### 3.4 日志注入

**问题**：关键操作无日志记录

**修复策略**：注入 logger 调用

```python
# 修复前
def login(self, username, password, headers=None):
    url = self.base_url + "/api/auth/login"
    response = self.request_util.post(url, json={"username": username, "password": password}, headers=_headers)
    return response

# 修复后
from utils.logger import get_logger  # [优化器修复] 引入日志模块

logger = get_logger("user_api")

class UserAPI:
    def login(self, username, password, headers=None):
        url = self.base_url + "/api/auth/login"
        _headers = headers or TokenUtil.get_headers(self.request_util)
        logger.info(f"用户登录 | username={username}")  # [优化器修复] 注入请求日志
        response = self.request_util.post(url, json={"username": username, "password": password}, headers=_headers)
        logger.info(f"用户登录 | status={response.status_code}")  # [优化器修复] 注入响应日志
        return response
```

---

## 四、逻辑修复模式

### 4.1 三层断言补充

**问题**：只有状态码断言

**修复策略**：补充业务码断言和业务数据断言

```python
# 修复前
def test_login_success(self, request_util, auth_headers):
    api = UserAPI(request_util)
    response = api.login(username="test", password="Test@1234", headers=auth_headers)
    assert response.status_code == 200  # 仅状态码断言

# 修复后
def test_login_success(self, request_util, auth_headers):
    api = UserAPI(request_util)
    response = api.login(username="test", password="Test@1234", headers=auth_headers)
    # [优化器修复] 补充三层断言
    AssertUtil.assert_all(
        response,
        expected_status=200,
        expected_code=0,
        field_checks=[
            {"field": "data.token", "check": "not_empty"},
            {"field": "data.user_id", "check": "type", "expect": int},
            {"field": "data.username", "check": "equals", "expect": "test"},
        ]
    )
```

### 4.2 无效断言替换

**问题**：存在 assert True 或 assert 1==1 等无效断言

**修复策略**：替换为有效的三层断言

```python
# 修复前
def test_login_success(self, request_util, auth_headers):
    api = UserAPI(request_util)
    response = api.login(username="test", headers=auth_headers)
    assert True  # 无效断言

# 修复后
def test_login_success(self, request_util, auth_headers):
    api = UserAPI(request_util)
    response = api.login(username="test", headers=auth_headers)
    # [优化器修复] 替换无效断言为三层断言
    AssertUtil.assert_all(
        response,
        expected_status=200,
        expected_code=0,
        field_checks=[
            {"field": "data.token", "check": "not_empty"},
        ]
    )
```

### 4.3 路径参数替换修复

**问题**：URL 中的路径参数占位符未被替换

**修复策略**：注入替换逻辑

```python
# 修复前
def get_user_info(self, user_id, headers=None):
    url = self.base_url + "/api/users/{user_id}"  # 路径参数未替换
    response = self.request_util.get(url, headers=_headers)
    return response

# 修复后
def get_user_info(self, user_id, headers=None):
    url = self.base_url + "/api/users/{user_id}"
    url = url.replace("{user_id}", str(user_id))  # [优化器修复] 注入路径参数替换
    _headers = headers or TokenUtil.get_headers(self.request_util)
    response = self.request_util.get(url, headers=_headers)
    return response
```

### 4.4 接口依赖处理

**问题**：接口返回的数据未传递给后续用例

**修复策略**：通过 fixture 或类属性传递

```python
# 修复前（数据不传递）
def test_create_order(self, request_util, auth_headers):
    api = OrderAPI(request_util)
    response = api.create_order(product_id=1, headers=auth_headers)
    assert response.status_code == 200

def test_pay_order(self, request_util, auth_headers):
    api = OrderAPI(request_util)
    response = api.pay_order(order_id=???, headers=auth_headers)  # order_id 未传递
    assert response.status_code == 200

# 修复后（通过类属性传递）
class TestOrderFlow:
    """订单流程测试"""

    def setup_class(self):
        self.order_id = None  # [优化器修复] 添加类属性存储依赖数据

    def test_create_order(self, request_util, auth_headers):
        api = OrderAPI(request_util)
        response = api.create_order(product_id=1, headers=auth_headers)
        AssertUtil.assert_all(response, expected_status=200, expected_code=0)
        # [优化器修复] 保存依赖数据
        self.order_id = response.json()["data"]["order_id"]

    def test_pay_order(self, request_util, auth_headers):
        api = OrderAPI(request_util)
        # [优化器修复] 使用依赖数据
        assert self.order_id is not None, "前置订单创建失败，跳过支付测试"
        response = api.pay_order(order_id=self.order_id, headers=auth_headers)
        AssertUtil.assert_all(response, expected_status=200, expected_code=0)
```

---

## 五、代码精简模式

### 5.1 重复代码提取

**问题**：多个用例中有相同的初始化和断言代码

**修复策略**：提取公共方法到 utils/ 或使用 fixture

```python
# 修复前（重复代码）
class TestUserLoginNormal:
    def test_login_success(self, request_util, auth_headers):
        api = UserAPI(request_util)
        response = api.login(username="test", password="Test@1234", headers=auth_headers)
        AssertUtil.assert_all(response, expected_status=200, expected_code=0, ...)

    def test_login_with_phone(self, request_util, auth_headers):
        api = UserAPI(request_util)
        response = api.login(username="13800138000", password="Test@1234", headers=auth_headers)
        AssertUtil.assert_all(response, expected_status=200, expected_code=0, ...)

# 修复后（提取公共方法）
class TestUserLoginNormal:
    """用户登录 - 正向场景"""

    def setup_class(self):
        self.api = None

    def _init_api(self, request_util):
        """[优化器重构] 提取公共初始化"""
        if self.api is None:
            self.api = UserAPI(request_util)
        return self.api

    def _assert_login_success(self, response):
        """[优化器重构] 提取公共断言"""
        AssertUtil.assert_all(
            response,
            expected_status=200,
            expected_code=0,
            field_checks=[
                {"field": "data.token", "check": "not_empty"},
            ]
        )

    def test_login_success(self, request_util, auth_headers):
        api = self._init_api(request_util)
        response = api.login(username="test", password="Test@1234", headers=auth_headers)
        self._assert_login_success(response)

    def test_login_with_phone(self, request_util, auth_headers):
        api = self._init_api(request_util)
        response = api.login(username="13800138000", password="Test@1234", headers=auth_headers)
        self._assert_login_success(response)
```

### 5.2 死代码删除

**问题**：存在未被引用的变量和方法

**修复策略**：删除死代码

```python
# 修复前
def test_login(self, request_util, auth_headers):
    unused_var = "this is never used"  # 死代码
    api = UserAPI(request_util)
    debug_response = api.health_check()  # 调试代码，未被使用
    response = api.login(username="test", headers=auth_headers)
    AssertUtil.assert_status_code(response, 200)

# 修复后
def test_login(self, request_util, auth_headers):
    # [优化器重构] 删除未使用的变量和调试代码
    api = UserAPI(request_util)
    response = api.login(username="test", headers=auth_headers)
    AssertUtil.assert_status_code(response, 200)
```

### 5.3 魔法数字提取

**问题**：代码中存在魔法数字

**修复策略**：提取为命名常量

```python
# 修复前
def test_login(self, request_util, auth_headers):
    api = UserAPI(request_util)
    response = api.login(username="test", headers=auth_headers)
    assert response.status_code == 200  # 魔法数字
    assert response.json()["code"] == 0  # 魔法数字

# 修复后
HTTP_OK = 200  # [优化器重构] 提取魔法数字
BIZ_SUCCESS = 0  # [优化器重构] 提取魔法数字

def test_login(self, request_util, auth_headers):
    api = UserAPI(request_util)
    response = api.login(username="test", headers=auth_headers)
    AssertUtil.assert_status_code(response, HTTP_OK)
    AssertUtil.assert_business_code(response, BIZ_SUCCESS)
```

---

## 六、场景补齐模板

### 6.1 单接口场景补齐模板

对一个接口，按10维度生成完整的补齐用例类：

```python
"""
{api_name}测试用例（优化器补齐版）
- 接口路径：{api_path}
- 请求方法：{method}
- 补齐维度：D1-D10
"""
import pytest
import allure
from api.{module}_api import {ClassName}API
from utils.assert_util import AssertUtil
from utils.logger import get_logger

logger = get_logger("test_{module}_{api}")


class Test{ClassName}Normal:
    """{api_name} - 正向场景"""

    def setup_class(self):
        self.api = None

    def _init_api(self, request_util):
        if self.api is None:
            self.api = {ClassName}API(request_util)
        return self.api

    @pytest.mark.p0
    @allure.title("{api_name} - 正常请求")
    @allure.feature("{module_name}")
    @allure.story("正向场景")
    def test_{method_name}_success(self, request_util, auth_headers):
        """测试正常请求"""
        api = self._init_api(request_util)
        response = api.{method_name}({default_params}, headers=auth_headers)
        AssertUtil.assert_all(
            response,
            expected_status=200,
            expected_code=0,
            field_checks=[{field_check_items}]
        )


# ===== [优化器补齐] D2-必填校验 =====
class Test{ClassName}Required:
    """{api_name} - 必填校验"""

    def setup_class(self):
        self.api = None

    def _init_api(self, request_util):
        if self.api is None:
            self.api = {ClassName}API(request_util)
        return self.api

    @pytest.mark.p0
    @allure.title("{api_name} - 必填参数为空")
    @allure.feature("{module_name}")
    @allure.story("必填校验")
    @pytest.mark.parametrize("param_name,invalid_value", [
        ("{param1}", ""),
        ("{param1}", None),
        ("{param2}", ""),
        ("{param2}", None),
    ])
    def test_{method_name}_required_empty(self, param_name, invalid_value, request_util, auth_headers):
        """测试必填参数为空/None"""
        api = self._init_api(request_util)
        params = {default_params}
        params[param_name] = invalid_value
        response = api.{method_name}(**params, headers=auth_headers)
        AssertUtil.assert_status_code(response, 400)
        AssertUtil.assert_business_code(response, {error_code})


# ===== [优化器补齐] D3-参数合法性 =====
class Test{ClassName}Validation:
    """{api_name} - 参数合法性"""

    def setup_class(self):
        self.api = None

    def _init_api(self, request_util):
        if self.api is None:
            self.api = {ClassName}API(request_util)
        return self.api

    @pytest.mark.p0
    @allure.title("{api_name} - 参数类型不匹配")
    @allure.feature("{module_name}")
    @allure.story("参数合法性")
    def test_{method_name}_type_mismatch(self, request_util, auth_headers):
        """测试参数类型不匹配"""
        api = self._init_api(request_util)
        params = {default_params}
        params["{param_name}"] = {invalid_type_value}
        response = api.{method_name}(**params, headers=auth_headers)
        AssertUtil.assert_status_code(response, 400)


# ===== [优化器补齐] D4-边界值 =====
class Test{ClassName}Boundary:
    """{api_name} - 边界值"""

    def setup_class(self):
        self.api = None

    def _init_api(self, request_util):
        if self.api is None:
            self.api = {ClassName}API(request_util)
        return self.api

    @pytest.mark.p0
    @allure.title("{api_name} - 边界值测试")
    @allure.feature("{module_name}")
    @allure.story("边界值")
    @pytest.mark.parametrize("param_name,value,expected_status", [
        ("{param_name}", {min_value}, 200),
        ("{param_name}", {min_value_minus_1}, 400),
        ("{param_name}", {max_value}, 200),
        ("{param_name}", {max_value_plus_1}, 400),
        ("{param_name}", 0, 400),
        ("{param_name}", -1, 400),
    ])
    def test_{method_name}_boundary(self, param_name, value, expected_status, request_util, auth_headers):
        """测试参数边界值"""
        api = self._init_api(request_util)
        params = {default_params}
        params[param_name] = value
        response = api.{method_name}(**params, headers=auth_headers)
        AssertUtil.assert_status_code(response, expected_status)


# ===== [优化器补齐] D5-异常处理 =====
class Test{ClassName}Exception:
    """{api_name} - 异常处理"""

    def setup_class(self):
        self.api = None

    def _init_api(self, request_util):
        if self.api is None:
            self.api = {ClassName}API(request_util)
        return self.api

    @pytest.mark.p0
    @allure.title("{api_name} - 资源不存在")
    @allure.feature("{module_name}")
    @allure.story("异常处理")
    def test_{method_name}_not_found(self, request_util, auth_headers):
        """测试访问不存在的资源"""
        api = self._init_api(request_util)
        response = api.{method_name}({non_exist_params}, headers=auth_headers)
        AssertUtil.assert_all(
            response,
            expected_status=404,
            expected_code={not_found_code}
        )


# ===== [优化器补齐] D6-业务规则 =====
class Test{ClassName}BusinessRule:
    """{api_name} - 业务规则"""

    def setup_class(self):
        self.api = None

    def _init_api(self, request_util):
        if self.api is None:
            self.api = {ClassName}API(request_util)
        return self.api

    @pytest.mark.p0
    @allure.title("{api_name} - 业务规则违反")
    @allure.feature("{module_name}")
    @allure.story("业务规则")
    def test_{method_name}_{rule_name}(self, request_util, auth_headers):
        """测试业务规则：{business_rule}"""
        api = self._init_api(request_util)
        params = {default_params}
        {modify_params_to_violate_rule}
        response = api.{method_name}(**params, headers=auth_headers)
        AssertUtil.assert_business_code(response, {error_code})


# ===== [优化器补齐] D7-安全风险 =====
class Test{ClassName}Security:
    """{api_name} - 安全风险"""

    def setup_class(self):
        self.api = None

    def _init_api(self, request_util):
        if self.api is None:
            self.api = {ClassName}API(request_util)
        return self.api

    @pytest.mark.p0
    @allure.title("{api_name} - 无Token访问")
    @allure.feature("{module_name}")
    @allure.story("安全风险")
    def test_{method_name}_no_token(self, request_util):
        """测试无Token访问"""
        api = self._init_api(request_util)
        response = api.{method_name}({params}, headers={"Content-Type": "application/json"})
        AssertUtil.assert_status_code(response, 401)

    @pytest.mark.p1
    @allure.title("{api_name} - SQL注入")
    @allure.feature("{module_name}")
    @allure.story("安全风险")
    def test_{method_name}_sql_injection(self, request_util, auth_headers):
        """测试SQL注入"""
        api = self._init_api(request_util)
        params = {default_params}
        params["{param_name}"] = "' OR 1=1 --"
        response = api.{method_name}(**params, headers=auth_headers)
        AssertUtil.assert_status_code(response, 400)


# ===== [优化器补齐] D8-接口依赖 =====
class Test{ClassName}Dependency:
    """{api_name} - 接口依赖"""

    def setup_class(self):
        self.api = None

    def _init_api(self, request_util):
        if self.api is None:
            self.api = {ClassName}API(request_util)
        return self.api

    @pytest.mark.p1
    @allure.title("{api_name} - 前置依赖失败")
    @allure.feature("{module_name}")
    @allure.story("接口依赖")
    def test_{method_name}_dependency_failed(self, request_util, auth_headers):
        """测试前置依赖失败"""
        api = self._init_api(request_util)
        response = api.{method_name}({non_exist_dependency}, headers=auth_headers)
        AssertUtil.assert_status_code(response, 404)


# ===== [优化器补齐] D9-兼容性 =====
class Test{ClassName}Compatibility:
    """{api_name} - 兼容性"""

    def setup_class(self):
        self.api = None

    def _init_api(self, request_util):
        if self.api is None:
            self.api = {ClassName}API(request_util)
        return self.api

    @pytest.mark.p2
    @allure.title("{api_name} - 空结果集")
    @allure.feature("{module_name}")
    @allure.story("兼容性")
    def test_{method_name}_empty_result(self, request_util, auth_headers):
        """测试查询条件无匹配"""
        api = self._init_api(request_util)
        response = api.{method_name}({no_match_params}, headers=auth_headers)
        AssertUtil.assert_all(
            response,
            expected_status=200,
            expected_code=0,
            field_checks=[
                {"field": "data.list", "check": "length", "expect": 0},
            ]
        )
```

---

## 优化标识规范

所有自动修改和补齐的内容必须添加标识注释，便于 Code Review 追溯：

| 标识 | 格式 | 使用场景 |
|------|------|---------|
| `[优化器修复]` | `# [优化器修复] 修复说明` | 语法错误、无效断言、缺失导入等修复 |
| `[优化器补齐]` | `# [优化器补齐] D{N}-{维度名}` | 场景补齐的新增用例/代码 |
| `[优化器重构]` | `# [优化器重构] 重构说明` | 提取公共方法、删除死代码等重构 |
| `[优化器对齐]` | `# [优化器对齐] 对齐说明` | 命名规范、注释、Allure标记等对齐 |
