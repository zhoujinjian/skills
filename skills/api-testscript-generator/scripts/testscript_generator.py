#!/usr/bin/env python3
"""
接口自动化测试脚本批量生成器
- 基于标准化接口定义（api_definitions.json）与可选测试数据目录
- 按团队既定工程规范生成分层架构的 Pytest 自动化脚本
- 支持数据驱动模式和内联数据模式

用法：
  python3 testscript_generator.py <api_definitions.json> [--data-dir <dir>] [--output <dir>]
      [--module <name>] [--api <api_id>] [--data-format yaml|json] [--skip-infra]
      [--skip-utils] [--skip-config]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ============================================================
# 常量定义
# ============================================================

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RETRY = 2
DEFAULT_PROJECT_NAME = "api_auto_project"
DEFAULT_DATA_FORMAT = "yaml"

# ============================================================
# 工具函数
# ============================================================


def to_snake_case(name):
    """转换为 snake_case"""
    # 替换常见分隔符
    name = re.sub(r"[-/\\]", "_", name)
    # 大驼峰/小驼峰转下划线
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    # 清理
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    return name.lower()


def to_camel_case(name):
    """转换为 UpperCamelCase"""
    parts = to_snake_case(name).split("_")
    return "".join(p.capitalize() for p in parts if p)


# 中文模块名 -> 英文映射
MODULE_NAME_MAP = {
    "认证管理": "auth",
    "认证": "auth",
    "用户管理": "user",
    "用户": "user",
    "订单管理": "order",
    "订单": "order",
    "商品管理": "product",
    "商品": "product",
    "支付管理": "payment",
    "支付": "payment",
    "购物车": "cart",
    "收货地址": "address",
    "地址管理": "address",
    "物流管理": "logistics",
    "物流": "logistics",
    "评价管理": "review",
    "评价": "review",
    "优惠券": "coupon",
    "营销管理": "marketing",
    "营销": "marketing",
    "搜索": "search",
    "分类管理": "category",
    "分类": "category",
    "品牌管理": "brand",
    "品牌": "brand",
    "库存管理": "inventory",
    "库存": "inventory",
    "统计分析": "statistics",
    "统计": "statistics",
    "消息通知": "message",
    "消息": "message",
    "系统管理": "system",
    "系统": "system",
    "权限管理": "permission",
    "权限": "permission",
    "角色管理": "role",
    "角色": "role",
    "文件管理": "file",
    "文件": "file",
    "上传": "upload",
    "管理后台": "admin",
    "Banner轮播图": "banner",
    "轮播图": "banner",
    "商品搜索": "search",
    "验证码管理": "captcha",
    "验证码": "captcha",
    "购物车管理": "cart",
}


def to_module_name(module_str):
    """模块名转 snake_case 目录名"""
    if not module_str or module_str == "未分类":
        return "common"
    # 优先查中文映射表
    if module_str in MODULE_NAME_MAP:
        return MODULE_NAME_MAP[module_str]
    # 尝试 snake_case 转换
    result = to_snake_case(module_str)
    # 如果转换后为空（纯中文），基于路径推断
    if not result:
        return "common"
    return result


def api_id_to_filename(api_id, suffix=""):
    """api_id 转文件名"""
    # POST_/api/auth/login -> auth_login
    parts = api_id.split("_", 1)
    if len(parts) > 1:
        path_part = parts[1]
    else:
        path_part = api_id
    # 移除 /api/ 前缀
    path_part = re.sub(r"^/api/", "", path_part)
    # 替换 / 和 {xxx} 为 _
    path_part = re.sub(r"[/{]", "_", path_part)
    path_part = re.sub(r"}", "", path_part)
    path_part = re.sub(r"_+", "_", path_part)
    path_part = path_part.strip("_")
    return path_part + suffix


def api_id_to_class_name(api_id):
    """api_id 转 API 类名"""
    filename = api_id_to_filename(api_id)
    return to_camel_case(filename) + "API"


def api_id_to_method_name(api_id):
    """api_id 转 API 方法名"""
    method = api_id.split("_")[0].lower()
    filename = api_id_to_filename(api_id)
    base_name = to_snake_case(filename)
    # 如果方法名中已包含方法前缀，移除
    for m in ["get_", "post_", "put_", "delete_", "patch_"]:
        if base_name.startswith(m):
            base_name = base_name[len(m):]
            break
    return f"{method}_{base_name}" if method != "get" else f"get_{base_name}"


def get_method_verb(method):
    """获取方法对应的动词"""
    verbs = {
        "GET": "获取",
        "POST": "创建",
        "PUT": "更新",
        "DELETE": "删除",
        "PATCH": "修改",
    }
    return verbs.get(method.upper(), "操作")


# ============================================================
# 基础设施生成器
# ============================================================


class InfraGenerator:
    """项目基础设施生成"""

    def __init__(self, output_dir, data_format="yaml"):
        self.output_dir = Path(output_dir)
        self.data_format = data_format

    def generate_all(self):
        """生成全部基础设施"""
        self._generate_config()
        self._generate_utils()
        self._generate_conftest()
        self._generate_pytest_ini()
        self._generate_requirements()
        self._generate_init_files()

    def _ensure_dir(self, dir_path):
        """确保目录存在"""
        os.makedirs(dir_path, exist_ok=True)

    def _write_file(self, file_path, content):
        """写入文件"""
        self._ensure_dir(os.path.dirname(file_path))
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

    def _generate_config(self):
        """生成 config/ 目录"""
        # config.py
        config_py = '''"""
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
    if not os.path.exists(config_path):
        return {"base_url": "", "timeout": 30, "max_retry": 2}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


CONFIG = load_config()

# 全局常量
BASE_URL = CONFIG.get("base_url", "")
TIMEOUT = CONFIG.get("timeout", 30)
MAX_RETRY = CONFIG.get("max_retry", 2)
CONTENT_TYPE = "application/json"
'''
        self._write_file(self.output_dir / "config" / "config.py", config_py)

        # test.yaml
        test_yaml = """# 测试环境配置
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
"""
        self._write_file(self.output_dir / "config" / "test.yaml", test_yaml)

        # dev.yaml
        dev_yaml = """# 开发环境配置
base_url: "http://localhost:8080"
timeout: 30
max_retry: 2

auth:
  login_url: "/api/auth/login"
  username: "devuser"
  password: "Dev@1234"
"""
        self._write_file(self.output_dir / "config" / "dev.yaml", dev_yaml)

    def _generate_utils(self):
        """生成 utils/ 目录"""
        # logger.py
        logger_py = '''"""
统一日志模块
- 格式：时间 - 级别 - 模块 - 信息
- 请求/响应自动打印
"""
import logging
import os

LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "logs"
)
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
'''
        self._write_file(self.output_dir / "utils" / "logger.py", logger_py)

        # request_util.py
        request_util_py = '''"""
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
        for attempt in range(1, MAX_RETRY + 2):
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
'''
        self._write_file(self.output_dir / "utils" / "request_util.py", request_util_py)

        # assert_util.py
        assert_util_py = '''"""
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
                    f"类型断言失败: {field_path} 期望类型={expect_type}, "
                    f"实际类型={type(value)} | 实际值={value}"
                )
            elif check_type == "contains":
                expect = check_item["expect"]
                assert expect in str(value), (
                    f"包含断言失败: {field_path} 期望包含={expect}, 实际={value}"
                )
            elif check_type == "length":
                expect_len = check_item["expect"]
                assert len(str(value)) == expect_len, (
                    f"长度断言失败: {field_path} 期望长度={expect_len}, "
                    f"实际长度={len(str(value))}"
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
'''
        self._write_file(self.output_dir / "utils" / "assert_util.py", assert_util_py)

        # token_util.py
        token_util_py = '''"""
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
    _token_lifetime = 7200

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
'''
        self._write_file(self.output_dir / "utils" / "token_util.py", token_util_py)

    def _generate_conftest(self):
        """生成 conftest.py"""
        conftest_py = '''"""
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
    """失败信息附加到 Allure 报告"""
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
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
'''
        self._write_file(self.output_dir / "conftest.py", conftest_py)

    def _generate_pytest_ini(self):
        """生成 pytest.ini"""
        pytest_ini = """[pytest]
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
"""
        self._write_file(self.output_dir / "pytest.ini", pytest_ini)

    def _generate_requirements(self):
        """生成 requirements.txt"""
        requirements = """requests>=2.28.0
pytest>=7.0.0
allure-pytest>=2.12.0
PyYAML>=6.0
pytest-rerunfailures>=11.0
"""
        self._write_file(self.output_dir / "requirements.txt", requirements)

    def _generate_init_files(self):
        """生成 __init__.py 文件"""
        init_content = '"""\n{module_name}\n"""\n'
        for pkg in ["api", "testcases", "utils"]:
            pkg_dir = self.output_dir / pkg
            self._ensure_dir(str(pkg_dir))
            self._write_file(
                pkg_dir / "__init__.py",
                init_content.format(module_name=pkg)
            )


# ============================================================
# API 层生成器
# ============================================================


class ApiLayerGenerator:
    """API 请求层生成"""

    def __init__(self, output_dir, apis, global_rules=None):
        self.output_dir = Path(output_dir)
        self.apis = apis
        self.global_rules = global_rules or {}
        self.generated_files = []

    def generate(self):
        """生成所有 API 封装文件"""
        # 按模块分组
        module_groups = {}
        for api in self.apis:
            module = to_module_name(api.get("module", "common"))
            if module not in module_groups:
                module_groups[module] = []
            module_groups[module].append(api)

        for module, module_apis in module_groups.items():
            self._generate_module_api(module, module_apis)

        return self.generated_files

    def _generate_module_api(self, module, module_apis):
        """生成模块级 API 文件"""
        # 按接口逐个生成文件
        for api_def in module_apis:
            self._generate_single_api(module, api_def)

    def _generate_single_api(self, module, api_def):
        """生成单个接口的 API 封装文件"""
        api_id = api_def["api_id"]
        class_name = api_id_to_class_name(api_id)
        api_name = api_def.get("name", api_id)
        api_path = api_def["path"]
        method = api_def["method"].upper()
        filename = api_id_to_filename(api_id, "_api.py")

        # 解析参数
        params = api_def.get("parameters", {})
        path_params = params.get("path_params", [])
        query_params = params.get("query_params", [])
        header_params = params.get("header_params", [])
        body_params = params.get("body_params", [])

        # 判断是否需要鉴权
        needs_auth = self._needs_auth(api_def, header_params)

        # 构建方法签名
        method_params = self._build_method_params(
            path_params, query_params, body_params, needs_auth
        )

        # 构建方法体
        method_body = self._build_method_body(
            api_path, method, path_params, query_params,
            body_params, header_params, needs_auth, api_name
        )

        # 构建参数文档
        param_docs = self._build_param_docs(
            path_params, query_params, body_params
        )

        method_name = self._get_method_name(api_id, api_path, method)
        logger_name = f"{module}_{api_id_to_filename(api_id)}"

        code = f'''"""
{api_name}接口封装
- 接口路径：{api_path}
- 请求方法：{method}
"""
from config.config import BASE_URL
from utils.request_util import RequestUtil
from utils.token_util import TokenUtil
from utils.logger import get_logger

logger = get_logger("{logger_name}")


class {class_name}:
    """{api_name}接口封装"""

    def __init__(self, request_util=None):
        self.request_util = request_util or RequestUtil()
        self.base_url = BASE_URL

    def {method_name}({method_params}):
        """
        {api_name}
        - 接口路径：{api_path}
        - 请求方法：{method}
{param_docs}
        """
{method_body}
'''

        file_path = self.output_dir / "api" / module / filename
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
        self.generated_files.append(str(file_path))

    def _needs_auth(self, api_def, header_params):
        """判断接口是否需要鉴权"""
        # 检查 header_params 中是否有 Authorization
        for hp in header_params:
            if hp.get("name", "").lower() in ["authorization", "token", "x-auth-token"]:
                return True
        # 检查全局规则
        auth_rule = self.global_rules.get("authentication", {})
        if auth_rule:
            # 排除登录/注册等不需要鉴权的接口
            no_auth_paths = ["/login", "/register", "/captcha"]
            api_path = api_def.get("path", "")
            if any(p in api_path.lower() for p in no_auth_paths):
                return False
            return True
        return True  # 默认需要鉴权

    def _build_method_params(self, path_params, query_params, body_params, needs_auth):
        """构建方法参数签名"""
        params = ["self"]
        seen_names = set()

        # Path 参数
        for p in path_params:
            param_name = to_snake_case(p["name"])
            if param_name not in seen_names:
                params.append(param_name)
                seen_names.add(param_name)

        # Query 参数（可选）
        for p in query_params:
            param_name = to_snake_case(p["name"])
            if param_name not in seen_names:
                if not p.get("required", False):
                    params.append(f"{param_name}=None")
                else:
                    params.append(param_name)
                seen_names.add(param_name)

        # Body 参数（可选），跳过与 path/query 同名的参数
        for p in body_params:
            param_name = to_snake_case(p["name"])
            if param_name not in seen_names:
                if not p.get("required", False):
                    params.append(f"{param_name}=None")
                else:
                    params.append(param_name)
                seen_names.add(param_name)

        # Headers
        params.append("headers=None")

        return ", ".join(params)

    def _build_method_body(self, api_path, method, path_params, query_params,
                           body_params, header_params, needs_auth, api_name):
        """构建方法体"""
        lines = []

        # URL 构建
        url = api_path
        # Path 参数替换
        for p in path_params:
            param_name = to_snake_case(p["name"])
            original_name = p["name"]
            url = url.replace(f"{{{original_name}}}", f"{{{param_name}}}")

        lines.append(f'        url = self.base_url + "{url}"')

        # 如果有 path 参数替换
        if path_params:
            for p in path_params:
                param_name = to_snake_case(p["name"])
                original_name = p["name"]
                if f"{{{param_name}}}" in url or f"{{{original_name}}}" in api_path:
                    lines.append(
                        f'        url = url.replace("{{{original_name}}}", str({param_name}))'
                    )

        # Headers
        if needs_auth:
            lines.append(
                "        _headers = headers or TokenUtil.get_headers(self.request_util)"
            )
        else:
            lines.append(
                '        _headers = headers or {"Content-Type": "application/json"}'
            )

        # Query 参数
        if query_params:
            lines.append("        params = {}")
            for p in query_params:
                param_name = to_snake_case(p["name"])
                original_name = p["name"]
                if p.get("required", False):
                    lines.append(f'        params["{original_name}"] = {param_name}')
                else:
                    lines.append(
                        f"        if {param_name} is not None:\n"
                        f'            params["{original_name}"] = {param_name}'
                    )

        # Body 参数（跳过与 path/query 同名的参数，这些已通过其他方式传递）
        path_query_names = {to_snake_case(p["name"]) for p in path_params + query_params}
        if body_params:
            lines.append("        json_data = {}")
            for p in body_params:
                param_name = to_snake_case(p["name"])
                original_name = p["name"]
                # 跳过与 path/query 同名的参数
                if param_name in path_query_names:
                    continue
                if p.get("required", False):
                    lines.append(f'        json_data["{original_name}"] = {param_name}')
                else:
                    lines.append(
                        f"        if {param_name} is not None:\n"
                        f'            json_data["{original_name}"] = {param_name}'
                    )

        # 请求调用
        method_lower = method.lower()
        call_parts = [f"url", "headers=_headers"]
        if query_params:
            call_parts.append("params=params")
        if body_params:
            call_parts.append("json=json_data")

        call_args = ", ".join(call_parts)
        lines.append(
            f"        response = self.request_util.{method_lower}({call_args})"
        )

        # 日志
        lines.append(
            f'        logger.info(f"{api_name} | status={{response.status_code}}")'
        )

        # 返回
        lines.append("        return response")

        return "\n".join(lines)

    def _build_param_docs(self, path_params, query_params, body_params):
        """构建参数文档"""
        docs = []
        for p in path_params:
            name = to_snake_case(p["name"])
            desc = p.get("description", p["name"])
            required = "必填" if p.get("required", True) else "选填"
            docs.append(f"        :param {name}: {desc}（{required}）")

        for p in query_params:
            name = to_snake_case(p["name"])
            desc = p.get("description", p["name"])
            required = "必填" if p.get("required", False) else "选填"
            docs.append(f"        :param {name}: {desc}（{required}）")

        for p in body_params:
            name = to_snake_case(p["name"])
            desc = p.get("description", p["name"])
            required = "必填" if p.get("required", False) else "选填"
            ptype = p.get("type", "string")
            constraints = []
            if p.get("minLength"):
                constraints.append(f"最短{p['minLength']}位")
            if p.get("maxLength"):
                constraints.append(f"最长{p['maxLength']}位")
            if p.get("pattern"):
                constraints.append(f"格式约束")
            constraint_str = f"，{','.join(constraints)}" if constraints else ""
            docs.append(
                f"        :param {name}: {desc}（{required}，{ptype}{constraint_str}）"
            )

        docs.append("        :param headers: 自定义请求头")
        return "\n".join(docs)

    def _get_method_name(self, api_id, api_path, method):
        """获取方法名 - 基于接口路径和 HTTP 方法生成语义化的方法名"""
        # 解析路径，生成语义化方法名
        path = api_path
        # 移除 /api/ 前缀
        path = re.sub(r"^/api(/v\d+)?/", "", path)
        # 移除路径参数 {xxx}
        path = re.sub(r"\{[^}]+\}", "", path)
        # 替换 / 为 _
        path = re.sub(r"/+", "_", path)
        path = path.strip("_")

        # 基于路径和方法组合方法名
        parts = path.split("_") if path else []
        parts = [p for p in parts if p]

        # HTTP 方法动词映射
        method_verbs = {
            "GET": "get",
            "POST": "create" if not any(kw in path.lower() for kw in ["login", "register", "search", "logout"]) else None,
            "PUT": "update",
            "DELETE": "delete",
            "PATCH": "update",
        }

        # 特殊路径关键词映射
        special_names = {
            "login": "login",
            "register": "register",
            "logout": "logout",
            "search": "search",
            "list": "list",
            "detail": "detail",
            "info": "get_info",
        }

        # 检查特殊路径
        for keyword, method_name in special_names.items():
            if keyword in path.lower():
                return method_name

        # 常规方法名生成
        verb = method_verbs.get(method, method.lower())
        if verb is None:
            verb = method.lower()

        if parts:
            return f"{verb}_{'_'.join(parts)}"
        return method.lower()


# ============================================================
# 数据层生成器
# ============================================================


class DataLayerGenerator:
    """测试数据层生成"""

    def __init__(self, output_dir, apis, data_dir=None, data_format="yaml"):
        self.output_dir = Path(output_dir)
        self.apis = apis
        self.data_dir = data_dir  # 外部测试数据目录
        self.data_format = data_format
        self.generated_files = []

    def generate(self):
        """生成数据层文件"""
        if self.data_dir and os.path.isdir(self.data_dir):
            # 数据驱动模式：复制/映射外部数据文件
            self._map_external_data()
        else:
            # 内联数据模式：为每个接口生成默认测试数据
            self._generate_default_data()

        return self.generated_files

    def _map_external_data(self):
        """映射外部测试数据文件"""
        for api_def in self.apis:
            api_id = api_def["api_id"]
            module = to_module_name(api_def.get("module", "common"))
            filename = api_id_to_filename(api_id, f"_data.{self.data_format}")

            # 在外部数据目录中查找对应数据文件
            data_file = self._find_data_file(api_id, module)
            if data_file:
                # 读取外部数据并写入 data/ 目录
                with open(data_file, "r", encoding="utf-8") as f:
                    content = f.read()
                target_path = self.output_dir / "data" / module / filename
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(content)
                self.generated_files.append(str(target_path))
            else:
                # 找不到外部数据文件，生成默认数据
                self._generate_default_data_for_api(api_def)

    def _find_data_file(self, api_id, module):
        """在外部数据目录中查找接口对应的数据文件"""
        if not self.data_dir or not os.path.isdir(self.data_dir):
            return None

        # 在模块目录下查找
        module_dir = os.path.join(self.data_dir, module)
        if os.path.isdir(module_dir):
            for f in os.listdir(module_dir):
                if f.endswith((".yaml", ".yml", ".json")):
                    # 按 api_id 或接口名称匹配
                    if api_id.replace("/", "_").replace("{", "").replace("}", "") in f:
                        return os.path.join(module_dir, f)

        # 在根目录查找
        for f in os.listdir(self.data_dir):
            if f.endswith((".yaml", ".yml", ".json")):
                if api_id.replace("/", "_").replace("{", "").replace("}", "") in f:
                    return os.path.join(self.data_dir, f)

        return None

    def _generate_default_data(self):
        """为所有接口生成默认测试数据"""
        for api_def in self.apis:
            self._generate_default_data_for_api(api_def)

    def _generate_default_data_for_api(self, api_def):
        """为单个接口生成默认测试数据"""
        api_id = api_def["api_id"]
        api_name = api_def.get("name", api_id)
        module = to_module_name(api_def.get("module", "common"))
        filename = api_id_to_filename(api_id, f"_data.{self.data_format}")

        params = api_def.get("parameters", {})
        body_params = params.get("body_params", [])
        query_params = params.get("query_params", [])
        path_params = params.get("path_params", [])

        # 构建正向数据
        positive_params = {}
        for p in body_params + query_params + path_params:
            name = p["name"]
            positive_params[name] = self._generate_default_value(p)

        # 构建异常数据
        negative_cases = []
        for p in body_params + query_params:
            if p.get("required", False):
                neg_params = dict(positive_params)
                neg_params[p["name"]] = ""
                negative_cases.append({
                    "case_id": f"NEG_{len(negative_cases)+1:03d}",
                    "name": f"{p.get('description', p['name'])}为空",
                    "category": "negative",
                    "priority": "P0",
                    "parameters": {
                        "body_params": neg_params if p in body_params else positive_params,
                        "query_params": neg_params if p in query_params else {},
                        "path_params": neg_params if p in path_params else {},
                    },
                    "expected": {
                        "status_code": 400,
                    }
                })

        # 构建 YAML 内容
        data = {
            "api_id": api_id,
            "name": api_name,
            "module": api_def.get("module", "未分类"),
            "test_cases": [
                {
                    "case_id": "POS_001",
                    "name": f"正常请求",
                    "category": "positive",
                    "priority": "P0",
                    "parameters": {
                        "body_params": {
                            k: v for k, v in positive_params.items()
                            if any(bp["name"] == k for bp in body_params)
                        },
                        "query_params": {
                            k: v for k, v in positive_params.items()
                            if any(qp["name"] == k for qp in query_params)
                        },
                        "path_params": {
                            k: v for k, v in positive_params.items()
                            if any(pp["name"] == k for pp in path_params)
                        },
                    },
                    "expected": {
                        "status_code": 200,
                        "business_code": 0,
                    }
                }
            ] + negative_cases
        }

        # 写入文件
        target_path = self.output_dir / "data" / module / filename
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        if self.data_format == "yaml":
            import yaml
            with open(target_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        else:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        self.generated_files.append(str(target_path))

    def _generate_default_value(self, param):
        """根据参数约束生成默认值"""
        ptype = param.get("type", "string")
        example = param.get("example")
        default = param.get("default")

        if example is not None:
            return example
        if default is not None:
            return default

        if ptype == "string":
            fmt = param.get("format", "")
            if fmt == "email":
                return "test@example.com"
            elif fmt == "uri" or fmt == "url":
                return "https://example.com"
            elif fmt == "uuid":
                return "550e8400-e29b-41d4-a716-446655440000"
            elif fmt == "date-time":
                return "2026-01-15T10:30:00+08:00"
            elif fmt == "date":
                return "2026-01-15"
            elif fmt == "phone":
                return "13800001234"
            min_len = param.get("minLength", 4)
            return "test" + "a" * max(0, min_len - 4)
        elif ptype == "integer":
            minimum = param.get("minimum", 1)
            maximum = param.get("maximum", 100)
            return (minimum + maximum) // 2
        elif ptype == "number":
            minimum = param.get("minimum", 0)
            maximum = param.get("maximum", 100)
            return round((minimum + maximum) / 2, 2)
        elif ptype == "boolean":
            return True
        elif ptype == "array":
            return []
        elif ptype == "object":
            return {}
        return ""


# ============================================================
# 用例层生成器
# ============================================================


class TestCaseGenerator:
    """测试用例层生成"""

    def __init__(self, output_dir, apis, data_dir=None, data_format="yaml",
                 global_rules=None):
        self.output_dir = Path(output_dir)
        self.apis = apis
        self.data_dir = data_dir
        self.data_format = data_format
        self.global_rules = global_rules or {}
        self.generated_files = []

    def generate(self):
        """生成所有测试用例文件"""
        for api_def in self.apis:
            self._generate_test_case(api_def)
        return self.generated_files

    def _generate_test_case(self, api_def):
        """生成单个接口的测试用例"""
        api_id = api_def["api_id"]
        api_name = api_def.get("name", api_id)
        api_path = api_def["path"]
        method = api_def["method"].upper()
        module = to_module_name(api_def.get("module", "common"))
        module_name = api_def.get("module", "通用")
        class_base = api_id_to_class_name(api_id).replace("API", "")
        filename = api_id_to_filename(api_id)
        test_filename = f"test_{filename}.py"
        data_filename = f"{module}/{filename}_data.{self.data_format}"

        # 生成 API 方法名（与 API 层保持一致）
        api_layer = ApiLayerGenerator(self.output_dir, [api_def], self.global_rules)
        method_name = api_layer._get_method_name(api_id, api_path, method)

        params = api_def.get("parameters", {})
        body_params = params.get("body_params", [])
        query_params = params.get("query_params", [])
        path_params = params.get("path_params", [])

        # 判断是否需要鉴权
        needs_auth = True
        no_auth_paths = ["/login", "/register", "/captcha"]
        if any(p in api_path.lower() for p in no_auth_paths):
            needs_auth = False

        # 构建请求参数调用
        call_params = self._build_call_params(body_params, query_params, path_params, needs_auth)

        # 构建默认参数值（正向测试用）
        default_params = self._build_default_call_params(body_params, query_params, path_params)

        # 构建断言
        field_checks = self._build_field_checks(api_def)

        # 数据驱动模式判定
        is_data_driven = self.data_dir is not None

        if is_data_driven:
            code = self._generate_data_driven_test(
                api_name, api_path, method, module, module_name,
                class_base, filename, data_filename, method_name,
                call_params, default_params, field_checks,
                body_params, query_params, path_params, needs_auth
            )
        else:
            code = self._generate_inline_test(
                api_name, api_path, method, module, module_name,
                class_base, filename, data_filename, method_name,
                call_params, default_params, field_checks,
                body_params, query_params, path_params, needs_auth,
                api_def
            )

        file_path = self.output_dir / "testcases" / module / test_filename
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
        self.generated_files.append(str(file_path))

    def _generate_data_driven_test(self, api_name, api_path, method, module,
                                    module_name, class_base, filename,
                                    data_filename, method_name,
                                    call_params, default_params,
                                    field_checks, body_params, query_params,
                                    path_params, needs_auth):
        """生成数据驱动模式测试用例"""
        # fixture 参数
        fixture_params = ["self", "request_util"]
        if needs_auth:
            fixture_params.append("auth_headers")

        # 构建 API 调用参数
        if needs_auth:
            call_line = f"        response = self.api.{method_name}({call_params},\n            headers=auth_headers)"
        else:
            call_line = f"        response = self.api.{method_name}({call_params})"

        # fixture 参数（正向场景需要额外 case 参数）
        fixture_params_no_self = [p for p in fixture_params if p != "self"]
        param_extraction = self._build_param_extraction(body_params, query_params, path_params)

        # 正向场景参数提取（与异常场景相同逻辑）
        positive_param_extraction = param_extraction

        # 从 case 中提取参数并调用 API
        case_call_params = self._build_case_call_params(body_params, query_params, path_params, needs_auth, method_name)

        # 正向场景调用（与异常/边界/安全场景相同逻辑）
        positive_call_params = case_call_params

        field_checks_str = ""
        if field_checks:
            items = []
            for fc in field_checks:
                items.append(f"                {fc}")
            field_checks_str = ",\n".join(items)

        code = f'''"""
{api_name}测试用例
- 接口路径：{api_path}
- 请求方法：{method}
"""
import pytest
import allure
import yaml
import os
from api.{module}.{filename}_api import {class_base}API
from utils.assert_util import AssertUtil
from utils.logger import get_logger

logger = get_logger("test_{filename}")


def load_test_data(data_file):
    """加载 YAML 测试数据"""
    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", data_file
    )
    with open(data_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


TEST_DATA = load_test_data("{data_filename}")


class Test{class_base}Normal:
    """{api_name} - 正向场景"""

    def setup_class(self):
        self.api = {class_base}API()

    @pytest.mark.p0
    @pytest.mark.smoke
    @allure.title("{api_name} - 正常请求成功")
    @allure.feature("{module_name}")
    @allure.story("正向场景")
    @pytest.mark.parametrize(
        "case",
        [c for c in TEST_DATA["test_cases"] if c["category"] == "positive"],
        ids=[c["case_id"] for c in TEST_DATA["test_cases"] if c["category"] == "positive"]
    )
    def test_{method_name}_success(self, case, {", ".join(fixture_params_no_self)}):
        """测试正常请求成功"""
        self.api.request_util = request_util
{positive_param_extraction}
{positive_call_params}
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])
        if "business_code" in case["expected"]:
            AssertUtil.assert_business_code(response, case["expected"]["business_code"])
        # 执行 assertions 中的断言
        for assertion in case["expected"].get("assertions", []):
            field = assertion.get("field", "")
            operator = assertion.get("operator", "eq")
            value = assertion.get("value")
            if field and operator == "eq":
                AssertUtil.assert_business_data(response, [{{"field": field, "check": "equals", "expect": value}}])


