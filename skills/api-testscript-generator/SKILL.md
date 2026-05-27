---
name: api-testscript-generator
description: 接口自动化测试脚本批量生成技能。基于标准化接口定义（api_definitions.json）与可选的全场景测试数据文件，按照团队既定工程规范（Python + Requests + Pytest + Allure2），自动生成分层架构的接口自动化测试脚本。支持数据驱动模式（脚本与数据解耦）和内联数据模式，输出可直接运行的接口自动化脚本工程。
---

# API Test Script Generator - 接口自动化测试脚本批量生成

## 概述

本技能扮演接口自动化测试架构师角色，核心能力是基于标准化接口定义与可选测试数据，按照团队既定工程规范，批量生成分层架构、数据驱动、可直接运行的接口自动化测试脚本。

**两种数据模式：**

| 模式 | 输入 | 数据来源 | 适用场景 |
|------|------|---------|---------|
| 数据驱动模式 | `api_definitions.json` + 测试数据目录 | 外部 YAML/JSON 数据文件 | 团队规范、数据频繁变更、脚本与数据解耦 |
| 内联数据模式 | `api_definitions.json`（无测试数据目录） | 脚本内自动生成默认测试数据 | 快速验证、无测试数据文件、初期搭建 |

**分层架构：**

```
api_auto_project/
├── config/             # 环境配置、全局常量
├── api/                # 接口请求层（封装所有接口）
├── testcases/          # 测试用例层
├── data/               # 测试数据（数据驱动模式）
├── utils/              # 工具类
├── reports/            # 报告输出
├── conftest.py         # Pytest 全局钩子
└── pytest.ini          # Pytest 配置
```

## 触发条件

以下场景自动触发本技能：

- 用户提供 `api_definitions.json` 或 `api_definitions.yaml` 文件，要求生成接口自动化脚本
- 用户同时提供 `api_definitions.json` + 测试数据目录，要求按数据驱动方式生成脚本
- 用户要求"生成接口测试脚本""生成自动化脚本""接口自动化代码生成"
- 用户提及"api-testscript-generator""/api_testscript_generator"
- 用户需要将接口定义转化为可执行的 Pytest 自动化测试工程
- 用户需要基于 api-testdata-generator 的输出结果生成对应的测试脚本

## 输入

### 必需输入

1. **标准化接口定义文件**：由 `api-schema-parser` 输出的 `api_definitions.json/yaml`
   - 包含 `meta`、`apis`、`global_rules` 顶层结构
   - 每个接口含 `api_id`、`path`、`method`、`parameters`、`responses`、`business_rules`

### 可选输入

2. **全场景测试数据目录**：由 `api-testdata-generator` 输出的测试数据文件目录
   - 每个接口对应一个 YAML/JSON 数据文件
   - 数据文件包含 `test_cases` 列表，每条含 `case_id`、`name`、`category`、`parameters`、`expected`
   - 目录按模块分组织（如 `auth/`、`order/`）

3. **目标接口/模块筛选**（选填）：接口 api_id 或模块名称，仅生成指定范围的脚本

4. **自定义输出路径**（选填）：指定生成脚本的根目录，默认为当前目录下的 `api_auto_project/`

## 执行流程

```
输入（api_definitions.json + 可选测试数据目录）
        ↓
  Step 1: 读取接口结构与参数约束
        ↓
  Step 2: 识别数据模式（数据驱动 / 内联数据）
        ↓
  Step 3: 生成项目基础设施（config/、utils/、conftest.py、pytest.ini）
        ↓
  Step 4: 生成接口请求层（api/ 层封装）
        ↓
  Step 5: 生成测试数据层（data/ 层，数据驱动模式）
        ↓
  Step 6: 生成测试用例层（testcases/ 层）
        ↓
  Step 7: 注入健壮逻辑（超时、重试、异常捕获、日志）
        ↓
  Step 8: 输出校验与汇总
```

### Step 1: 读取接口结构与参数约束

从 `api_definitions.json` 中逐个读取接口定义，提取以下关键信息：

