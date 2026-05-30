from playwright.sync_api import Page, Locator, FrameLocator, expect
from typing import Optional
import time
import os


class EnhancedBasePage:
    """增强版 BasePage — 智能等待 + 安全操作 + 弹窗处理 + iframe 穿透"""

    def __init__(self, page: Page):
        self.page = page
        self.timeout = 10000

    # ---- 页面加载等待 ----

    def navigate(self, url: str, wait_until: str = "networkidle") -> "EnhancedBasePage":
        self.page.goto(url, wait_until=wait_until)
        return self

    def wait_for_page_ready(self, timeout: int = 30000) -> "EnhancedBasePage":
        self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
        self.page.wait_for_load_state("networkidle", timeout=timeout)
        return self

    # ---- 智能等待 ----

    def wait_for_locator(self, locator: Locator, timeout: Optional[int] = None):
        locator.wait_for(state="visible", timeout=timeout or self.timeout)

    def wait_for_loading_gone(self, timeout: int = 15000) -> "EnhancedBasePage":
        loading = self.page.locator(
            ".loading, .el-loading-mask, [class*='skeleton'], .el-skeleton"
        )
        if loading.count() > 0:
            loading.last.wait_for(state="hidden", timeout=timeout)
        return self

    def wait_for_ajax(self, api_pattern: str = "**/api/**", timeout: int = 15000):
        self.page.wait_for_response(api_pattern, timeout=timeout)

    def wait_for_animation(self, locator: Locator, timeout: int = 3000):
        locator.wait_for(state="visible", timeout=timeout)
        self.page.wait_for_timeout(300)

    def wait_for_url(self, expected_url: str, timeout: int = 10000):
        expect(self.page).to_have_url(expected_url, timeout=timeout)

    # ---- 安全操作（等待 + 重试） ----

    def safe_click(self, locator: Locator, retries: int = 3) -> "EnhancedBasePage":
        for attempt in range(retries):
            try:
                self.wait_for_loading_gone()
                locator.wait_for(state="visible", timeout=self.timeout)
                locator.click(timeout=self.timeout)
                return self
            except Exception as e:
                if attempt == retries - 1:
                    self.take_screenshot(f"safe_click_failed_{attempt}")
                    raise
                self.page.wait_for_timeout(1000 * (attempt + 1))

    def safe_fill(
        self, locator: Locator, value: str, retries: int = 3
    ) -> "EnhancedBasePage":
        for attempt in range(retries):
            try:
                self.wait_for_loading_gone()
                locator.wait_for(state="visible", timeout=self.timeout)
                locator.clear()
                locator.fill(value)
                return self
            except Exception as e:
                if attempt == retries - 1:
                    self.take_screenshot(f"safe_fill_failed_{attempt}")
                    raise
                self.page.wait_for_timeout(1000 * (attempt + 1))

    # ---- 弹窗处理 ----

    def dismiss_unexpected_dialog(self) -> "EnhancedBasePage":
        self.page.on("dialog", lambda dialog: dialog.dismiss())
        return self

    def auto_accept_dialog(self) -> "EnhancedBasePage":
        self.page.on("dialog", lambda dialog: dialog.accept())
        return self

    # ---- iframe 操作 ----

    def enter_iframe(self, iframe_selector: str) -> FrameLocator:
        return self.page.frame_locator(iframe_selector)

    # ---- Toast 断言 ----

    def wait_for_toast(
        self, expected_text: str = "", timeout: int = 10000
    ) -> str:
        toast = self.page.locator(
            ".el-message, .el-notification, .toast, [role='alert']"
        )
        toast.first.wait_for(state="visible", timeout=timeout)
        text = toast.first.text_content() or ""
        if expected_text:
            assert expected_text in text, f"期望包含'{expected_text}'，实际为'{text}'"
        return text

    # ---- 页面恢复 ----

    def recover_page(self) -> "EnhancedBasePage":
        try:
            self.page.reload(wait_until="networkidle")
        except Exception:
            self.page.goto(self.page.url, wait_until="networkidle")
        return self

    # ---- 截图 ----

    def take_screenshot(self, name: str) -> str:
        os.makedirs("screenshots", exist_ok=True)
        path = f"screenshots/{name}.png"
        self.page.screenshot(path=path, full_page=True)
        return path

    # ---- 通用导航 ----

    def get_page_title(self) -> str:
        return self.page.title()

    def refresh(self) -> "EnhancedBasePage":
        self.page.reload()
        return self

    def go_back(self) -> "EnhancedBasePage":
        self.page.go_back()
        return self
