# 代码模板参考

## 一、API 层封装模板

### 标准 GET 请求（无参数）

```python
"""
{module_name}接口封装
- 接口路径：{api_path}
- 请求方法：GET
"""
from config.config import BASE_URL
from utils.request_util import RequestUtil
from utils.token_util import TokenUtil
from utils.logger import get_logger

logger = get_logger("{module_name}_api")


class {ClassName}API:
    """{api_name}接口封装"""

    def __init__(self, request_util=None):
        self.request_util = request_util or RequestUtil()
        self.base_url = BASE_URL

    def {method_name}(self, headers=None):
        """
        {api_name}
        - 接口路径：{api_path}
        - 请求方法：GET
        """
        url = self.base_url + "{api_path}"
        _headers = headers or TokenUtil.get_headers(self.request_util)
        response = self.request_util.get(url, headers=_headers)
        logger.info(f"{api_name} | status={response.status_code}")
        return response
```

### GET 请求（Query 参数 + Path 参数）

```python
class UserAPI:
    """用户接口封装"""

    def __init__(self, request_util=None):
        self.request_util = request_util or RequestUtil()
        self.base_url = BASE_URL

    def get_user_list(self, page=None, size=None, keyword=None, headers=None):
        """
        获取用户列表
        - 接口路径：/api/v1/users
        - 请求方法：GET
        :param page: 页码
        :param size: 每页条数
        :param keyword: 搜索关键词
        :param headers: 自定义请求头
        """
        url = self.base_url + "/api/v1/users"
        _headers = headers or TokenUtil.get_headers(self.request_util)
        params = {}
        if page is not None:
            params["page"] = page
        if size is not None:
            params["size"] = size
        if keyword is not None:
            params["keyword"] = keyword
        response = self.request_util.get(url, headers=_headers, params=params)
        logger.info(f"获取用户列表 | status={response.status_code}")
        return response

    def get_user_info(self, user_id, headers=None):
        """
        获取用户详情
        - 接口路径：/api/v1/users/{user_id}
        - 请求方法：GET
        :param user_id: 用户ID
        :param headers: 自定义请求头
        """
        url = self.base_url + f"/api/v1/users/{user_id}"
        _headers = headers or TokenUtil.get_headers(self.request_util)
        response = self.request_util.get(url, headers=_headers)
        logger.info(f"获取用户详情 | status={response.status_code}")
        return response
```

### POST 请求（Body 参数）

```python
class AuthAPI:
    """认证接口封装"""

    def __init__(self, request_util=None):
        self.request_util = request_util or RequestUtil()
        self.base_url = BASE_URL

    def login(self, username, password, captcha_key=None, captcha_code=None, headers=None):
        """
        用户登录
        - 接口路径：/api/auth/login
        - 请求方法：POST
        :param username: 用户名
        :param password: 密码
        :param captcha_key: 验证码Key
        :param captcha_code: 验证码
        :param headers: 自定义请求头
        """
        url = self.base_url + "/api/auth/login"
        _headers = headers or {"Content-Type": "application/json"}
        json_data = {
            "username": username,
            "password": password,
        }
        if captcha_key is not None:
            json_data["captchaKey"] = captcha_key
        if captcha_code is not None:
            json_data["captchaCode"] = captcha_code
        response = self.request_util.post(url, headers=_headers, json=json_data)
        logger.info(f"用户登录 | status={response.status_code}")
        return response

    def register(self, username, password, email, phone, headers=None):
        """
        用户注册
        - 接口路径：/api/auth/register
        - 请求方法：POST
        :param username: 用户名
        :param password: 密码
        :param email: 邮箱
        :param phone: 手机号
        :param headers: 自定义请求头
        """
        url = self.base_url + "/api/auth/register"
        _headers = headers or {"Content-Type": "application/json"}
        json_data = {
            "username": username,
            "password": password,
            "email": email,
            "phone": phone,
        }
        response = self.request_util.post(url, headers=_headers, json=json_data)
        logger.info(f"用户注册 | status={response.status_code}")
        return response
```

### PUT 请求