| 信息类型 | 来源字段 | 用途 |
|---------|---------|------|
| 接口路径 | `path` | 拼接请求 URL |
| 请求方法 | `method` | 确定请求类型（GET/POST/PUT/DELETE） |
| 路径参数 | `parameters.path_params` | URL 路径替换 |
| 查询参数 | `parameters.query_params` | 拼接 Query String |
| 请求头 | `parameters.header_params` | 构建 Headers |
| 请求体 | `parameters.body_params` | 构建 Request Body |
| 响应结构 | `responses.success` / `responses.errors` | 生成断言 |
| 业务规则 | `business_rules` | 鉴权、幂等等特殊处理 |
| 全局规则 | `global_rules` | 全局鉴权、限流等 |
| 模块归属 | `module` | 文件与目录组织 |

### Step 2: 识别数据模式

| 判定条件 | 数据模式 | 处理方式 |
|---------|---------|---------|
| 用户提供了测试数据目录，且目录下存在对应的 YAML/JSON 文件 | 数据驱动模式 | 将数据文件映射到 `data/` 层，用例层通过 `@pytest.mark.parametrize` 或 `yaml.safe_load()` 读取 |
| 用户未提供测试数据目录，或数据目录为空 | 内联数据模式 | 在 `testcases/` 层用例中直接构建测试数据字典，或生成简单的 `data/` 层默认数据 |

**数据文件匹配规则（数据驱动模式）：**

| 测试数据目录结构 | 对应接口 | 匹配方式 |
|----------------|---------|---------|
| `auth/user_login.yaml` | `POST_/api/auth/login` | 按模块/文件名映射 |
| `order/create_order.yaml` | `POST_/api/order/create` | 按模块/文件名映射 |

匹配策略：优先按 `api_id` 精确匹配，其次按接口名称模糊匹配，最后按模块+路径推断。

### Step 3: 生成项目基础设施

#### 3.1 config/ 环境配置

**config/config.py**：

```python
"""
全局配置模块
- 环境切换：dev/test/pre/prod
- 读取对应环境配置文件
"""
import os
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENV = os.getenv("API_TEST_ENV", "test")

def load_config():
    """加载环境配置"""
    config_path = os.path.join(BASE_DIR, "config", f"{ENV}.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

CONFIG = load_config()

# 全局常量
BASE_URL = CONFIG.get("base_url", "")
TIMEOUT = CONFIG.get("timeout", 30)
MAX_RETRY = CONFIG.get("max_retry", 2)
CONTENT_TYPE = "application/json"
```

**config/dev.yaml** / **config/test.yaml**：

```yaml
# test.yaml 示例
base_url: "https://test-api.example.com"
timeout: 30
max_retry: 2

auth:
  login_url: "/api/auth/login"
  username: "testuser"
  password: "Test@1234"

database:
  host: "test-db.example.com"
  port: 3306
  name: "test_db"
```

#### 3.2 utils/ 工具类

**utils/logger.py**：

```python
"""
统一日志模块
- 格式：时间 - 级别 - 模块 - 信息
- 请求/响应自动打印
"""
import logging
import os

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def get_logger(name):
    """获取 Logger 实例"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        )
        # 控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        # 文件输出
        file_handler = logging.FileHandler(
            os.path.join(LOG_DIR, f"{name}.log"), encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger
```

**utils/request_util.py**：

```python
"""
统一请求工具类
- 超时统一 30s
- 失败自动重试 2 次
- 异常捕获（连接超时/读取超时/连接错误/代理异常/数据解析异常）
- 请求/响应自动日志
- Allure 步骤记录
"""
import allure
import requests
from requests.exceptions import (
    ConnectionError,
    ProxyError,
    ReadTimeout,
    ConnectTimeout,
    JSONDecodeError,
)
from utils.logger import get_logger
from config.config import TIMEOUT, MAX_RETRY

logger = get_logger("request_util")

class RequestUtil:
    """统一请求封装"""

    def __init__(self, session=None):
        self.session = session or requests.Session()

    def _retry_request(self, method, url, **kwargs):
        """带重试的请求方法"""
        kwargs.setdefault("timeout", TIMEOUT)
        last_exception = None
        for attempt in range(1, MAX_RETRY + 2):  # 首次 + MAX_RETRY 次重试
            try:
                logger.info(f"[Request] {method} {url} | attempt={attempt}")
                response = self.session.request(method, url, **kwargs)
                logger.info(
                    f"[Response] status={response.status_code} | "
                    f"time={response.elapsed.total_seconds():.3f}s"
                )
                return response
            except (ConnectTimeout, ReadTimeout) as e:
                last_exception = e
                logger.warning(f"[Retry] Timeout on attempt {attempt}: {e}")
            except ConnectionError as e:
                last_exception = e
                logger.warning(f"[Retry] ConnectionError on attempt {attempt}: {e}")
            except ProxyError as e:
                last_exception = e
                logger.warning(f"[Retry] ProxyError on attempt {attempt}: {e}")
            except JSONDecodeError as e:
                last_exception = e
                logger.error(f"[Error] JSONDecodeError: {e}")
                raise
            except Exception as e:
                last_exception = e
                logger.error(f"[Error] Unexpected: {e}")
                raise
        raise last_exception

    @allure.step("GET {url}")
    def get(self, url, **kwargs):
        return self._retry_request("GET", url, **kwargs)

    @allure.step("POST {url}")
    def post(self, url, **kwargs):
        return self._retry_request("POST", url, **kwargs)

    @allure.step("PUT {url}")
    def put(self, url, **kwargs):
        return self._retry_request("PUT", url, **kwargs)

    @allure.step("DELETE {url}")
    def delete(self, url, **kwargs):
        return self._retry_request("DELETE", url, **kwargs)

    @allure.step("PATCH {url}")
    def patch(self, url, **kwargs):
        return self._retry_request("PATCH", url, **kwargs)
```

