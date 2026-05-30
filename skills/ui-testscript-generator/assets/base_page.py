# pages/base_page.py
from playwright.sync_api import Page, Locator, expect
from typing import Optional


class BasePage:
    """所有 Page 类的基类，封装通用能力"""

    def __init__(self, page: Page):
        self.page = page
        self.timeout = 10000  # 默认超时 10s

    def wait_for_locator(self, locator: Locator, timeout: Optional[int] = None):
        """显式等待元素可见"""
        locator.wait_for(state="visible", timeout=timeout or self.timeout)

    def safe_click(self, locator: Locator):
        """安全点击：等待 + 点击"""
        locator.wait_for(state="visible")
        locator.click()

    def take_screenshot(self, name: str) -> str:
        """截图并保存"""
        path = f"screenshots/{name}.png"
        self.page.screenshot(path=path, full_page=True)
        return path

    def get_page_title(self) -> str:
        return self.page.title()

    def refresh(self) -> "BasePage":
        self.page.reload()
        return self

    def go_back(self) -> "BasePage":
        self.page.go_back()
        return self
