# 团队编码规范

## 一、目录结构规范

### 标准项目结构

```
api_auto_project/
├── config/             # 环境配置、全局常量
│   ├── dev.yaml        # 开发环境
│   ├── test.yaml       # 测试环境
│   ├── pre.yaml        # 预发布环境
│   ├── prod.yaml       # 生产环境
│   └── config.py       # 配置加载模块
├── api/                # 接口请求层（封装所有接口）
│   ├── __init__.py
│   ├── user_api.py     # 用户模块接口
│   ├── auth_api.py     # 认证模块接口
│   └── ...
├── testcases/          # 测试用例层
│   ├── __init__.py
│   ├── test_user_login.py
│   └── ...
├── data/               # 测试数据（数据驱动）
│   ├── auth/
│   │   └── user_login_data.yaml
│   └── ...
├── utils/              # 工具类
│   ├── __init__.py
│   ├── logger.py
│   ├── request_util.py
│   ├── assert_util.py
│   └── token_util.py
├── reports/            # 报告输出
│   ├── logs/
│   └── allure-results/
├── conftest.py         # Pytest 全局钩子
├── pytest.ini          # Pytest 配置
└── requirements.txt    # 依赖
```

### 分层原则

| 原则 | 说明 |
|------|------|
| 接口只封装在 `api/` 层 | 所有 HTTP 请求的构建和发送只在 API 层完成 |
| 用例只写在 `testcases/` 层 | 测试逻辑、断言、数据加载只在用例层完成 |
| 数据只放 `data/` 层 | 测试数据文件独立存放，用例通过工具加载 |
| 工具统一放 `utils/` | 日志、请求、断言、鉴权等通用逻辑统一封装 |
| 禁止混用层级 | API 层不做断言，用例层不直接发请求，数据层不含逻辑 |
| 禁止硬编码 | URL、超时、重试次数等必须使用配置常量 |

## 二、命名规范

### 包 / 目录

| 规则 | 说明 |
|------|------|
| 小写字母 + 下划线 | 简洁清晰，无大写、无空格、无特殊字符 |
| 语义明确 | 目录名体现业务含义 |

| 目录 | 含义 |
|------|------|
| `api/` | 接口封装层 |
| `config/` | 配置层 |
| `utils/` | 工具层 |
| `testcases/` | 用例层 |
| `data/` | 数据层 |
| `reports/` | 报告层 |

### 文件名

| 规则 | 说明 |
|------|------|
| 小写字母 + 下划线 | 统一风格 |
| 一个接口对应一个文件 | 文件名与接口业务保持一致 |
| API 层后缀 `_api.py` | 如 `user_api.py` |
| 用例层前缀 `test_` | 如 `test_user_login.py` |
| 数据层后缀 `_data.yaml` | 如 `user_login_data.yaml` |

| 类型 | 示例 |
|------|------|
| API 层 | `user_api.py`、`order_api.py`、`product_api.py` |
| 用例层 | `test_user_login.py`、`test_order_create.py` |
| 数据层 | `user_login_data.yaml`、`order_create_data.yaml` |

### 类名

| 规则 | 说明 |
|------|------|
| 大驼峰命名法（UpperCamelCase） | 每个单词首字母大写 |
| 语义明确 | 类名体现业务或场景 |
| API 层以 `API` 结尾 | 如 `UserAPI` |
| 用例层以 `Test` 开头 + 场景后缀 | 如 `TestUserLoginNormal` |

| 层级 | 示例 |
|------|------|
| API 层 | `UserAPI`、`OrderAPI`、`AuthAPI` |
| 用例层-正常 | `TestUserLoginNormal` |
| 用例层-异常 | `TestUserLoginException` |
| 用例层-边界 | `TestUserLoginBoundary` |
| 用例层-安全 | `TestUserLoginSecurity` |

### 方法名