**utils/assert_util.py**：

```python
"""
统一断言工具类
- 三层断言：状态码 + 业务码 + 业务数据
- Allure 步骤记录
- 断言失败自动附加响应信息
"""
import allure
from utils.logger import get_logger

logger = get_logger("assert_util")

class AssertUtil:
    """统一断言封装"""

    @staticmethod
    @allure.step("断言状态码")
    def assert_status_code(response, expected_code):
        """断言 HTTP 状态码"""
        actual_code = response.status_code
        assert actual_code == expected_code, (
            f"状态码断言失败: 期望={expected_code}, 实际={actual_code} | "
            f"响应={response.text[:500]}"
        )

    @staticmethod
    @allure.step("断言业务码")
    def assert_business_code(response, expected_code):
        """断言业务状态码"""
        try:
            json_data = response.json()
        except Exception:
            assert False, f"响应非JSON格式: {response.text[:500]}"
        actual_code = json_data.get("code")
        assert actual_code == expected_code, (
            f"业务码断言失败: 期望={expected_code}, 实际={actual_code} | "
            f"message={json_data.get('message', '')} | "
            f"响应={response.text[:500]}"
        )

    @staticmethod
    @allure.step("断言业务数据")
    def assert_business_data(response, field_checks):
        """
        断言业务数据
        field_checks: list of dict
            [{"field": "data.id", "check": "not_empty"},
             {"field": "data.username", "check": "equals", "expect": "zhangsan"}]
        """
        try:
            json_data = response.json()
        except Exception:
            assert False, f"响应非JSON格式: {response.text[:500]}"

        for check_item in field_checks:
            field_path = check_item["field"]
            check_type = check_item["check"]

            # 按路径取值
            value = json_data
            for key in field_path.split("."):
                if isinstance(value, dict):
                    value = value.get(key)
                elif isinstance(value, list) and key.isdigit():
                    value = value[int(key)]
                else:
                    value = None
                    break

            if check_type == "not_empty":
                assert value is not None and value != "", (
                    f"字段非空断言失败: {field_path} 值为空 | 响应={response.text[:500]}"
                )
            elif check_type == "equals":
                expect = check_item["expect"]
                assert value == expect, (
                    f"字段匹配断言失败: {field_path} 期望={expect}, 实际={value} | "
                    f"响应={response.text[:500]}"
                )
            elif check_type == "type":
                expect_type = check_item["expect"]
                assert isinstance(value, expect_type), (
                    f"类型断言失败: {field_path} 期望类型={expect_type}, 实际类型={type(value)} | "
                    f"实际值={value}"
                )
            elif check_type == "contains":
                expect = check_item["expect"]
                assert expect in str(value), (
                    f"包含断言失败: {field_path} 期望包含={expect}, 实际={value}"
                )
            elif check_type == "length":
                expect_len = check_item["expect"]
                assert len(str(value)) == expect_len, (
                    f"长度断言失败: {field_path} 期望长度={expect_len}, 实际长度={len(str(value))}"
                )

    @staticmethod
    @allure.step("完整三层断言")
    def assert_all(response, expected_status, expected_code=None, field_checks=None):
        """完整三层断言"""
        AssertUtil.assert_status_code(response, expected_status)
        if expected_code is not None:
            AssertUtil.assert_business_code(response, expected_code)
        if field_checks:
            AssertUtil.assert_business_data(response, field_checks)
```

