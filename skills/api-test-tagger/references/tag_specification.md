# 标签规范与打标签规则参考

## 标签体系

### 1. 优先级标签

| 标签 | 含义 | 判定依据 |
|------|------|----------|
| P0 | 核心链路 | 登录、注册、下单、支付等关键路径 |
| P1 | 重要功能 | 主要业务流程的非核心分支 |
| P2 | 一般功能 | 辅助功能、配置管理、统计查询 |
| P3 | 边缘场景 | 罕见操作、极端异常 |

**优先级判定规则（按优先级排列）：**
1. 接口路径匹配核心链路模式 → P0
2. API定义文件中标记了 priority 字段 → 按标记
3. 方法名/docstring含核心业务关键词（login/register/create_order/pay/checkout）→ P0
4. 方法名/docstring含通用业务关键词（update/modify/search/list）→ P1
5. 方法名/docstring含管理/配置关键词（admin/config/stats/dashboard）→ P2/P3
6. 默认 → P1

### 2. 模块标签

| 标签 | 对应路径模式 |
|------|-------------|
| module:auth | /api/auth, /api/login, /api/register, /api/token, /api/logout |
| module:order | /api/order, /api/orders |
| module:product | /api/product, /api/products, /api/category, /api/categories, /api/search |
| module:cart | /api/cart |
| module:user | /api/user, /api/users, /api/profile, /api/account |
| module:address | /api/address, /api/addresses |
| module:payment | /api/payment, /api/pay, /api/refund |
| module:admin | /api/admin, /api/dashboard, /api/config, /api/stats, /api/statistics |

**模块判定规则（按优先级排列）：**
1. 请求URL路径匹配 → 按匹配的模块
2. 测试类名含模块关键词 → 按匹配的模块
3. 文件路径含模块关键词 → 按匹配的模块

### 3. 场景标签

| 标签 | 触发关键词模式 |
|------|---------------|
| scene:positive | success, valid, normal, correct, happy, ok, pass, *_successfully |
| scene:negative | error, invalid, fail, exception, not_found, unauthorized, forbidden, conflict, bad_request, missing, empty, null |
| scene:boundary | boundary, limit, min, max, edge, overflow, underflow, extreme, threshold, zero, too_long, too_short |
| scene:security | sql, xss, inject, attack, csrf, auth_bypass, privilege, malicious, sanitiz, hijack, token_exp |

**场景判定规则（按优先级排列）：**
1. 测试方法名正则匹配 → 按匹配的场景
2. docstring含场景关键词 → 按匹配的场景
3. 默认 → scene:positive

### 4. 执行策略标签

| 标签 | 判定规则 |
|------|---------|
| run:smoke | P0 + scene:positive |
| run:regression | P0 或 P1 |
| run:full | 其余所有用例 |

**组合规则：**
- 冒烟测试筛选条件: P0 + scene:positive + run:smoke
- 回归测试筛选条件: P0/P1 + run:regression

### 5. 环境标签

| 标签 | 含义 |
|------|------|
| env:dev | 开发环境 |
| env:test | 测试环境 |
| env:pre | 预发布环境 |
| env:prod | 生产环境 |

环境标签通常根据测试脚本中的配置引用（base_url、env配置等）自动判定。

## 冲突检测规则

| 冲突标签1 | 冲突标签2 | 冲突原因 |
|-----------|-----------|---------|
| P0 | P3 | 优先级冲突：最高与最低优先级不应共存 |
| P0 | P2 | 优先级冲突：核心链路与一般功能不应共存 |
| P1 | P3 | 优先级冲突：重要功能与边缘场景不应共存 |
| scene:positive | scene:negative | 场景冲突：正向与异常场景不应共存 |
| scene:positive | scene:boundary | 场景冲突：正向与边界场景不应共存 |
| run:smoke | P3 | 策略冲突：冒烟用例不应为边缘场景 |
| run:smoke | scene:negative | 策略冲突：冒烟用例通常不含异常场景 |

## 标签写入规范

### pytest 装饰器方式（推荐）

```python
import pytest

class TestUserLogin:
    @pytest.mark.P0
    @pytest.mark.module:auth
    @pytest.mark.scene:positive
    @pytest.mark.run:smoke
    def test_login_success(self):
        """正常登录测试"""
        pass
```

**注意：** pytest.mark 不支持含冒号的标签名作为属性，需使用 `@pytest.mark.parametrize` 方式或自定义标记注册。

### 推荐替代方案

在 `conftest.py` 中注册自定义标记：

```python
# conftest.py
def pytest_configure(config):
    custom_markers = [
        "P0: 核心链路",
        "P1: 重要功能",
        "P2: 一般功能",
        "P3: 边缘场景",
        "module_auth: 认证模块",
        "module_order: 订单模块",
        "module_product: 商品模块",
        "module_cart: 购物车模块",
        "module_user: 用户模块",
        "module_address: 地址模块",
        "module_payment: 支付模块",
        "module_admin: 管理模块",
        "scene_positive: 正向场景",
        "scene_negative: 异常场景",
        "scene_boundary: 边界场景",
        "scene_security: 安全场景",
        "run_smoke: 冒烟测试",
        "run_regression: 回归测试",
        "run_full: 全量测试",
    ]
    for marker in custom_markers:
        config.addinivalue_line("markers", marker)
```

### 装饰器标签映射（含冒号标签的替代写法）

| 标准标签 | 装饰器写法 |
|---------|-----------|
| module:auth | @pytest.mark.module_auth |
| module:order | @pytest.mark.module_order |
| module:product | @pytest.mark.module_product |
| module:cart | @pytest.mark.module_cart |
| module:user | @pytest.mark.module_user |
| module:address | @pytest.mark.module_address |
| module:payment | @pytest.mark.module_payment |
| module:admin | @pytest.mark.module_admin |
| scene:positive | @pytest.mark.scene_positive |
| scene:negative | @pytest.mark.scene_negative |
| scene:boundary | @pytest.mark.scene_boundary |
| scene:security | @pytest.mark.scene_security |
| run:smoke | @pytest.mark.run_smoke |
| run:regression | @pytest.mark.run_regression |
| run:full | @pytest.mark.run_full |
| env:dev | @pytest.mark.env_dev |
| env:test | @pytest.mark.env_test |
| env:pre | @pytest.mark.env_pre |
| env:prod | @pytest.mark.env_prod |

### docstring 标签方式（备用）

```python
class TestUserLogin:
    def test_login_success(self):
        """正常登录测试

        Tags: P0, module:auth, scene:positive, run:smoke
        """
        pass
```

## 标签补全建议

每个测试方法必须包含以下关键标签：
1. **优先级标签**（P0/P1/P2/P3）— 必填
2. **模块标签**（module:xxx）— 必填
3. **场景标签**（scene:xxx）— 必填
4. **执行策略标签**（run:xxx）— 必填
5. **环境标签**（env:xxx）— 选填，默认 env:test

缺失任一必填标签将出现在统计报告的「标签补全建议」清单中。
