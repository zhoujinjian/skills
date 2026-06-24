# UI 测试标签规范与打标签规则参考

本文档是 `ui-test-tagger` 技能的完整标签规范参考。当需要了解具体标签定义、识别规则、冲突规则、装饰器映射时加载此文件。

## 标签体系

### 1. 优先级标签

| 标签 | 含义 | 判定依据 |
|------|------|----------|
| P0 | 核心链路 | 登录、注册、下单、支付、结账等关键路径 |
| P1 | 重要功能 | 主要业务流程的非核心分支 |
| P2 | 一般功能 | 辅助功能、配置管理、统计查询 |
| P3 | 边缘场景 | 罕见操作、极端异常、兼容性边缘 |

**优先级判定规则（按优先级排列）：**
1. pages.yaml 中页面标记了 `priority` 字段 → 按标记
2. 页面 URL 路径匹配核心链路模式 → P0
3. 方法名/docstring 含核心业务关键词（login/register/create_order/pay/checkout/full_flow）→ P0
4. 方法名/docstring 含通用业务关键词（update/modify/search/list/browse）→ P1
5. 方法名/docstring 含管理/配置关键词（admin/config/stats/dashboard）→ P2/P3
6. 默认 → P1

### 2. 模块标签

| 标签 | 对应路径/关键词模式 |
|------|---------------------|
| module:login | /login, /signin, /auth, /logout, login_page, LoginPage |
| module:product | /product, /products, /category, /categories, /search, /goods, /item |
| module:cart | /cart, /basket, /shopping-cart |
| module:order | /order, /orders, /my-orders, /order-list |
| module:checkout | /checkout, /settle, /place-order |
| module:user | /user, /profile, /account, /member |
| module:address | /address, /addresses, /shipping, /location |
| module:payment | /payment, /pay, /refund, /transaction |
| module:admin | /admin, /manage, /dashboard, /config, /stats, /statistics |

**模块判定规则（按优先级排列）：**
1. pages.yaml 中页面声明的 `module` 字段 → 对应模块
2. 测试方法内 `page.goto(url)` 的 URL 路径模式匹配 → 对应模块
3. 测试类名含模块关键词（如 `TestLoginPage`、`CheckoutPage`）→ 对应模块
4. 文件路径含模块关键词（如 `testcases/order/test_checkout.py`）→ 对应模块

### 3. 场景标签

| 标签 | 触发关键词模式 |
|------|---------------|
| scene:positive | success, valid, normal, correct, happy, ok, pass, complete, *_successfully |
| scene:negative | error, invalid, fail, exception, not_found, unauthorized, forbidden, missing, empty, wrong, deny, reject |
| scene:boundary | boundary, limit, min, max, edge, overflow, underflow, extreme, threshold, zero, too_long, too_short |
| scene:full_flow | full_flow, end_to_end, e2e, complete_flow, full_shopping, whole_flow, business_flow |
| scene:visual_regress | visual, screenshot, regress, snapshot, pixel_diff, layout_check, responsive |

**场景判定规则（按优先级排列）：**
1. 测试方法名正则匹配（full_flow > visual_regress > boundary > negative > positive）→ 对应场景
2. docstring 含场景关键词（含中文「全流程」「端到端」「视觉回归」「边界」「异常」）→ 对应场景
3. 默认 → scene:positive

**为什么 full_flow 优先级最高**：UI 测试中端到端全流程通常横跨多个页面（登录→浏览→加购→下单→支付），方法名中可能同时包含 success 等正向词，必须优先识别为 full_flow 以便调度时单独编排。

### 4. 页面类型标签

| 标签 | 路径特征 | 说明 |
|------|---------|------|
| page:home | `/`, `/home`, `/index` | 站点首页/门户 |
| page:list | `/list`, `/search`, `/products`, `/category`, `/orders` | 列表/搜索页 |
| page:detail | `/detail`, `/info`, `/item/[id]`, `/order/[id]` | 详情页（含动态 ID 段） |
| page:form | `/login`, `/register`, `/create`, `/edit`, `/add`, `/checkout`, `/address/edit` | 表单页 |
| page:dialog | 测试涉及 dialog/modal/popup/alert | 弹窗类 |