**utils/token_util.py**：

```python
"""
统一鉴权与 Token 管理
- 登录接口统一获取 Token
- 全局 Headers 统一注入
- Token 过期自动刷新
"""
import time
from config.config import CONFIG, BASE_URL
from utils.request_util import RequestUtil
from utils.logger import get_logger

logger = get_logger("token_util")

class TokenUtil:
    """Token 管理工具"""

    _token = None
    _token_expire_time = 0
    _token_lifetime = 7200  # 默认 2 小时

    @classmethod
    def get_token(cls, request_util=None):
        """获取 Token，过期自动刷新"""
        if cls._token and time.time() < cls._token_expire_time:
            return cls._token

        logger.info("Token 已过期或未获取，正在刷新...")
        cls.refresh_token(request_util)
        return cls._token

    @classmethod
    def refresh_token(cls, request_util=None):
        """刷新 Token"""
        request_util = request_util or RequestUtil()
        auth_config = CONFIG.get("auth", {})
        login_url = BASE_URL + auth_config.get("login_url", "/api/auth/login")

        login_data = {
            "username": auth_config.get("username", ""),
            "password": auth_config.get("password", ""),
        }

        response = request_util.post(login_url, json=login_data)
        try:
            json_data = response.json()
            cls._token = json_data.get("data", {}).get("token", "")
            cls._token_expire_time = time.time() + cls._token_lifetime
            logger.info("Token 刷新成功")
        except Exception as e:
            logger.error(f"Token 刷新失败: {e}")
            raise

    @classmethod
    def get_headers(cls, request_util=None):
        """获取带 Token 的全局 Headers"""
        token = cls.get_token(request_util)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    @classmethod
    def clear_token(cls):
        """清除 Token"""
        cls._token = None
        cls._token_expire_time = 0
```

#### 3.3 conftest.py

```python
"""
Pytest 全局钩子
- Fixture：request_util、auth_headers
- Allure 环境信息
- 失败重跑配置
"""
import pytest
import allure
from utils.request_util import RequestUtil
from utils.token_util import TokenUtil
from config.config import CONFIG, ENV

@pytest.fixture(scope="session")
def request_util():
    """全局请求工具实例"""
    return RequestUtil()

@pytest.fixture(scope="session")
def auth_headers(request_util):
    """全局鉴权 Headers"""
    return TokenUtil.get_headers(request_util)

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """失败截图与响应信息附加"""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        # 附加失败信息到 Allure 报告
        allure.attach(
            str(report.longrepr),
            name="失败详情",
            attachment_type=allure.attachment_type.TEXT,
        )

def pytest_configure(config):
    """Allure 环境信息"""
    allure.environment(
        Environment=ENV,
        Base_URL=CONFIG.get("base_url", ""),
    )
```

#### 3.4 pytest.ini

```ini
[pytest]
testpaths = testcases
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --alluredir=reports/allure-results
    --reruns=1
    --reruns-delay=2
markers =
    smoke: 冒烟测试
    regression: 回归测试
    p0: 优先级P0
    p1: 优先级P1
    p2: 优先级P2
```

### Step 4: 生成接口请求层（api/ 层）

**规范要求：**
- 接口只封装在 `api/` 层
- 一个接口对应一个文件
- 类名采用大驼峰命名法（如 `UserAPI`、`OrderAPI`）
- 方法名采用小写字母+下划线（如 `login()`、`get_user_info()`）
- 引入 `RequestUtil` 和 `TokenUtil`
- 每个方法自动处理路径参数替换、Query 参数拼接、Headers 注入、Body 构建

**生成模板：**

```python
"""
{module_name}接口封装
- 接口路径：{api_path}
- 请求方法：{method}
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

    def {method_name}(self, {params_signature}, headers=None):
        """
        {api_name}
        - 接口路径：{api_path}
        - 请求方法：{method}
        {params_docstring}
        """
        url = self.base_url + "{api_path}"
        {path_param_replace}
        _headers = headers or TokenUtil.get_headers(self.request_util)
        {query_param_build}
        {body_param_build}
        {request_call}
        logger.info(f"{api_name} | status={response.status_code}")
        return response
```

