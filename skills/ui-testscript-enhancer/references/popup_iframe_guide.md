# 弹窗与 iframe 处理指南

## 目录

1. [原生弹窗处理](#原生弹窗处理alertconfirmprompt)
2. [自定义弹窗/Modal 处理](#自定义弹窗modal-处理)
3. [Toast 消息处理](#toast-消息处理)
4. [广告弹窗处理](#广告弹窗处理)
5. [iframe 内元素定位](#iframe-内元素定位)
6. [Shadow DOM 穿透](#shadow-dom-穿透)

---

## 原生弹窗处理（alert/confirm/prompt）

### 自动关闭所有弹窗

```python
# conftest.py 中全局配置
@pytest.fixture(autouse=True)
def handle_native_dialogs(page):
    """自动处理原生弹窗：全部确认"""
    page.on("dialog", lambda dialog: dialog.accept())
```

### 条件处理

```python
class PopupHandler:
    def __init__(self, page: Page):
        self.page = page
        self.dialog_log = []

    def auto_accept(self):
        """自动确认所有弹窗"""
        self.page.on("dialog", self._handle_dialog)

    def _handle_dialog(self, dialog):
        self.dialog_log.append({
            "type": dialog.type,
            "message": dialog.message,
        })
        dialog.accept()

    def assert_dialog_shown(self, expected_message: str):
        """验证弹窗已弹出"""
        assert any(
            expected_message in d["message"]
            for d in self.dialog_log
        ), f"未找到包含'{expected_message}'的弹窗"
```

### 按类型处理

```python
def handle_dialog_by_type(page: Page):
    """按弹窗类型分别处理"""
    def on_dialog(dialog):
        if dialog.type == "alert":
            dialog.accept()
        elif dialog.type == "confirm":
            dialog.accept()  # 或 dialog.dismiss()
        elif dialog.type == "prompt":
            dialog.accept("自动输入的文本")
    page.on("dialog", on_dialog)
```

---

## 自定义弹窗（Modal）处理

### 等待弹窗出现并操作

```python
class ModalHelper:
    def __init__(self, page: Page, modal_selector: str = ".el-dialog, .el-drawer, .modal"):
        self.page = page
        self.modal_selector = modal_selector

    def wait_for_modal(self, timeout: int = 10000) -> Locator:
        """等待弹窗出现"""
        modal = self.page.locator(self.modal_selector)
        modal.wait_for(state="visible", timeout=timeout)
        return modal

    def close_modal(self):
        """关闭弹窗"""
        close_btn = self.page.locator(
            f"{self.modal_selector} .el-dialog__close, "
            f"{self.modal_selector} .close-btn, "
            f"{self.modal_selector} [aria-label='Close']"
        )
        if close_btn.is_visible():
            close_btn.click()
            self.page.locator(self.modal_selector).wait_for(state="hidden")

    def fill_in_modal(self, field_name: str, value: str):
        """在弹窗内填写字段"""
        modal = self.page.locator(self.modal_selector)
        field = modal.get_by_label(field_name) or modal.get_by_placeholder(field_name)
        field.fill(value)

    def click_in_modal(self, button_text: str):
        """在弹窗内点击按钮"""
        modal = self.page.locator(self.modal_selector)
        modal.get_by_role("button", name=button_text).click()
```

---

## Toast 消息处理

### 等待 Toast 出现并断言

```python
class ToastHelper:
    def __init__(self, page: Page):
        self.page = page
        self._toast_selector = ".el-message, .el-notification, .toast, [role='alert']"

    def wait_for_toast(self, expected_text: str = "", timeout: int = 10000) -> str:
        """等待 Toast 出现并返回文本"""
        toast = self.page.locator(self._toast_selector)
        toast.first.wait_for(state="visible", timeout=timeout)
        text = toast.first.text_content() or ""
        if expected_text:
            assert expected_text in text, f"期望包含'{expected_text}'，实际为'{text}'"
        return text

    def wait_for_success(self, timeout: int = 10000) -> str:
        """等待成功 Toast"""
        return self.wait_for_toast(timeout=timeout)

    def wait_for_error(self, timeout: int = 10000) -> str:
        """等待错误 Toast"""
        return self.wait_for_toast(timeout=timeout)

    def dismiss_all(self):
        """关闭所有 Toast"""
        toasts = self.page.locator(self._toast_selector)
        count = toasts.count()
        for _ in range(count):
            close = toasts.first.locator(".el-message__closeBtn, .close")
            if close.is_visible():
                close.click()
```

---

## 广告弹窗处理

### 自动关闭广告弹窗

```python
class AdDismissHandler:
    """广告弹窗自动关闭"""

    COMMON_AD_SELECTORS = [
        ".ad-close",
        ".popup-close",
        "[class*='advertisement'] .close",
        ".modal-ad .close-btn",
        "button[aria-label='关闭广告']",
        ".guide-close",
        ".coupon-close",
    ]

    def __init__(self, page: Page):
        self.page = page

    def dismiss_all(self):
        """尝试关闭所有广告弹窗"""
        for selector in self.COMMON_AD_SELECTORS:
            close_btn = self.page.locator(selector)
            if close_btn.is_visible():
                try:
                    close_btn.click(timeout=2000)
                except Exception:
                    pass

    def register_auto_dismiss(self):
        """注册自动关闭：每次页面加载后自动检测"""
        self.page.on("load", lambda: self.dismiss_all())
```

---

## iframe 内元素定位

### 基础 iframe 切换

```python
# 方式 1：FrameLocator（推荐）
frame = page.frame_locator("#captcha-iframe")
frame.get_by_placeholder("请输入验证码").fill("1234")
frame.get_by_role("button", name="提交").click()

# 方式 2：嵌套 iframe
outer_frame = page.frame_locator("#outer-iframe")
inner_frame = outer_frame.frame_locator("#inner-iframe")
inner_frame.get_by_text("目标元素").click()
```

### POM 中封装 iframe 操作

```python
class CaptchaIframe(BasePage):
    """验证码 iframe 内部操作"""

    def __init__(self, page: Page):
        super().__init__(page)
        self._frame = page.frame_locator("iframe[src*='captcha']")

    def fill_captcha(self, code: str) -> "CaptchaIframe":
        self._frame.get_by_placeholder("验证码").fill(code)
        return self

    def click_verify(self):
        self._frame.get_by_role("button", name="验证").click()
```

### 通用 iframe 辅助方法

```python
def safe_iframe_action(page: Page, iframe_selector: str, action_fn):
    """安全执行 iframe 内操作"""
    frame = page.frame_locator(iframe_selector)
    try:
        action_fn(frame)
    except Exception as e:
        # 截图帮助调试
        page.screenshot(path="screenshots/iframe_error.png")
        raise Exception(f"iframe 操作失败: {e}") from e
```

---

## Shadow DOM 穿透

### Playwright 自动穿透

Playwright 默认支持 Shadow DOM 穿透，`locator()` 可直接定位 Shadow DOM 内元素：

```python
# 自动穿透 Shadow DOM
page.locator("my-custom-element >>> button").click()

# 使用 >>> 或 >> shadow DOM 组合器
page.locator("custom-card").locator("internal:shadow-root >> button").click()
```

### POM 中 Shadow DOM 元素封装

```python
class ComponentWithShadow(BasePage):
    def __init__(self, page: Page):
        super().__init__(page)
        self._shadow_host = page.locator("custom-element")
        self._inner_button = self._shadow_host.locator("button.submit")
        self._inner_input = self._shadow_host.locator("input")
```