| 规则 | 说明 |
|------|------|
| 小写字母 + 下划线 | 统一风格 |
| 语义简短精准 | 方法名体现操作含义 |
| 公共方法必须抽离到 utils | 不允许在用例中重复编写 |

| 层级 | 示例 |
|------|------|
| API 层 | `login()`、`get_user_info()`、`create_order()` |
| 工具方法 | `get_token()`、`encrypt_params()`、`load_test_data()` |

### 测试方法名

| 规则 | 说明 |
|------|------|
| 必须以 `test_` 开头 | Pytest 识别规则 |
| 见名知意 | 清晰体现场景与预期结果 |
| 小写字母 + 下划线 | 统一风格 |

| 场景 | 示例 |
|------|------|
| 正常成功 | `test_login_success` |
| 参数错误 | `test_login_password_error` |
| 参数为空 | `test_login_mobile_empty` |
| 边界值 | `test_login_password_min_length` |
| SQL 注入 | `test_login_sql_injection` |

### 变量名

| 规则 | 说明 |
|------|------|
| 小写字母 + 下划线 | 统一风格 |
| 命名直观 | 不使用单字母、不使用歧义缩写 |

| 示例 | 含义 |
|------|------|
| `username` | 用户名 |
| `token` | 认证令牌 |
| `headers` | 请求头 |
| `response` | 响应对象 |
| `order_id` | 订单ID |
| `page` | 页码 |
| `size` | 每页条数 |

### 常量

| 规则 | 说明 |
|------|------|
| 全大写字母 + 下划线 | 区分于变量 |
| 集中存放于配置文件 | 禁止在脚本中硬编码 |

| 常量 | 含义 |
|------|------|
| `BASE_URL` | 基础URL |
| `TIMEOUT` | 超时时间 |
| `MAX_RETRY` | 最大重试次数 |
| `CONTENT_TYPE` | 内容类型 |

## 三、注释规范

### 文件头注释

每个 Python 文件必须包含文件头注释：

```python
"""
{模块名称}
- 功能描述
- 接口路径（API 层）
"""
```

### 类注释

```python
class UserAPI:
    """用户接口封装"""
```

### 方法注释

```python
def login(self, username, password, headers=None):
    """
    用户登录
    - 接口路径：/api/auth/login
    - 请求方法：POST
    :param username: 用户名
    :param password: 密码
    :param headers: 自定义请求头
    :return: Response 对象
    """
```

### 测试方法注释

```python
def test_login_success(self, request_util, auth_headers):
    """测试正常登录"""
```

## 四、导入规范

### 导入顺序

1. 标准库（`import os`、`import time`）
2. 第三方库（`import pytest`、`import allure`）
3. 本项目模块（`from config.config import ...`、`from utils.request_util import ...`）

### 禁止

- 禁止使用 `from module import *`
- 禁止在 API 层导入 `pytest` 或 `allure`
- 禁止在 utils 层导入业务 API 类

## 五、依赖管理

### requirements.txt

```
requests>=2.28.0
pytest>=7.0.0
allure-pytest>=2.12.0
PyYAML>=6.0
pytest-rerunfailures>=11.0
```

### 版本约束

- Python 3.9+
- 所有依赖使用 `>=` 最小版本约束
- 不锁定具体小版本号，保持兼容性

## 六、禁止事项

| 禁止 | 说明 |
|------|------|
| 禁止混用层级 | API 层不做断言，用例层不直接发请求 |
| 禁止硬编码 | 所有配置项必须通过配置文件或常量管理 |
| 禁止使用 `import *` | 显式导入，避免命名冲突 |
| 禁止在用例中封装请求逻辑 | 请求封装必须在 API 层 |
| 禁止在 API 层做断言 | 断言逻辑必须在用例层 |
| 禁止单字母变量 | 除循环变量外，禁止 `a`、`b`、`x` 等命名 |
| 禁止魔法数字 | 超时 30、重试 2 等必须使用常量 |