**路径参数替换：**

```python
# Path 参数替换
url = url.replace("{id}", str(id))
url = url.replace("{order_id}", str(order_id))
```

**Query 参数构建：**

```python
# Query 参数
params = {}
if page is not None:
    params["page"] = page
if size is not None:
    params["size"] = size
```

**Body 参数构建：**

```python
# Body 参数
json_data = {
    "username": username,
    "password": password,
}
```

**请求调用（按方法类型）：**

```python
# GET
response = self.request_util.get(url, headers=_headers, params=params)

# POST
response = self.request_util.post(url, headers=_headers, json=json_data)

# PUT
response = self.request_util.put(url, headers=_headers, json=json_data)

# DELETE
response = self.request_util.delete(url, headers=_headers, params=params)

# PATCH
response = self.request_util.patch(url, headers=_headers, json=json_data)
```

### Step 5: 生成测试数据层（data/ 层）

#### 5.1 数据驱动模式

当用户提供了测试数据目录时，将数据文件映射到 `data/` 目录：

```
data/
├── _dependencies.yaml          # 依赖关系配置（如存在）
├── auth/                       # 认证管理模块
│   ├── user_login_data.yaml    # 登录接口测试数据
│   └── user_register_data.yaml
├── order/
│   ├── create_order_data.yaml
│   └── ...
└── ...
```

数据文件保持原格式（YAML/JSON），在用例层通过以下方式加载：

```python
import yaml
import os

def load_test_data(data_file):
    """加载 YAML 测试数据"""
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", data_file
    )
    with open(data_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
```

#### 5.2 内联数据模式

当用户未提供测试数据目录时，在 `data/` 目录下为每个接口生成默认测试数据文件：

```yaml
# data/auth/user_login_data.yaml
api_id: "POST_/api/auth/login"
name: "用户登录"
test_cases:
  - case_id: "POS_001"
    name: "合法用户名密码登录"
    category: "positive"
    priority: "P0"
    parameters:
      body_params:
        username: "testuser01"
        password: "Test@1234"
    expected:
      status_code: 200
      business_code: 0
  - case_id: "NEG_001"
    name: "用户名为空"
    category: "negative"
    priority: "P0"
    parameters:
      body_params:
        username: ""
        password: "Test@1234"
    expected:
      status_code: 400
```

默认生成规则：
- **正向数据**：基于参数的 example/default 值构造合法请求
- **异常数据**：必填参数为空、类型不匹配、超长字符串
- **仅生成核心场景**：不过度生成，保持精简可用

### Step 6: 生成测试用例层（testcases/ 层）

**规范要求：**
- 用例只写在 `testcases/` 层
- 一个接口对应一个测试文件
- 测试方法必须以 `test_` 开头
- 类名采用大驼峰命名法，按场景分类（Normal/Exception/Boundary/Security）
- 引入 `pytest`、`allure`、API 层、断言工具
- 三层断言（状态码 + 业务码 + 业务数据）
- 数据驱动：使用 `@pytest.mark.parametrize` 或内部加载

**数据驱动模式用例模板：**

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
    @pytest.mark.parametrize("case", load_test_data("auth/user_login_data.yaml")["test_cases"])
    @allure.title("{api_name} - {case_name}")
    @allure.feature("{module_name}")
    @allure.story("异常场景")
    def test_{method_name}_data_driven(self, case, request_util, auth_headers):
        """数据驱动测试"""
        self.api.request_util = request_util
        # 构建请求参数
        {build_params_from_case}
        response = self.api.{method_name}(
            {params_from_case},
            headers=auth_headers
        )
        # 三层断言
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])
        if "business_code" in case["expected"]:
            AssertUtil.assert_business_code(response, case["expected"]["business_code"])


class Test{ClassName}Boundary:
    """{api_name} - 边界场景"""

    def setup_class(self):
        self.api = {ClassName}API()

    @pytest.mark.p1
    @allure.title("{api_name} - 边界值测试")
    @allure.feature("{module_name}")
    @allure.story("边界场景")
    def test_{method_name}_boundary(self, request_util, auth_headers):
        """测试边界值"""
        # 按接口参数约束生成边界测试
        {boundary_test_cases}