**页面类型判定规则（按优先级排列）：**
1. pages.yaml 中页面声明的 `page_type` 字段 → 对应类型
2. 测试方法涉及 dialog/modal/popup/alert → page:dialog
3. URL 路径匹配表单路径模式（含 create/edit/add/login/register/checkout）→ page:form
4. URL 路径匹配详情路径模式（含 detail/info 或动态 ID 段 `/\d+`、`/[a-z0-9_-]{8,}`）→ page:detail
5. URL 路径匹配列表路径模式（含 list/search/products/category/orders）→ page:list
6. URL 路径为根路径或 /home/index → page:home
7. 默认 → page:list（UI 测试最常见页面类型）

### 5. 执行策略标签

| 标签 | 判定规则 |
|------|---------|
| run:smoke | P0 + scene:positive（或 scene:full_flow 中的关键链路） |
| run:regression | P0 或 P1 |
| run:full | 其余所有用例 |

**组合规则：**
- 冒烟测试筛选条件：`P0 and scene_positive and run_smoke`
- 回归测试筛选条件：`(P0 or P1) and run_regression`

### 6. 浏览器/平台标签

| 标签 | 含义 |
|------|------|
| browser:chrome | Chrome 浏览器 |
| browser:firefox | Firefox 浏览器 |
| browser:edge | Edge 浏览器 |
| browser:safari | Safari 浏览器 |
| browser:headless | 无头浏览器执行 |
| platform:windows | Windows 平台 |
| platform:linux | Linux 平台 |
| platform:mac | macOS 平台 |

浏览器/平台标签通常根据以下来源判定（按优先级）：
1. 命令行 `--browser` / `--platform` 参数强制预设
2. 测试脚本中的 `pytest.fixture` 浏览器参数化（`@pytest.mark.parametrize("browser_name", ["chrome", "firefox"])`）
3. `conftest.py` 中的浏览器配置引用
4. 默认不写入（仅在明确存在浏览器适配场景时才标记）

## 冲突检测规则

| 冲突标签 1 | 冲突标签 2 | 冲突原因 |
|-----------|-----------|---------|
| P0 | P3 | 优先级冲突：最高与最低优先级不应共存 |
| P0 | P2 | 优先级冲突：核心链路与一般功能不应共存 |
| P1 | P3 | 优先级冲突：重要功能与边缘场景不应共存 |
| scene:positive | scene:negative | 场景冲突：正向与异常不应共存 |
| scene:positive | scene:boundary | 场景冲突：正向与边界不应共存 |
| scene:positive | scene:visual_regress | 场景冲突：正向功能与视觉回归目的不同 |
| run:smoke | P3 | 策略冲突：冒烟用例不应为边缘场景 |
| run:smoke | scene:negative | 策略冲突：冒烟用例通常不含异常场景 |
| page:home | page:form | 页面冲突：同一方法不应跨多种页面类型 |

## 标签写入规范

### pytest 装饰器方式（推荐）

pytest 不支持含冒号的属性名，因此使用下划线格式：

```python
import pytest

class TestUserLogin:
    @pytest.mark.P0
    @pytest.mark.module_login
    @pytest.mark.scene_positive
    @pytest.mark.page_form
    @pytest.mark.run_smoke
    def test_login_success(self, page, base_url):
        """正常登录测试"""
        pass
```

### conftest.py 标记注册模板

在项目的 `conftest.py` 中注册自定义标记，避免 pytest 警告：

```python
# conftest.py
def pytest_configure(config):
    custom_markers = [
        # 优先级
        "P0: 核心链路（登录、下单、支付等关键路径）",
        "P1: 重要功能（主要业务流程的非核心分支）",
        "P2: 一般功能（辅助功能、配置管理）",
        "P3: 边缘场景（罕见操作、极端异常）",
        # 模块
        "module_login: 登录模块",
        "module_product: 商品模块",
        "module_cart: 购物车模块",
        "module_order: 订单模块",
        "module_checkout: 结账模块",
        "module_user: 用户中心模块",
        "module_address: 地址管理模块",
        "module_payment: 支付模块",
        "module_admin: 后台管理模块",
        # 场景
        "scene_positive: 正向场景",
        "scene_negative: 异常场景",
        "scene_boundary: 边界场景",
        "scene_full_flow: 端到端全流程",
        "scene_visual_regress: 视觉回归场景",
        # 页面类型
        "page_home: 首页",
        "page_list: 列表页",
        "page_detail: 详情页",
        "page_form: 表单页",
        "page_dialog: 弹窗页",
        # 执行策略
        "run_smoke: 冒烟测试",
        "run_regression: 回归测试",
        "run_full: 全量测试",
        # 浏览器/平台
        "browser_chrome: Chrome 浏览器",
        "browser_firefox: Firefox 浏览器",
        "browser_edge: Edge 浏览器",
        "browser_safari: Safari 浏览器",
        "browser_headless: 无头浏览器",
        "platform_windows: Windows 平台",
        "platform_linux: Linux 平台",
        "platform_mac: macOS 平台",
    ]
    for marker in custom_markers:
        config.addinivalue_line("markers", marker)
```