```python
class UserAPI:
    """用户接口封装"""

    def update_user(self, user_id, username=None, email=None, phone=None, headers=None):
        """
        更新用户信息
        - 接口路径：/api/v1/users/{user_id}
        - 请求方法：PUT
        :param user_id: 用户ID
        :param username: 用户名
        :param email: 邮箱
        :param phone: 手机号
        :param headers: 自定义请求头
        """
        url = self.base_url + f"/api/v1/users/{user_id}"
        _headers = headers or TokenUtil.get_headers(self.request_util)
        json_data = {}
        if username is not None:
            json_data["username"] = username
        if email is not None:
            json_data["email"] = email
        if phone is not None:
            json_data["phone"] = phone
        response = self.request_util.put(url, headers=_headers, json=json_data)
        logger.info(f"更新用户信息 | status={response.status_code}")
        return response
```

### DELETE 请求

```python
class OrderAPI:
    """订单接口封装"""

    def delete_order(self, order_id, headers=None):
        """
        删除订单
        - 接口路径：/api/v1/orders/{order_id}
        - 请求方法：DELETE
        :param order_id: 订单ID
        :param headers: 自定义请求头
        """
        url = self.base_url + f"/api/v1/orders/{order_id}"
        _headers = headers or TokenUtil.get_headers(self.request_util)
        response = self.request_util.delete(url, headers=_headers)
        logger.info(f"删除订单 | status={response.status_code}")
        return response
```

## 二、数据驱动用例模板

### 完整四场景分类

```python
"""
{api_name}测试用例
- 接口路径：{api_path}
- 请求方法：{method}
"""
import pytest
import allure
import yaml
import os
from api.{module}_api import {ClassName}API
from utils.assert_util import AssertUtil
from utils.logger import get_logger

logger = get_logger("test_{module}_{api}")


def load_test_data(data_file):
    """加载 YAML 测试数据"""
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", data_file
    )
    with open(data_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# 加载测试数据
TEST_DATA = load_test_data("{module}/{api}_data.yaml")


class Test{ClassName}Normal:
    """{api_name} - 正向场景"""

    def setup_class(self):
        self.api = {ClassName}API()

    @pytest.mark.p0
    @pytest.mark.smoke
    @allure.title("{api_name} - 正常请求成功")
    @allure.feature("{module_name}")
    @allure.story("正向场景")
    def test_{method_name}_success(self, request_util, auth_headers):
        """测试正常请求成功"""
        self.api.request_util = request_util
        response = self.api.{method_name}(
            {params_with_defaults},
            headers=auth_headers
        )
        AssertUtil.assert_all(
            response,
            expected_status=200,
            expected_code=0,
            field_checks=[
                {field_check_items}
            ]
        )


class Test{ClassName}Exception:
    """{api_name} - 异常场景"""

    def setup_class(self):
        self.api = {ClassName}API()

    @pytest.mark.p0
    @allure.title("{api_name} - 数据驱动异常测试")
    @allure.feature("{module_name}")
    @allure.story("异常场景")
    @pytest.mark.parametrize(
        "case",
        [c for c in TEST_DATA["test_cases"] if c["category"] == "negative"],
        ids=[c["case_id"] for c in TEST_DATA["test_cases"] if c["category"] == "negative"]
    )
    def test_{method_name}_negative(self, case, request_util, auth_headers):
        """数据驱动异常测试"""
        self.api.request_util = request_util
        {build_params_from_case}
        response = self.api.{method_name}(
            {params_from_case},
            headers=auth_headers
        )
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])
        if "business_code" in case["expected"]:
            AssertUtil.assert_business_code(response, case["expected"]["business_code"])


class Test{ClassName}Boundary:
    """{api_name} - 边界场景"""

    def setup_class(self):
        self.api = {ClassName}API()

    @pytest.mark.p1
    @allure.title("{api_name} - 数据驱动边界测试")
    @allure.feature("{module_name}")
    @allure.story("边界场景")
    @pytest.mark.parametrize(
        "case",
        [c for c in TEST_DATA["test_cases"] if c["category"] == "boundary"],
        ids=[c["case_id"] for c in TEST_DATA["test_cases"] if c["category"] == "boundary"]
    )
    def test_{method_name}_boundary(self, case, request_util, auth_headers):
        """数据驱动边界测试"""
        self.api.request_util = request_util
        {build_params_from_case}
        response = self.api.{method_name}(
            {params_from_case},
            headers=auth_headers
        )
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])


class Test{ClassName}Security:
    """{api_name} - 安全场景"""

    def setup_class(self):
        self.api = {ClassName}API()

    @pytest.mark.p1
    @allure.title("{api_name} - 数据驱动安全测试")
    @allure.feature("{module_name}")
    @allure.story("安全场景")
    @pytest.mark.parametrize(
        "case",
        [c for c in TEST_DATA["test_cases"] if c["category"] == "security"],
        ids=[c["case_id"] for c in TEST_DATA["test_cases"] if c["category"] == "security"]
    )
    def test_{method_name}_security(self, case, request_util, auth_headers):
        """数据驱动安全测试"""
        self.api.request_util = request_util
        {build_params_from_case}
        response = self.api.{method_name}(
            {params_from_case},
            headers=auth_headers
        )
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])
        if "business_code" in case["expected"]:
            AssertUtil.assert_business_code(response, case["expected"]["business_code"])
```