class Test{ClassName}Security:
    """{api_name} - 安全场景"""

    def setup_class(self):
        self.api = {ClassName}API()

    @pytest.mark.p1
    @allure.title("{api_name} - 安全测试")
    @allure.feature("{module_name}")
    @allure.story("安全场景")
    def test_{method_name}_security(self, request_util, auth_headers):
        """测试安全场景"""
        {security_test_cases}
```

**内联数据模式用例模板：**

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
            "name": "合法请求",
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
                {empty_params}
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
            {params_from_case},
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
```

### Step 7: 注入健壮逻辑

所有生成的脚本自动包含以下企业级健壮逻辑：

| 能力 | 实现方式 | 位置 |
|------|---------|------|
| 超时统一 | `TIMEOUT=30` 常量 | `config/config.py` |
| 自动重试 | `MAX_RETRY=2` + 重试循环 | `utils/request_util.py` |
| 异常捕获 | try/except 捕获 5 类异常 | `utils/request_util.py` |
| Token 鉴权 | `TokenUtil` 自动获取/刷新 | `utils/token_util.py` |
| 失败重跑 | `--reruns=1` | `pytest.ini` |
| 日志输出 | `get_logger` 统一日志 | `utils/logger.py` |
| Allure 报告 | 步骤/特性/故事标记 | 用例层 `@allure` |
| 环境切换 | `ENV` 环境变量 | `config/config.py` |
| 脚本不中断 | 单个用例失败不影响整体 | Pytest 机制 + try/except |

### Step 8: 输出校验与汇总

生成完成后，输出汇总报告：

```
========================================
接口自动化脚本生成汇总
========================================
项目路径：api_auto_project/
接口总数：15
模块数量：3

生成文件统计：
- config/      3 文件（config.py + 2 环境配置）
- api/         15 文件（每个接口一个封装文件）
- testcases/   15 文件（每个接口一个用例文件）
- data/        15 文件（每个接口一个数据文件）
- utils/       4 文件（logger + request + assert + token）
- conftest.py  1 文件
- pytest.ini   1 文件

数据模式：数据驱动 / 内联数据
命名规范：✓ 符合团队标准
断言覆盖：✓ 三层断言（状态码+业务码+业务数据）
健壮逻辑：✓ 超时/重试/异常/鉴权/日志

运行方式：
1. cd api_auto_project
2. pip install -r requirements.txt
3. pytest testcases/ -v --alluredir=reports/allure-results
4. allure serve reports/allure-results
========================================
```

## 输出目录结构（完整）

```
api_auto_project/
├── config/
│   ├── config.py               # 全局配置（环境切换、常量）
│   ├── dev.yaml                # 开发环境配置
│   └── test.yaml               # 测试环境配置
├── api/
│   ├── __init__.py
│   ├── user_api.py             # 用户接口封装
│   ├── auth_api.py             # 认证接口封装
│   ├── order_api.py            # 订单接口封装
│   └── ...                     # 按模块/接口拆分
├── testcases/
│   ├── __init__.py
│   ├── test_user_login.py      # 用户登录用例
│   ├── test_user_register.py   # 用户注册用例
│   ├── test_order_create.py    # 创建订单用例
│   └── ...                     # 按模块/接口拆分
├── data/
│   ├── auth/
│   │   ├── user_login_data.yaml
│   │   └── user_register_data.yaml
│   ├── order/
│   │   ├── create_order_data.yaml
│   │   └── ...
│   └── ...
├── utils/
│   ├── __init__.py
│   ├── logger.py               # 统一日志
│   ├── request_util.py         # 统一请求封装
│   ├── assert_util.py          # 统一断言
│   └── token_util.py           # Token 管理
├── reports/
│   ├── logs/                   # 日志输出目录
│   └── allure-results/         # Allure 报告数据
├── conftest.py                 # Pytest 全局钩子
├── pytest.ini                  # Pytest 配置
├── requirements.txt            # Python 依赖
└── README.md                   # 项目说明（可选）
```

## requirements.txt

```
requests>=2.28.0
pytest>=7.0.0
allure-pytest>=2.12.0
PyYAML>=6.0
pytest-rerunfailures>=11.0
```

## 统一命名规范

### 包 / 目录
- 小写字母 + 下划线，简洁清晰
- 示例：`api/`、`config/`、`utils/`、`testcases/`、`data/`

### 文件名
- 小写字母 + 下划线，一个接口对应一个文件
- 示例：`user_api.py`、`order_api.py`、`test_login.py`