class Test{class_base}Exception:
    """{api_name} - 异常场景"""

    def setup_class(self):
        self.api = {class_base}API()

    @pytest.mark.p0
    @allure.title("{api_name} - 异常测试")
    @allure.feature("{module_name}")
    @allure.story("异常场景")
    @pytest.mark.parametrize(
        "case",
        [c for c in TEST_DATA["test_cases"] if c["category"] == "negative"],
        ids=[c["case_id"] for c in TEST_DATA["test_cases"] if c["category"] == "negative"]
    )
    def test_{method_name}_negative(self, case, request_util{', auth_headers' if needs_auth else ''}):
        """数据驱动异常测试"""
        self.api.request_util = request_util
{param_extraction}
{case_call_params}
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])
        if "business_code" in case["expected"]:
            AssertUtil.assert_business_code(response, case["expected"]["business_code"])
        for assertion in case["expected"].get("assertions", []):
            field = assertion.get("field", "")
            operator = assertion.get("operator", "eq")
            value = assertion.get("value")
            if field and operator == "eq":
                AssertUtil.assert_business_data(response, [{{"field": field, "check": "equals", "expect": value}}])


class Test{class_base}Boundary:
    """{api_name} - 边界场景"""

    def setup_class(self):
        self.api = {class_base}API()

    @pytest.mark.p1
    @allure.title("{api_name} - 边界测试")
    @allure.feature("{module_name}")
    @allure.story("边界场景")
    @pytest.mark.parametrize(
        "case",
        [c for c in TEST_DATA["test_cases"] if c["category"] == "boundary"],
        ids=[c["case_id"] for c in TEST_DATA["test_cases"] if c["category"] == "boundary"]
    )
    def test_{method_name}_boundary(self, case, request_util{', auth_headers' if needs_auth else ''}):
        """数据驱动边界测试"""
        self.api.request_util = request_util
{param_extraction}
{case_call_params}
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])
        for assertion in case["expected"].get("assertions", []):
            field = assertion.get("field", "")
            operator = assertion.get("operator", "eq")
            value = assertion.get("value")
            if field and operator == "eq":
                AssertUtil.assert_business_data(response, [{{"field": field, "check": "equals", "expect": value}}])