## 三、内联数据用例模板

### 简化版（无外部数据文件）

```python
"""
{api_name}测试用例（内联数据模式）
- 接口路径：{api_path}
- 请求方法：{method}
"""
import pytest
import allure
from api.{module}_api import {ClassName}API
from utils.assert_util import AssertUtil
from utils.logger import get_logger

logger = get_logger("test_{module}_{api}")

# 内联测试数据
TEST_DATA = {
    "positive": [
        {
            "name": "正常请求",
            "params": {
                {default_params}
            },
            "expected": {
                "status_code": 200,
                "business_code": 0
            }
        }
    ],
    "negative": [
        {
            "name": "必填参数为空",
            "params": {
                {empty_required_params}
            },
            "expected": {
                "status_code": 400,
                "business_code": 40001
            }
        },
        {
            "name": "参数类型错误",
            "params": {
                {type_mismatch_params}
            },
            "expected": {
                "status_code": 400
            }
        }
    ]
}


class Test{ClassName}Normal:
    """{api_name} - 正向场景"""

    def setup_class(self):
        self.api = {ClassName}API()

    @pytest.mark.p0
    @allure.title("{api_name} - 正常请求")
    @allure.feature("{module_name}")
    @allure.story("正向场景")
    def test_{method_name}_success(self, request_util, auth_headers):
        """测试正常请求"""
        self.api.request_util = request_util
        case = TEST_DATA["positive"][0]
        response = self.api.{method_name}(
            **case["params"],
            headers=auth_headers
        )
        AssertUtil.assert_all(
            response,
            expected_status=case["expected"]["status_code"],
            expected_code=case["expected"].get("business_code"),
            field_checks=[
                {field_check_items}
            ]
        )


class Test{ClassName}Exception:
    """{api_name} - 异常场景"""

    def setup_class(self):
        self.api = {ClassName}API()

    @pytest.mark.p0
    @pytest.mark.parametrize("case", TEST_DATA["negative"],
        ids=[c["name"] for c in TEST_DATA["negative"]])
    @allure.title("{api_name} - 异常测试")
    @allure.feature("{module_name}")
    @allure.story("异常场景")
    def test_{method_name}_negative(self, case, request_util, auth_headers):
        """测试异常场景"""
        self.api.request_util = request_util
        response = self.api.{method_name}(
            **case["params"],
            headers=auth_headers
        )
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])
        if "business_code" in case["expected"]:
            AssertUtil.assert_business_code(response, case["expected"]["business_code"])
```

## 四、数据加载工具模板

### load_test_data 通用函数

