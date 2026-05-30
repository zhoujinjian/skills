# POM 页面对象模板与示例

本文件提供 POM 页面类的编写模板和完整示例，用于生成代码时参考。

---

## 目录

1. [标准 POM 类模板](#标准-pom-类模板)
2. [登录页 POM 完整示例](#登录页-pom-完整示例)
3. [列表页 POM 示例](#列表页-pom-示例)
4. [详情页 POM 示例](#详情页-pom-示例)
5. [共享组件封装](#共享组件封装)
6. [页面跳转方法规范](#页面跳转方法规范)

---

## 标准 POM 类模板

```python
# pages/<module>/<page_name>_page.py
from playwright.sync_api import Page, Locator, expect
from pages.base_page import BasePage


class PageNamePage(BasePage):
    """页面业务描述"""

    def __init__(self, page: Page):
        super().__init__(page)
        # ---- 元素定位器（私有） ----
        self._element_name: Locator = page.get_by_role("textbox", name="元素标签")

    # ---- 导航 ----
    def navigate(self) -> "PageNamePage":
        self.page.goto("/page-path")
        return self

    # ---- 操作方法 ----
    def fill_element(self, value: str) -> "PageNamePage":
        self._element_name.fill(value)
        return self

    def click_element(self) -> "TargetPage":
        self._element_name.click()
        return TargetPage(self.page)

    # ---- 组合操作 ----
    def do_something(self, param: str) -> "TargetPage":
        self.fill_element(param).click_element()
        return TargetPage(self.page)

    # ---- 状态查询 ----
    def get_element_text(self) -> str:
        return self._element_name.text_content() or ""

    # ---- 页面验证 ----
    def assert_on_page(self) -> "PageNamePage":
        expect(self.page).to_have_url("/page-path")
        return self
```

---

## 登录页 POM 完整示例

基于 pages.yaml 中登录页的元素定义生成：

```python
# pages/auth/login_page.py
from playwright.sync_api import Page, Locator, expect
from pages.base_page import BasePage


class LoginPage(BasePage):
    """登录页 - 用户通过用户名和密码登录系统"""

    def __init__(self, page: Page):
        super().__init__(page)
        # ---- 元素定位器 ----
        self._username_input: Locator = page.get_by_placeholder("请输入用户名")
        self._password_input: Locator = page.get_by_placeholder("请输入密码")
        self._remember_me_checkbox: Locator = page.get_by_text("记住我")
        self._login_button: Locator = page.get_by_role("button", name="登 录")
        self._wechat_login_button: Locator = page.get_by_role("button", name="微信登录")
        self._forgot_password_link: Locator = page.get_by_text("忘记密码")

    # ---- 导航 ----
    def navigate(self) -> "LoginPage":
        self.page.goto("/login")
        self._login_button.wait_for(state="visible")
        return self

    # ---- 填写操作 ----
    def fill_username(self, username: str) -> "LoginPage":
        self._username_input.fill(username)
        return self

    def fill_password(self, password: str) -> "LoginPage":
        self._password_input.fill(password)
        return self

    # ---- 点击操作 ----
    def click_login(self) -> "HomePage":
        self._login_button.click()
        return HomePage(self.page)

    def click_wechat_login(self) -> "LoginPage":
        self._wechat_login_button.click()
        return self

    def click_forgot_password(self) -> "LoginPage":
        self._forgot_password_link.click()
        return self

    # ---- 复选框 ----
    def check_remember_me(self) -> "LoginPage":
        self._remember_me_checkbox.check()
        return self

    # ---- 组合操作 ----
    def login(self, username: str, password: str) -> "HomePage":
        """完整登录流程：输入用户名密码并点击登录"""
        self.fill_username(username).fill_password(password)
        self._login_button.click()
        return HomePage(self.page)

    def login_with_remember(self, username: str, password: str) -> "HomePage":
        """登录并勾选记住我"""
        self.fill_username(username).fill_password(password)
        self.check_remember_me()
        self._login_button.click()
        return HomePage(self.page)

    # ---- 状态查询 ----
    def get_error_message(self) -> str:
        """获取错误提示文本（需等待错误提示出现）"""
        error_locator = self.page.get_by_role("alert")
        error_locator.wait_for(state="visible", timeout=5000)
        return error_locator.text_content() or ""

    # ---- 页面验证 ----
    def assert_on_page(self) -> "LoginPage":
        expect(self.page).to_have_url("/login")
        expect(self._login_button).to_be_visible()
        return self


# 需要导入的跳转目标页面
from pages.home_page import HomePage  # noqa: E402
```

---

## 列表页 POM 示例

```python
# pages/product/product_list_page.py
from playwright.sync_api import Page, Locator, expect
from pages.base_page import BasePage


class ProductListPage(BasePage):
    """商品列表页 - 展示商品列表，支持分类筛选、排序、翻页"""

    def __init__(self, page: Page):
        super().__init__(page)
        # ---- 筛选区域 ----
        self._min_price_input: Locator = page.get_by_placeholder("最低价")
        self._max_price_input: Locator = page.get_by_placeholder("最高价")
        self._sort_default: Locator = page.get_by_text("默认", exact=True)
        self._sort_price_asc: Locator = page.get_by_text("价格升序")
        self._sort_price_desc: Locator = page.get_by_text("价格降序")
        self._sort_sales: Locator = page.get_by_text("销量")

        # ---- 分类标签（动态） ----
        # 使用时通过 get_by_text 动态定位

        # ---- 分页 ----
        self._prev_page_button: Locator = page.get_by_role("button", name="上一页")
        self._next_page_button: Locator = page.get_by_role("button", name="下一页")

    # ---- 导航 ----
    def navigate(self) -> "ProductListPage":
        self.page.goto("/product")
        return self

    # ---- 筛选操作 ----
    def fill_price_range(self, min_price: str, max_price: str) -> "ProductListPage":
        self._min_price_input.fill(min_price)
        self._max_price_input.fill(max_price)
        return self

    def select_category(self, category_name: str) -> "ProductListPage":
        self.page.get_by_text(category_name, exact=True).click()
        return self

    def sort_by(self, sort_type: str) -> "ProductListPage":
        sort_map = {
            "默认": self._sort_default,
            "价格升序": self._sort_price_asc,
            "价格降序": self._sort_price_desc,
            "销量": self._sort_sales,
        }
        locator = sort_map.get(sort_type)
        if locator:
            locator.click()
        return self

    # ---- 分页操作 ----
    def click_next_page(self) -> "ProductListPage":
        self._next_page_button.click()
        return self

    def click_prev_page(self) -> "ProductListPage":
        self._prev_page_button.click()
        return self

    # ---- 商品操作 ----
    def click_product_by_name(self, product_name: str) -> "ProductDetailPage":
        self.page.get_by_text(product_name).click()
        return ProductDetailPage(self.page)

    def get_product_count(self) -> int:
        return self.page.locator(".product-item, .product-card").count()

    # ---- 页面验证 ----
    def assert_on_page(self) -> "ProductListPage":
        expect(self.page).to_have_url("/product")
        return self


from pages.product.product_detail_page import ProductDetailPage  # noqa: E402
```

---

## 详情页 POM 示例

```python
# pages/product/product_detail_page.py
from playwright.sync_api import Page, Locator, expect
from pages.base_page import BasePage


class ProductDetailPage(BasePage):
    """商品详情页 - 展示商品信息，支持加购和购买"""

    def __init__(self, page: Page):
        super().__init__(page)
        self._product_name: Locator = page.locator("h1")
        self._product_desc: Locator = page.locator("h1 + p")
        self._quantity_input: Locator = page.locator("input[type='number']")
        self._add_to_cart_button: Locator = page.get_by_role("button", name="加入购物车")
        self._buy_now_button: Locator = page.get_by_role("button", name="立即购买")
        self._detail_tab: Locator = page.locator("#tab-detail")
        self._specs_tab: Locator = page.locator("#tab-specs")
        self._detail_content: Locator = page.locator("#pane-detail")
        self._specs_content: Locator = page.locator("#pane-specs")

    # ---- 导航 ----
    def navigate(self, product_id: int = 1) -> "ProductDetailPage":
        self.page.goto(f"/product/{product_id}")
        self._product_name.wait_for(state="visible")
        return self

    # ---- 操作 ----
    def set_quantity(self, quantity: int) -> "ProductDetailPage":
        self._quantity_input.fill(str(quantity))
        return self

    def click_add_to_cart(self) -> "ProductDetailPage":
        self._add_to_cart_button.click()
        return self

    def click_buy_now(self) -> "OrderConfirmPage":
        self._buy_now_button.click()
        return OrderConfirmPage(self.page)

    def switch_to_detail_tab(self) -> "ProductDetailPage":
        self._detail_tab.click()
        return self

    def switch_to_specs_tab(self) -> "ProductDetailPage":
        self._specs_tab.click()
        return self

    # ---- 组合操作 ----
    def add_to_cart(self, quantity: int = 1) -> "ProductDetailPage":
        self.set_quantity(quantity).click_add_to_cart()
        return self

    # ---- 状态查询 ----
    def get_product_name(self) -> str:
        return self._product_name.text_content() or ""

    def get_product_desc(self) -> str:
        return self._product_desc.text_content() or ""

    def get_specs_text(self) -> str:
        self.switch_to_specs_tab()
        return self._specs_content.text_content() or ""

    # ---- 页面验证 ----
    def assert_on_page(self, product_id: int = 1) -> "ProductDetailPage":
        expect(self.page).to_have_url(f"/product/{product_id}")
        expect(self._product_name).to_be_visible()
        return self


from pages.order.order_confirm_page import OrderConfirmPage  # noqa: E402
```

---

## 共享组件封装

当多个页面共享相同的 UI 组件（如页头导航、侧边栏），应封装为独立的组件类：

```python
# pages/components/header.py
from playwright.sync_api import Page, Locator


class Header:
    """全局页头导航组件"""

    def __init__(self, page: Page):
        self.page = page
        self._logo_link: Locator = page.locator("a.logo")
        self._search_input: Locator = page.get_by_placeholder("搜索商品")
        self._search_button: Locator = page.locator(".search-box button.el-button")
        self._cart_link: Locator = page.get_by_text("购物车")
        self._login_link: Locator = page.get_by_text("登录")
        self._register_link: Locator = page.get_by_text("注册")

    def search(self, keyword: str) -> "SearchResultPage":
        self._search_input.fill(keyword)
        self._search_button.click()
        return SearchResultPage(self.page)

    def go_home(self) -> "HomePage":
        self._logo_link.click()
        return HomePage(self.page)

    def go_to_cart(self) -> "CartPage":
        self._cart_link.click()
        return CartPage(self.page)

    def go_to_login(self) -> "LoginPage":
        self._login_link.click()
        return LoginPage(self.page)

    def is_logged_in(self) -> bool:
        return self._login_link.is_hidden()
```

---

## 页面跳转方法规范

### 规则

1. 跳转到其他页面的方法返回目标 Page 对象
2. 同页面内的操作返回 `self`
3. 跳转方法应等待目标页面加载完成
4. 在文件底部使用延迟导入避免循环依赖

### 模式

```python
# 同页操作 → 返回 self
def fill_username(self, username: str) -> "LoginPage":
    self._username_input.fill(username)
    return self

# 页面跳转 → 返回目标 Page
def click_login(self) -> "HomePage":
    self._login_button.click()
    return HomePage(self.page)

# 组合操作 → 返回最终目标 Page
def login(self, username: str, password: str) -> "HomePage":
    self.fill_username(username).fill_password(password)
    self._login_button.click()
    return HomePage(self.page)
```

### 从 pages.yaml 的 flows 提取跳转关系

```yaml
# pages.yaml 中的 flow:
flows:
  - flow_name: "正常登录流程"
    steps:
      - step: 3
        action: "click"
        element: "登录按钮"
        wait_after: "url_change"
      - step: 4
        action: "assert"
        target: "url"
        expected: "/"
```

转换为：
- `click_login()` → 返回 `HomePage`
- `login(username, password)` → 返回 `HomePage`