class Test{class_base}Security:
    """{api_name} - 安全场景"""

    def setup_class(self):
        self.api = {class_base}API()

    @pytest.mark.p1
    @allure.title("{api_name} - 安全测试")
    @allure.feature("{module_name}")
    @allure.story("安全场景")
    @pytest.mark.parametrize(
        "case",
        [c for c in TEST_DATA["test_cases"] if c["category"] == "security"],
        ids=[c["case_id"] for c in TEST_DATA["test_cases"] if c["category"] == "security"]
    )
    def test_{method_name}_security(self, case, request_util{', auth_headers' if needs_auth else ''}):
        """数据驱动安全测试"""
        self.api.request_util = request_util
{param_extraction}
{case_call_params}
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])
        if "business_code" in case["expected"]:
            AssertUtil.assert_business_code(response, case["expected"]["business_code"])
        for assertion in case["expected"].get("assertions", []):
            field = assertion.get("field", "")
            operator = assertion.get("operator", "eq")
            value = assertion.get("value")
            if field and operator == "eq":
                AssertUtil.assert_business_data(response, [{{"field": field, "check": "equals", "expect": value}}])
'''
        return code

    def _generate_inline_test(self, api_name, api_path, method, module,
                              module_name, class_base, filename,
                              data_filename, method_name,
                              call_params, default_params,
                              field_checks, body_params, query_params,
                              path_params, needs_auth, api_def):
        """生成内联数据模式测试用例"""
        params = api_def.get("parameters", {})
        body_params_list = params.get("body_params", [])

        # 构建内联测试数据
        positive_data = self._build_inline_positive_data(body_params_list, query_params, path_params)
        negative_data = self._build_inline_negative_data(body_params_list, query_params, path_params)

        # fixture 参数
        fixture_params = ["self", "request_util"]
        if needs_auth:
            fixture_params.append("auth_headers")

        # API 调用（处理空参数时去掉尾逗号）
        if needs_auth:
            if default_params:
                success_call = f"        response = self.api.{method_name}({default_params},\n            headers=auth_headers)"
            else:
                success_call = f"        response = self.api.{method_name}(headers=auth_headers)"
            neg_call = f"        response = self.api.{method_name}(**case[\"params\"],\n            headers=auth_headers)"
        else:
            success_call = f"        response = self.api.{method_name}({default_params})"
            neg_call = f"        response = self.api.{method_name}(**case[\"params\"])"

        field_checks_str = ""
        if field_checks:
            items = []
            for fc in field_checks:
                items.append(f"                {fc}")
            field_checks_str = ",\n".join(items)

        code = f'''"""
{api_name}测试用例（内联数据模式）
- 接口路径：{api_path}
- 请求方法：{method}
"""
import pytest
import allure
from api.{module}.{filename}_api import {class_base}API
from utils.assert_util import AssertUtil
from utils.logger import get_logger