```python
import yaml
import json
import os


def load_test_data(data_file):
    """
    加载测试数据文件
    :param data_file: 相对于 data/ 目录的文件路径
    :return: 解析后的数据
    """
    data_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data"
    )
    file_path = os.path.join(data_dir, data_file)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"测试数据文件不存在: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        if file_path.endswith(".yaml") or file_path.endswith(".yml"):
            return yaml.safe_load(f)
        elif file_path.endswith(".json"):
            return json.load(f)
        else:
            raise ValueError(f"不支持的数据文件格式: {file_path}")


def resolve_dependencies(data, context=None):
    """
    解析测试数据中的依赖变量
    :param data: 测试数据字典
    :param context: 上下文变量字典
    :return: 解析后的数据

    支持 ${VARIABLE_NAME} 格式的变量替换
    """
    if context is None:
        context = {}

    import re

    def replace_vars(obj):
        if isinstance(obj, str):
            pattern = r"\$\{(\w+)\}"
            matches = re.findall(pattern, obj)
            for match in matches:
                if match in context:
                    obj = obj.replace(f"${{{match}}}", str(context[match]))
            return obj
        elif isinstance(obj, dict):
            return {k: replace_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [replace_vars(item) for item in obj]
        return obj

    return replace_vars(data)
```

## 五、模块级 `__init__.py` 模板

### api/__init__.py

```python
"""
接口请求层
- 所有接口封装统一存放于此
- 一个接口对应一个文件
"""
```

### testcases/__init__.py

```python
"""
测试用例层
- 所有测试用例统一存放于此
- 一个接口对应一个测试文件
"""
```

### utils/__init__.py

```python
"""
工具类
- 日志、请求、断言、鉴权等通用逻辑
- 公共方法统一封装，禁止在用例中重复编写
"""
```

## 六、参数构建逻辑模板

### 从测试数据构建请求参数

```python
def build_request_params(case, param_mapping):
    """
    从测试数据用例构建请求参数
    :param case: 测试数据用例字典
    :param param_mapping: 参数映射 {方法参数名: 数据字段名}
    :return: 请求参数字典
    """
    params = {}
    case_params = case.get("parameters", {})

    # Body 参数
    body_params = case_params.get("body_params", {})
    for method_param, data_field in param_mapping.items():
        if data_field in body_params:
            params[method_param] = body_params[data_field]

    # Query 参数
    query_params = case_params.get("query_params", {})
    for method_param, data_field in param_mapping.items():
        if data_field in query_params:
            params[method_param] = query_params[data_field]

    # Path 参数
    path_params = case_params.get("path_params", {})
    for method_param, data_field in param_mapping.items():
        if data_field in path_params:
            params[method_param] = path_params[data_field]

    return params
```

### 依赖变量替换逻辑

```python
import re


def resolve_variable(value, context):
    """
    替换 ${VARIABLE_NAME} 格式的依赖变量
    :param value: 原始值
    :param context: 上下文变量字典
    :return: 替换后的值
    """
    if isinstance(value, str):
        pattern = r"\$\{(\w+)\}"
        matches = re.findall(pattern, value)
        for match in matches:
            if match in context:
                value = value.replace(f"${{{match}}}", str(context[match]))
        return value
    elif isinstance(value, dict):
        return {k: resolve_variable(v, context) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_variable(item, context) for item in value]
    return value
```

## 七、完整示例

### 用户登录接口 - API 层

```python
"""
认证接口封装
- 接口路径：/api/auth/login
- 请求方法：POST
"""
from config.config import BASE_URL
from utils.request_util import RequestUtil
from utils.token_util import TokenUtil
from utils.logger import get_logger

logger = get_logger("auth_api")


class AuthAPI:
    """认证接口封装"""

    def __init__(self, request_util=None):
        self.request_util = request_util or RequestUtil()
        self.base_url = BASE_URL

    def login(self, username, password, captcha_key=None, captcha_code=None, headers=None):
        """
        用户登录
        - 接口路径：/api/auth/login
        - 请求方法：POST
        :param username: 用户名（必填，3-50位字母数字下划线）
        :param password: 密码（必填，8-50位）
        :param captcha_key: 验证码Key（选填）
        :param captcha_code: 验证码（选填）
        :param headers: 自定义请求头
        """
        url = self.base_url + "/api/auth/login"
        _headers = headers or {"Content-Type": "application/json"}
        json_data = {
            "username": username,
            "password": password,
        }
        if captcha_key is not None:
            json_data["captchaKey"] = captcha_key
        if captcha_code is not None:
            json_data["captchaCode"] = captcha_code
        response = self.request_util.post(url, headers=_headers, json=json_data)
        logger.info(f"用户登录 | status={response.status_code}")
        return response
```