### 装饰器标签映射（含冒号标签的替代写法）

| 标准标签 | 装饰器写法 |
|---------|-----------|
| P0/P1/P2/P3 | @pytest.mark.P0 / P1 / P2 / P3 |
| module:login | @pytest.mark.module_login |
| module:product | @pytest.mark.module_product |
| module:cart | @pytest.mark.module_cart |
| module:order | @pytest.mark.module_order |
| module:checkout | @pytest.mark.module_checkout |
| module:user | @pytest.mark.module_user |
| module:address | @pytest.mark.module_address |
| module:payment | @pytest.mark.module_payment |
| module:admin | @pytest.mark.module_admin |
| scene:positive | @pytest.mark.scene_positive |
| scene:negative | @pytest.mark.scene_negative |
| scene:boundary | @pytest.mark.scene_boundary |
| scene:full_flow | @pytest.mark.scene_full_flow |
| scene:visual_regress | @pytest.mark.scene_visual_regress |
| page:home | @pytest.mark.page_home |
| page:list | @pytest.mark.page_list |
| page:detail | @pytest.mark.page_detail |
| page:form | @pytest.mark.page_form |
| page:dialog | @pytest.mark.page_dialog |
| run:smoke | @pytest.mark.run_smoke |
| run:regression | @pytest.mark.run_regression |
| run:full | @pytest.mark.run_full |
| browser:chrome | @pytest.mark.browser_chrome |
| browser:firefox | @pytest.mark.browser_firefox |
| browser:edge | @pytest.mark.browser_edge |
| browser:safari | @pytest.mark.browser_safari |
| browser:headless | @pytest.mark.browser_headless |
| platform:windows | @pytest.mark.platform_windows |
| platform:linux | @pytest.mark.platform_linux |
| platform:mac | @pytest.mark.platform_mac |

### 旧标记兼容映射

| 已有小写/简写标记 | 标准标签 |
|------------------|---------|
| p0 | P0 |
| p1 | P1 |
| p2 | P2 |
| p3 | P3 |
| smoke | run:smoke |
| regression | run:regression |
| full | run:full |

写入时会自动将旧标记替换为标准下划线标记。

### docstring 标签方式（备用）

```python
class TestUserLogin:
    def test_login_success(self, page, base_url):
        """正常登录测试

        Tags: P0, module:login, scene:positive, page:form, run:smoke
        """
        pass
```

## 标签补全建议

每个测试方法必须包含以下 5 类必填标签：
1. **优先级标签**（P0/P1/P2/P3）— 必填
2. **模块标签**（module:xxx）— 必填
3. **场景标签**（scene:xxx）— 必填
4. **页面类型标签**（page:xxx）— 必填
5. **执行策略标签**（run:xxx）— 必填

可选标签：
6. **浏览器标签**（browser:xxx）— 仅跨浏览器适配场景标记
7. **平台标签**（platform:xxx）— 仅跨平台适配场景标记

缺失任一必填标签将出现在统计报告的「标签补全建议」清单中。

## pages.yaml 辅助信息字段

pages.yaml 中可声明以下字段辅助标签推断（可选）：

```yaml
pages:
  - name: LoginPage
    url: /login
    module: login          # 辅助 module 标签
    page_type: form        # 辅助 page 标签
    priority: P0           # 辅助 priority 标签
  - name: OrderCreatePage
    url: /order/create
    module: order
    page_type: form
    priority: P0
```

字段缺失时，标签推荐会回退到基于 URL/类名/方法名的启发式推断。