### 类名
- 大驼峰命名法（UpperCamelCase），按场景分不同类
- API 层：`UserAPI`、`OrderAPI`
- 用例层：`TestUserLoginNormal`、`TestUserLoginException`、`TestUserLoginBoundary`、`TestUserLoginSecurity`

### 方法名
- 小写字母 + 下划线，语义简短精准
- API 层：`login()`、`get_user_info()`、`create_order()`
- 公共方法抽离到 `utils/` 目录

### 测试方法
- 必须以 `test_` 开头，见名知意
- 示例：`test_login_success`、`test_login_password_error`、`test_login_mobile_empty`

### 变量名
- 小写字母 + 下划线，不使用单字母、不使用歧义缩写
- 示例：`username`、`token`、`headers`、`response`、`order_id`

### 常量
- 全大写字母 + 下划线，集中存放于配置文件，禁止硬编码
- 示例：`BASE_URL`、`TIMEOUT`、`MAX_RETRY`、`CONTENT_TYPE`

## 断言策略

每条用例至少包含 **3 层断言**：

| 层级 | 断言内容 | 示例 |
|------|---------|------|
| 1. 状态码断言 | HTTP 状态码匹配 | `status_code == 200` / `status_code == 400` |
| 2. 业务码断言 | 业务状态码匹配 | `code == 0` / `code == 40001` |
| 3. 业务数据断言 | 关键字段非空/匹配/类型/长度 | `data.id not_empty` / `data.username == "zhangsan"` |

**业务数据断言类型：**

| 检查类型 | check 值 | 说明 |
|---------|----------|------|
| 非空检查 | `not_empty` | 字段值不为 None 且不为空字符串 |
| 值匹配 | `equals` | 字段值等于期望值 |
| 类型检查 | `type` | 字段值类型匹配 |
| 包含检查 | `contains` | 字段值包含期望内容 |
| 长度检查 | `length` | 字段值长度等于期望值 |

**禁止：**
- 只断言 `status_code`
- 无意义断言（如 `assert True`）
- 重复冗余断言

## 全局异常处理

| 异常类型 | 处理方式 |
|---------|---------|
| ConnectTimeout | 自动重试，记录日志 |
| ReadTimeout | 自动重试，记录日志 |
| ConnectionError | 自动重试，记录日志 |
| ProxyError | 自动重试，记录日志 |
| JSONDecodeError | 直接抛出，记录错误日志 |
| 其他异常 | 直接抛出，记录错误日志 |

**重试机制：**
- 默认重试 2 次（首次请求 + 2 次重试 = 最多 3 次请求）
- 每次重试前记录 warning 日志
- 重试全部失败后抛出最后一次异常

**失败重跑：**
- Pytest `--reruns=1`，单个用例失败自动重跑 1 次
- 重跑间隔 2 秒

## 统一鉴权与 Token 注入

1. **登录接口统一获取 Token**：通过 `TokenUtil.get_token()` 获取
2. **全局 Headers 统一注入**：`Authorization: Bearer {token}` + `Content-Type: application/json`
3. **Token 过期自动刷新**：Token 有效期 2 小时，过期自动调用 `refresh_token()`
4. **不需要鉴权的接口**：在 API 层方法中可传入自定义 `headers`，跳过 Token 注入

## 日志、报告、环境切换

### 日志格式
- 格式：`时间 - 级别 - 模块 - 信息`
- 请求/响应自动打印
- 控制台输出 INFO 级别，文件输出 DEBUG 级别

### 报告
- Allure2 报告
- 包含步骤（`@allure.step`）、特性（`@allure.feature`）、故事（`@allure.story`）
- 失败用例自动附加失败详情

### 环境切换
- dev/test/pre/prod 四环境隔离
- 通过环境变量 `API_TEST_ENV` 切换
- 命令行：`API_TEST_ENV=dev pytest testcases/`

## 生成脚本调用