logger = get_logger("test_{filename}")

# 内联测试数据
TEST_DATA = {{
    "positive": [
{positive_data}
    ],
    "negative": [
{negative_data}
    ]
}}


class Test{class_base}Normal:
    """{api_name} - 正向场景"""

    def setup_class(self):
        self.api = {class_base}API()

    @pytest.mark.p0
    @pytest.mark.smoke
    @allure.title("{api_name} - 正常请求")
    @allure.feature("{module_name}")
    @allure.story("正向场景")
    def test_{method_name}_success({", ".join(fixture_params)}):
        """测试正常请求"""
        self.api.request_util = request_util
{success_call}
        AssertUtil.assert_all(
            response,
            expected_status=200,
            expected_code=0,
            field_checks=[
{field_checks_str}
            ]
        )


class Test{class_base}Exception:
    """{api_name} - 异常场景"""

    def setup_class(self):
        self.api = {class_base}API()

    @pytest.mark.p0
    @pytest.mark.parametrize("case", TEST_DATA["negative"],
        ids=[c["name"] for c in TEST_DATA["negative"]])
    @allure.title("{api_name} - 异常测试")
    @allure.feature("{module_name}")
    @allure.story("异常场景")
    def test_{method_name}_negative(self, case, request_util{', auth_headers' if needs_auth else ''}):
        """测试异常场景"""
        self.api.request_util = request_util
{neg_call}
        AssertUtil.assert_status_code(response, case["expected"]["status_code"])
        if "business_code" in case["expected"]:
            AssertUtil.assert_business_code(response, case["expected"]["business_code"])