### 用户登录接口 - 用例层（数据驱动）

```python
"""
用户登录测试用例
- 接口路径：/api/auth/login
- 请求方法：POST
"""
import pytest
import allure
import yaml
import os
from api.auth_api import AuthAPI
from utils.assert_util import AssertUtil
from utils.logger import get_logger

logger = get_logger("test_auth_login")


def load_test_data(data_file):
    """加载 YAML 测试数据"""
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", data_file
    )
    with open(data_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


TEST_DATA = load_test_data("auth/user_login_data.yaml")


class TestAuthLoginNormal:
    """用户登录 - 正向场景"""

    def setup_class(self):
        self.api = AuthAPI()

    @pytest.mark.p0
    @pytest.mark.smoke
    @allure.title("用户登录 - 正常登录成功")
    @allure.feature("认证管理")
    @allure.story("正向场景")
    def test_login_success(self, request_util):
        """测试正常登录成功"""
        self.api.request_util = request_util
        response = self.api.login(
            username="testuser01",
            password="Test@1234"
        )
        AssertUtil.assert_all(
            response,
            expected_status=200,
            expected_code=0,
            field_checks=[
                {"field": "data.token", "check": "not_empty"},
                {"field": "data.username", "check": "equals", "expect": "testuser01"},
            ]
        )


class TestAuthLoginException:
    """用户登录 - 异常场景"""

    def setup_class(self):
        self.api = AuthAPI()

    @pytest.mark.p0
    @pytest.mark.parametrize(
        "case",
        [c for c in TEST_DATA["test_cases"] if c["category"] == "negative"],
        ids=[c["case_id"] for c in TEST_DATA["test_cases"] if c["category"] == "negative"]
    )
    @allure.title("用户登录 - 异常测试")
    @allure.feature("认证管理")
    @allure.story("异常场景")
    def test_login_negative(self, case, request_util):
        """数据驱动异常测试"""
        self.api.request_util = request_util
        body = case["parameters"].get("body_params", {})
        response = self.api.login(
            username=body.get("username", ""),
            password=body.get("password", "")
        )
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])
        if "business_code" in case["expected"]:
            AssertUtil.assert_business_code(response, case["expected"]["business_code"])


class TestAuthLoginBoundary:
    """用户登录 - 边界场景"""

    def setup_class(self):
        self.api = AuthAPI()

    @pytest.mark.p1
    @pytest.mark.parametrize(
        "case",
        [c for c in TEST_DATA["test_cases"] if c["category"] == "boundary"],
        ids=[c["case_id"] for c in TEST_DATA["test_cases"] if c["category"] == "boundary"]
    )
    @allure.title("用户登录 - 边界测试")
    @allure.feature("认证管理")
    @allure.story("边界场景")
    def test_login_boundary(self, case, request_util):
        """数据驱动边界测试"""
        self.api.request_util = request_util
        body = case["parameters"].get("body_params", {})
        response = self.api.login(
            username=body.get("username", ""),
            password=body.get("password", "")
        )
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])


class TestAuthLoginSecurity:
    """用户登录 - 安全场景"""

    def setup_class(self):
        self.api = AuthAPI()

    @pytest.mark.p1
    @pytest.mark.parametrize(
        "case",
        [c for c in TEST_DATA["test_cases"] if c["category"] == "security"],
        ids=[c["case_id"] for c in TEST_DATA["test_cases"] if c["category"] == "security"]
    )
    @allure.title("用户登录 - 安全测试")
    @allure.feature("认证管理")
    @allure.story("安全场景")
    def test_login_security(self, case, request_util):
        """数据驱动安全测试"""
        self.api.request_util = request_util
        body = case["parameters"].get("body_params", {})
        response = self.api.login(
            username=body.get("username", ""),
            password=body.get("password", "")
        )
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])
        if "business_code" in case["expected"]:
            AssertUtil.assert_business_code(response, case["expected"]["business_code"])
```