```bash
# 基本用法：仅基于接口定义生成脚本（内联数据模式）
python3 <skill_path>/scripts/testscript_generator.py api_definitions.json --output api_auto_project/

# 数据驱动模式：指定测试数据目录
python3 <skill_path>/scripts/testscript_generator.py api_definitions.json --data-dir test_data/ --output api_auto_project/

# 仅生成指定模块的脚本
python3 <skill_path>/scripts/testscript_generator.py api_definitions.json --module "认证管理" --output api_auto_project/

# 仅生成指定接口的脚本
python3 <skill_path>/scripts/testscript_generator.py api_definitions.json --api "POST_/api/auth/login" --output api_auto_project/

# 指定输出格式为 YAML 数据驱动
python3 <skill_path>/scripts/testscript_generator.py api_definitions.json --data-format yaml --output api_auto_project/

# 跳过基础设施生成（已有项目仅追加接口）
python3 <skill_path>/scripts/testscript_generator.py api_definitions.json --skip-infra --output api_auto_project/

# 不生成 utils/ 和 config/（已有项目仅更新接口和用例）
python3 <skill_path>/scripts/testscript_generator.py api_definitions.json --skip-utils --skip-config --output api_auto_project/
```

## 注意事项

- **严格分层**：接口只封装在 `api/` 层，用例只写在 `testcases/` 层，数据只放 `data/` 层，工具统一放 `utils/`，禁止混用层级、禁止硬编码
- **命名一致**：文件名、类名、方法名、变量名严格遵循命名规范
- **三层断言**：每条用例至少包含状态码 + 业务码 + 业务数据三层断言
- **数据解耦**：数据驱动模式下，测试数据与测试脚本分离，修改数据不影响脚本逻辑
- **不遗漏接口**：`api_definitions.json` 中的所有接口必须全部生成，不可跳过
- **不遗漏参数**：每个接口的所有参数都必须在 API 封装中体现
- **业务规则覆盖**：识别到的业务规则（鉴权/幂等/限流等）在用例中有对应测试
- **Token 自动处理**：需要鉴权的接口自动注入 Token，不需要的接口可跳过
- **依赖变量处理**：测试数据中的 `${VARIABLE}` 格式变量在运行时动态替换
- **路径参数替换**：`/api/users/{id}` 格式的路径参数在 API 层自动替换
- **编码处理**：所有文件 UTF-8 编码
- **环境隔离**：不同环境的配置互不干扰
- **可运行性**：生成的脚本无需修改即可运行（需先配置环境地址和账号）

## 与其他技能的协作

```
api-schema-parser ──→ 标准化接口数据 (api_definitions.json)
        │
        ├──→ api-testdata-generator ──→ 测试数据文件 (data/)
        │       │
        │       └──→ api-testscript-generator ──→ 接口自动化脚本工程
        │               │                         (api/ + testcases/ + data/ + utils/ + config/)
        │               │
        │               └── 可直接运行：pytest testcases/
        │
        └──→ api-testscript-generator（无测试数据）
                    │
                    └── 内联数据模式 ──→ 接口自动化脚本工程
                                        (自动生成默认测试数据)
```

**建议使用流程**：
1. 先使用 `api-schema-parser` 将接口文档标准化为 `api_definitions.json`
2. 使用 `api-testdata-generator` 生成全场景测试数据（可选）
3. 使用本技能基于接口定义和测试数据生成自动化脚本工程
4. 配置环境地址和账号后直接运行 `pytest testcases/`

## Resources

### scripts/testscript_generator.py
Python 脚本，核心脚本生成引擎，支持：
- 读取 `api_definitions.json` 接口定义
- 识别数据模式（数据驱动/内联数据）
- 按团队目录规范和分层架构生成脚本文件
- 自动完成接口请求封装（路径替换、参数构建、请求调用）
- 按数据驱动方式绑定测试数据
- 自动生成三层断言
- 注入企业级健壮逻辑
- 严格遵循团队编码规范
- CLI 用法：
  - 基本用法：`python3 testscript_generator.py <api_definitions.json> [--data-dir <dir>] [--output <dir>] [--module <name>] [--api <api_id>] [--data-format yaml|json] [--skip-infra] [--skip-utils] [--skip-config]`

### references/coding-standards.md
团队编码规范参考文档，包含：
- 目录结构规范
- 命名规范（包/文件/类/方法/变量/常量）
- 分层架构规范
- 硬编码禁止规则
- 依赖管理规范

### references/assertion-patterns.md
断言策略与模式参考文档，包含：
- 三层断言规范
- 业务数据断言类型定义
- 响应字段路径取值规则
- 断言失败信息格式
- 禁止断言列表

### references/template-reference.md
代码模板参考文档，包含：
- API 层封装模板
- 数据驱动用例模板
- 内联数据用例模板
- 数据加载工具模板
- 模块级 `__init__.py` 模板
- 依赖变量替换逻辑