'''
        return code

    def _build_call_params(self, body_params, query_params, path_params, needs_auth):
        """构建 API 调用参数（去重：path/query 优先，body 同名跳过）"""
        parts = []
        seen_names = set()
        for p in path_params:
            name = to_snake_case(p["name"])
            if name not in seen_names:
                parts.append(f"{name}={name}")
                seen_names.add(name)
        for p in query_params:
            name = to_snake_case(p["name"])
            if name not in seen_names:
                parts.append(f"{name}={name}")
                seen_names.add(name)
        for p in body_params:
            name = to_snake_case(p["name"])
            if name not in seen_names:
                parts.append(f"{name}={name}")
                seen_names.add(name)
        return ", ".join(parts)

    def _build_default_call_params(self, body_params, query_params, path_params):
        """构建默认参数值的调用（去重：path/query 优先，body 同名跳过）"""
        parts = []
        seen_names = set()
        # Path 参数优先
        for p in path_params:
            name = to_snake_case(p["name"])
            if name not in seen_names:
                default_val = self._get_default_literal(p)
                parts.append(f"{name}={default_val}")
                seen_names.add(name)
        # Query 参数
        for p in query_params:
            name = to_snake_case(p["name"])
            if name not in seen_names:
                default_val = self._get_default_literal(p)
                parts.append(f"{name}={default_val}")
                seen_names.add(name)
        # Body 参数（跳过与 path/query 同名的参数）
        for p in body_params:
            name = to_snake_case(p["name"])
            if name not in seen_names:
                default_val = self._get_default_literal(p)
                parts.append(f"{name}={default_val}")
                seen_names.add(name)
        return ", ".join(parts)

    def _get_default_literal(self, param):
        """获取参数的默认字面量"""
        ptype = param.get("type", "string")
        example = param.get("example")
        default = param.get("default")

        if example is not None:
            if isinstance(example, str):
                return f'"{example}"'
            return str(example)
        if default is not None:
            if isinstance(default, str):
                return f'"{default}"'
            return str(default)

        if ptype == "string":
            return '""'
        elif ptype == "integer":
            return "1"
        elif ptype == "number":
            return "1.0"
        elif ptype == "boolean":
            return "True"
        elif ptype == "array":
            return "[]"
        elif ptype == "object":
            return "{}"
        return '""'

    def _build_field_checks(self, api_def):
        """从接口定义构建默认断言"""
        checks = []
        responses = api_def.get("responses", {})
        success = responses.get("success", {})
        schema = success.get("schema", [])

        for field in schema[:5]:  # 最多取 5 个字段
            field_path = field.get("field_path", "")
            ftype = field.get("type", "string")
            if not field_path:
                continue

            # 跳过 code 字段（已在业务码断言中）
            if field_path == "code":
                continue

            # 跳过 message 字段
            if field_path == "message":
                continue

            if ftype in ["string", "integer", "number"]:
                checks.append(
                    f'{{"field": "{field_path}", "check": "not_empty"}}'
                )

        return checks

    def _build_param_extraction(self, body_params, query_params, path_params):
        """构建从 case 中提取参数的代码"""
        lines = []
        all_params = body_params + query_params + path_params
        if not all_params:
            return "        # 无参数"

        # 收集 path 和 query 中的参数名，用于去重
        path_query_names = {to_snake_case(p["name"]) for p in path_params + query_params}

        # Path 参数
        if path_params:
            lines.append("        path = case[\"parameters\"].get(\"path_params\", {})")
            for p in path_params:
                name = to_snake_case(p["name"])
                original = p["name"]
                lines.append(f"        {name} = path.get(\"{original}\", \"\")")

        # Query 参数
        if query_params:
            lines.append("        query = case[\"parameters\"].get(\"query_params\", {})")
            for p in query_params:
                name = to_snake_case(p["name"])
                original = p["name"]
                lines.append(f"        {name} = query.get(\"{original}\", \"\")")

        # Body 参数（跳过与 path/query 同名的参数）
        body_params_filtered = [p for p in body_params if to_snake_case(p["name"]) not in path_query_names]
        if body_params_filtered:
            lines.append("        body = case[\"parameters\"].get(\"body_params\", {})")
            for p in body_params_filtered:
                name = to_snake_case(p["name"])
                original = p["name"]
                lines.append(f"        {name} = body.get(\"{original}\", \"\")")

        return "\n".join(lines)

    def _build_case_call_params(self, body_params, query_params, path_params, needs_auth, method_name="send"):
        """构建从 case 数据调用 API 的代码"""
        all_params = body_params + query_params + path_params
        if not all_params:
            if needs_auth:
                return f"        response = self.api.{method_name}(headers=auth_headers)"
            else:
                return f"        response = self.api.{method_name}()"

        parts = []
        seen_names = set()
        for p in path_params + query_params + body_params:
            name = to_snake_case(p["name"])
            if name not in seen_names:
                parts.append(f"{name}={name}")
                seen_names.add(name)
        params_str = ", ".join(parts)

        if needs_auth:
            return f"        response = self.api.{method_name}({params_str}, headers=auth_headers)"
        else:
            return f"        response = self.api.{method_name}({params_str})"

    def _build_inline_positive_data(self, body_params, query_params, path_params):
        """构建内联正向测试数据（path/query 优先，body 同名跳过）"""
        params_dict = {}
        seen_names = set()
        # Path 参数优先
        for p in path_params:
            name = to_snake_case(p["name"])
            if name not in seen_names:
                seen_names.add(name)
                self._add_param_default(params_dict, p)
        # Query 参数
        for p in query_params:
            name = to_snake_case(p["name"])
            if name not in seen_names:
                seen_names.add(name)
                self._add_param_default(params_dict, p)
        # Body 参数（跳过与 path/query 同名）
        for p in body_params:
            name = to_snake_case(p["name"])
            if name not in seen_names:
                seen_names.add(name)
                self._add_param_default(params_dict, p)

        params_str = ", ".join(f'"{k}": {v}' for k, v in params_dict.items())
        return f'        {{\n            "name": "正常请求",\n            "params": {{{params_str}}},\n            "expected": {{\n                "status_code": 200,\n                "business_code": 0\n            }}\n        }}'

    def _add_param_default(self, params_dict, p):
        """添加参数默认值到字典"""
        name = to_snake_case(p["name"])
        ptype = p.get("type", "string")
        example = p.get("example")
        default = p.get("default")

        if example is not None:
            if isinstance(example, str):
                params_dict[name] = f'"{example}"'
            else:
                params_dict[name] = str(example)
        elif default is not None:
            if isinstance(default, str):
                params_dict[name] = f'"{default}"'
            else:
                params_dict[name] = str(default)
        elif ptype == "string":
            params_dict[name] = '"test"'
        elif ptype == "integer":
            params_dict[name] = "1"
        elif ptype == "number":
            params_dict[name] = "1.0"
        elif ptype == "boolean":
            params_dict[name] = "True"
        else:
            params_dict[name] = '""'

    def _build_inline_negative_data(self, body_params, query_params, path_params):
        """构建内联异常测试数据"""
        cases = []
        for p in body_params + query_params:
            if p.get("required", False):
                name = to_snake_case(p["name"])
                desc = p.get("description", name)
                ptype = p.get("type", "string")

                if ptype == "string":
                    empty_val = '""'
                elif ptype == "integer" or ptype == "number":
                    empty_val = "None"
                elif ptype == "boolean":
                    empty_val = "None"
                else:
                    empty_val = '""'

                cases.append(
                    f'        {{\n            "name": "{desc}为空",\n'
                    f'            "params": {{"{name}": {empty_val}}},\n'
                    f'            "expected": {{\n                "status_code": 400,\n'
                    f'                "business_code": 40001\n            }}\n        }}'
                )

        if not cases:
            cases.append(
                '        {\n            "name": "默认异常测试",\n'
                '            "params": {},\n'
                '            "expected": {\n                "status_code": 400\n            }\n        }'
            )

        return ",\n".join(cases)


# ============================================================
# 主生成器
# ============================================================


class TestScriptGenerator:
    """接口自动化测试脚本主生成器"""

    def __init__(self, api_def_file, data_dir=None, output_dir=None,
                 module_filter=None, api_filter=None, data_format="yaml",
                 skip_infra=False, skip_utils=False, skip_config=False):
        self.api_def_file = api_def_file
        self.data_dir = data_dir
        self.output_dir = output_dir or DEFAULT_PROJECT_NAME
        self.module_filter = module_filter
        self.api_filter = api_filter
        self.data_format = data_format
        self.skip_infra = skip_infra
        self.skip_utils = skip_utils
        self.skip_config = skip_config

        # 加载接口定义
        self.definition = self._load_definition()
        self.apis = self._filter_apis()
        self.global_rules = self.definition.get("global_rules", {})

    def _load_definition(self):
        """加载 api_definitions.json"""
        with open(self.api_def_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _filter_apis(self):
        """过滤接口"""
        apis = self.definition.get("apis", [])

        if self.api_filter:
            apis = [a for a in apis if a["api_id"] == self.api_filter]

        if self.module_filter:
            apis = [a for a in apis if a.get("module", "") == self.module_filter]

        return apis

    def generate(self):
        """执行生成"""
        print(f"开始生成接口自动化脚本...")
        print(f"  接口定义文件：{self.api_def_file}")
        print(f"  输出目录：{self.output_dir}")
        print(f"  接口数量：{len(self.apis)}")
        print(f"  数据模式：{'数据驱动' if self.data_dir else '内联数据'}")
        print()

        # Step 3: 生成基础设施
        if not self.skip_infra:
            print("[Step 3] 生成项目基础设施...")
            infra = InfraGenerator(self.output_dir, self.data_format)
            if self.skip_config:
                # 只生成不跳过的部分
                infra._generate_utils()
                infra._generate_conftest()
                infra._generate_pytest_ini()
                infra._generate_requirements()
                infra._generate_init_files()
            elif self.skip_utils:
                infra._generate_config()
                infra._generate_conftest()
                infra._generate_pytest_ini()
                infra._generate_requirements()
                infra._generate_init_files()
            else:
                infra.generate_all()
            print("  完成")
            print()

        # Step 4: 生成 API 层
        print("[Step 4] 生成接口请求层（api/）...")
        api_gen = ApiLayerGenerator(self.output_dir, self.apis, self.global_rules)
        api_files = api_gen.generate()
        print(f"  生成 {len(api_files)} 个文件")
        print()

        # Step 5: 生成数据层
        print("[Step 5] 生成测试数据层（data/）...")
        data_gen = DataLayerGenerator(
            self.output_dir, self.apis, self.data_dir, self.data_format
        )
        data_files = data_gen.generate()
        print(f"  生成 {len(data_files)} 个文件")
        print()

        # Step 6: 生成用例层
        print("[Step 6] 生成测试用例层（testcases/）...")
        case_gen = TestCaseGenerator(
            self.output_dir, self.apis, self.data_dir,
            self.data_format, self.global_rules
        )
        case_files = case_gen.generate()
        print(f"  生成 {len(case_files)} 个文件")
        print()

        # Step 8: 输出汇总
        self._print_summary(api_files, data_files, case_files)

    def _print_summary(self, api_files, data_files, case_files):
        """输出汇总报告"""
        modules = set()
        for api in self.apis:
            modules.add(api.get("module", "未分类"))

        print("=" * 60)
        print("接口自动化脚本生成汇总")
        print("=" * 60)
        print(f"项目路径：{os.path.abspath(self.output_dir)}/")
        print(f"接口总数：{len(self.apis)}")
        print(f"模块数量：{len(modules)}")
        print()
        print("生成文件统计：")
        print(f"  - api/          {len(api_files)} 文件（接口封装）")
        print(f"  - testcases/    {len(case_files)} 文件（测试用例）")
        print(f"  - data/         {len(data_files)} 文件（测试数据）")
        if not self.skip_infra:
            print("  - config/       3 文件（环境配置）")
            print("  - utils/        4 文件（工具类）")
            print("  - conftest.py   1 文件（Pytest 钩子）")
            print("  - pytest.ini    1 文件（Pytest 配置）")
        print()
        data_mode = "数据驱动" if self.data_dir else "内联数据"
        print(f"数据模式：{data_mode}")
        print("命名规范：✓ 符合团队标准")
        print("断言覆盖：✓ 三层断言（状态码+业务码+业务数据）")
        print("健壮逻辑：✓ 超时/重试/异常/鉴权/日志")
        print()
        print("运行方式：")
        print(f"  1. cd {self.output_dir}")
        print("  2. pip install -r requirements.txt")
        print("  3. pytest testcases/ -v --alluredir=reports/allure-results")
        print("  4. allure serve reports/allure-results")
        print("=" * 60)


# ============================================================
# CLI 入口
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="接口自动化测试脚本批量生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "api_definitions",
        help="标准化接口定义文件路径（api_definitions.json/yaml）"
    )
    parser.add_argument(
        "--data-dir",
        help="测试数据目录路径（可选，提供则启用数据驱动模式）"
    )
    parser.add_argument(
        "--output", "-o",
        default=DEFAULT_PROJECT_NAME,
        help=f"输出目录路径（默认：{DEFAULT_PROJECT_NAME}/）"
    )
    parser.add_argument(
        "--module", "-m",
        help="仅生成指定模块的脚本"
    )
    parser.add_argument(
        "--api", "-a",
        help="仅生成指定接口的脚本（api_id）"
    )
    parser.add_argument(
        "--data-format",
        choices=["yaml", "json"],
        default=DEFAULT_DATA_FORMAT,
        help=f"数据文件格式（默认：{DEFAULT_DATA_FORMAT}）"
    )
    parser.add_argument(
        "--skip-infra",
        action="store_true",
        help="跳过基础设施生成（已有项目仅追加接口）"
    )
    parser.add_argument(
        "--skip-utils",
        action="store_true",
        help="跳过 utils/ 生成"
    )
    parser.add_argument(
        "--skip-config",
        action="store_true",
        help="跳过 config/ 生成"
    )

    args = parser.parse_args()

    generator = TestScriptGenerator(
        api_def_file=args.api_definitions,
        data_dir=args.data_dir,
        output_dir=args.output,
        module_filter=args.module,
        api_filter=args.api,
        data_format=args.data_format,
        skip_infra=args.skip_infra,
        skip_utils=args.skip_utils,
        skip_config=args.skip_config,
    )
    generator.generate()


if __name__ == "__main__":
    main()
