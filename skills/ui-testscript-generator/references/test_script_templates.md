# 测试脚本模板与示例

本文件提供 Pytest 测试脚本的编写模板和完整示例。

---

## 目录

1. [标准测试脚本模板](#标准测试脚本模板)
2. [登录测试完整示例](#登录测试完整示例)
3. [注册测试示例](#注册测试示例)
4. [商品搜索测试示例](#商品搜索测试示例)
5. [参数化测试示例](#参数化测试示例)
6. [跨页面工作流测试示例](#跨页面工作流测试示例)

---

## 标准测试脚本模板

```python
# tests/<module>/test_<page_name>.py
import pytest
from playwright.sync_api import Page, expect


class TestPageName:
    """页面名称测试套件"""

    def test_<verb>_<expected_result>(self, page: Page):
        """测试简述"""
        # 1. 前置：导航到页面
        # 2. 执行：执行操作
        # 3. 断言：验证结果
        pass
```

---

## 登录测试完整示例

```python
# tests/auth/test_login.py
import pytest
from playwright.sync_api import Page, expect
from pages.auth.login_page import LoginPage
from pages.home_page import HomePage


class TestLogin:
    """登录功能测试"""

    def test_login_with_valid_credentials_shows_home_page(self, page: Page):
        """有效凭证登录成功后跳转首页"""
        # 执行
        home_page = (
            LoginPage(page)
            .navigate()
            .login("test_user", "Test@1234")
        )
        # 断言
        expect(page).to_have_url("/")
        expect(home_page.page).to_have_title("首页 - ShopLab")

    def test_login_with_empty_username_shows_error(self, page: Page):
        """用户名为空时显示错误提示"""
        # 执行
        login_page = LoginPage(page).navigate()
        login_page.fill_password("Test@1234").click_login()

        # 断言
        expect(page).to_have_url("/login")

    def test_login_with_empty_password_shows_error(self, page: Page):
        """密码为空时显示错误提示"""
        login_page = LoginPage(page).navigate()
        login_page.fill_username("test_user").click_login()

        expect(page).to_have_url("/login")

    def test_login_with_wrong_credentials_shows_error(self, page: Page):
        """错误凭证登录显示错误提示"""
        login_page = LoginPage(page).navigate()
        login_page.fill_username("wrong_user").fill_password("wrong_pass")
        login_page.click_login()

        expect(page).to_have_url("/login")

    def test_login_page_displays_all_elements(self, page: Page):
        """登录页所有核心元素可见"""
        login_page = LoginPage(page).navigate()

        expect(login_page._username_input).to_be_visible()
        expect(login_page._password_input).to_be_visible()
        expect(login_page._login_button).to_be_visible()

    def test_navigate_to_register_from_login(self, page: Page):
        """从登录页导航到注册页"""
        # 这里假设登录页有注册链接
        login_page = LoginPage(page).navigate()
        page.get_by_text("注册").click()

        expect(page).to_have_url("/register")


class TestLoginRemember:
    """登录记住我功能测试"""

    def test_login_with_remember_me_checked(self, page: Page):
        """勾选记住我后登录"""
        login_page = LoginPage(page).navigate()
        login_page.fill_username("test_user")
        login_page.fill_password("Test@1234")
        login_page.check_remember_me()
        login_page.click_login()

        expect(page).to_have_url("/")
```

---

## 注册测试示例

```python
# tests/auth/test_register.py
import pytest
from playwright.sync_api import Page, expect
from pages.auth.register_page import RegisterPage


class TestRegister:
    """注册功能测试"""

    def test_register_with_valid_data_succeeds(self, page: Page):
        """有效数据注册成功"""
        register_page = RegisterPage(page).navigate()
        register_page.fill_username("new_user_001")
        register_page.fill_password("Test@1234")
        register_page.fill_confirm_password("Test@1234")
        register_page.fill_email("new_user@example.com")
        register_page.fill_phone("13800138000")
        register_page.check_agreement()
        register_page.click_register()

        # 断言：注册成功跳转
        expect(page).to_have_url("/login")

    def test_register_with_mismatched_password_shows_error(self, page: Page):
        """两次密码不一致显示错误"""
        register_page = RegisterPage(page).navigate()
        register_page.fill_username("new_user_002")
        register_page.fill_password("Test@1234")
        register_page.fill_confirm_password("Different@1234")
        register_page.click_register()

        # 应停留在注册页
        expect(page).to_have_url("/register")

    def test_register_without_agreement_shows_error(self, page: Page):
        """未勾选协议无法注册"""
        register_page = RegisterPage(page).navigate()
        register_page.fill_username("new_user_003")
        register_page.fill_password("Test@1234")
        register_page.fill_confirm_password("Test@1234")
        register_page.fill_email("user003@example.com")
        register_page.fill_phone("13800138001")
        # 不勾选协议
        register_page.click_register()

        expect(page).to_have_url("/register")


class TestRegisterValidation:
    """注册表单校验测试"""

    @pytest.mark.parametrize("invalid_email", [
        "invalid",
        "@example.com",
        "user@",
        "",
    ])
    def test_register_with_invalid_email_shows_error(self, page: Page, invalid_email: str):
        """无效邮箱格式校验"""
        register_page = RegisterPage(page).navigate()
        register_page.fill_email(invalid_email)
        register_page.fill_username("test")  # 触发校验

        # 停留在注册页
        expect(page).to_have_url("/register")
```

---

## 商品搜索测试示例

```python
# tests/product/test_search.py
import pytest
from playwright.sync_api import Page, expect
from pages.product.product_list_page import ProductListPage


class TestSearch:
    """商品搜索功能测试"""

    def test_search_with_keyword_shows_results(self, page: Page):
        """关键词搜索返回结果"""
        list_page = ProductListPage(page).navigate()

        # 使用页头搜索
        page.get_by_placeholder("搜索商品").fill("手机")
        page.locator(".search-box button").click()

        expect(page).to_have_url("/search")

    def test_filter_by_price_range(self, page: Page):
        """价格区间筛选"""
        list_page = ProductListPage(page).navigate()
        list_page.fill_price_range("100", "5000")

        # 验证列表更新
        assert list_page.get_product_count() >= 0

    def test_sort_by_price_ascending(self, page: Page):
        """价格升序排序"""
        list_page = ProductListPage(page).navigate()
        list_page.sort_by("价格升序")

        # 验证排序生效（页面不报错即视为成功）
        expect(page.locator(".product-item, .product-card").first).to_be_visible()

    @pytest.mark.parametrize("category", [
        "数码产品",
        "服装鞋帽",
        "家居用品",
    ])
    def test_filter_by_category(self, page: Page, category: str):
        """分类筛选"""
        list_page = ProductListPage(page).navigate()
        list_page.select_category(category)

        # 验证筛选后页面正常
        expect(page).to_have_url("/product")
```

---

## 参数化测试示例

```python
# tests/auth/test_login_parametrize.py
import pytest
from playwright.sync_api import Page, expect
from pages.auth.login_page import LoginPage


class TestLoginParameterized:
    """登录参数化测试"""

    @pytest.mark.parametrize("username,password,expected_result", [
        ("test_user", "Test@1234", "success"),
        ("", "Test@1234", "error"),
        ("test_user", "", "error"),
        ("wrong_user", "wrong_pass", "error"),
        ("", "", "error"),
    ], ids=[
        "valid_credentials",
        "empty_username",
        "empty_password",
        "wrong_credentials",
        "both_empty",
    ])
    def test_login_scenarios(self, page: Page, username: str, password: str, expected_result: str):
        """多场景登录测试"""
        login_page = LoginPage(page).navigate()
        login_page.fill_username(username).fill_password(password)
        login_page.click_login()

        if expected_result == "success":
            expect(page).to_have_url("/")
        else:
            expect(page).to_have_url("/login")
```

---

## 跨页面工作流测试示例

```python
# tests/workflows/test_shopping_journey.py
import pytest
from playwright.sync_api import Page, expect
from pages.auth.login_page import LoginPage
from pages.product.product_detail_page import ProductDetailPage
from pages.product.product_list_page import ProductListPage


class TestShoppingJourney:
    """购物全流程测试"""

    def test_browse_product_and_add_to_cart(self, page: Page, auth_page):
        """浏览商品并加入购物车（已登录状态）"""
        # 1. 进入商品列表
        list_page = ProductListPage(page).navigate()
        expect(page).to_have_url("/product")

        # 2. 点击商品进入详情
        detail_page = list_page.click_product_by_name("小米SU7")
        expect(detail_page._product_name).to_be_visible()

        # 3. 加入购物车
        detail_page.add_to_cart(quantity=1)

        # 4. 验证成功提示（Toast）
        expect(page.get_by_text("添加成功")).to_be_visible()

    def test_search_and_buy_product(self, page: Page, auth_page):
        """搜索商品并立即购买"""
        # 1. 搜索
        page.get_by_placeholder("搜索商品").fill("华为手机")
        page.locator(".search-box button").click()

        # 2. 进入详情
        page.get_by_text("华为手机").first.click()
        expect(page.locator("h1")).to_be_visible()

        # 3. 立即购买
        page.get_by_role("button", name="立即购买").click()

        # 4. 验证跳转订单确认页
        expect(page).to_have_url("/order/confirm")
```

---

## Fixtures 模板

```python
# tests/fixtures/auth_fixture.py
import pytest
from playwright.sync_api import Page
from pages.auth.login_page import LoginPage


@pytest.fixture
def login_page(page: Page) -> LoginPage:
    """登录页 fixture"""
    return LoginPage(page).navigate()


@pytest.fixture
def auth_page(page: Page) -> Page:
    """已认证的 page fixture"""
    login_page = LoginPage(page)
    login_page.navigate().login("test_user", "Test@1234")
    return page


@pytest.fixture
def test_user() -> dict:
    """测试用户数据"""
    return {
        "username": "test_user",
        "password": "Test@1234",
        "email": "test_user@example.com",
        "phone": "13800138000",
    }
```

```python
# tests/fixtures/data_fixture.py
import pytest
from utils.data_factory import DataFactory


@pytest.fixture
def random_user() -> dict:
    """随机用户数据（用于注册等场景）"""
    return DataFactory.generate_user()


@pytest.fixture
def random_product_search() -> dict:
    """随机商品搜索数据"""
    return DataFactory.generate_product_search()
```

---

## conftest.py 模板

```python
# tests/conftest.py
import pytest
from playwright.sync_api import BrowserContext


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """全局浏览器上下文配置"""
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "locale": "zh-CN",
    }


# 导入各模块 fixtures
from tests.fixtures.auth_fixture import *  # noqa: F401,F403
from tests.fixtures.data_fixture import *  # noqa: F401,F403
```

---

## 从测试用例到脚本的转换对照表

| 测试用例步骤 | 脚本代码 |
|-------------|---------|
| 打开XX页 | `page_class = PageClass(page).navigate()` |
| 输入XX值为YY | `page_class.fill_xx("YY")` |
| 点击XX按钮 | `page_class.click_xx()` |
| 选择XX选项 | `page_class.select_xx("选项")` |
| 勾选XX | `page_class.check_xx()` |
| 验证跳转到YY页 | `expect(page).to_have_url("/yy")` |
| 验证显示XX文本 | `expect(page.get_by_text("XX")).to_be_visible()` |
| 验证元素可见 | `expect(locator).to_be_visible()` |
| 验证元素不可见 | `expect(locator).to_be_hidden()` |
| 验证文本内容 | `assert element.get_text() == "expected"` |
| 等待加载完成 | `page.wait_for_load_state("networkidle")` |
