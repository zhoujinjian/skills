from playwright.sync_api import Page, Locator
from typing import Optional


class PopupHandler:
    """弹窗自动处理器"""

    COMMON_CLOSE_SELECTORS = [
        ".ad-close",
        ".popup-close",
        "[class*='advertisement'] .close",
        ".modal-ad .close-btn",
        "button[aria-label='关闭广告']",
        ".guide-close",
        ".coupon-close",
        ".notification-close",
    ]

    def __init__(self, page: Page):
        self.page = page
        self.dialog_log: list[dict] = []

    # ---- 原生弹窗 ----

    def auto_accept_dialog(self):
        """自动确认所有原生弹窗"""
        self.page.on("dialog", self._handle_dialog)

    def auto_dismiss_dialog(self):
        """自动关闭所有原生弹窗"""
        self.page.on("dialog", lambda dialog: dialog.dismiss())

    def _handle_dialog(self, dialog):
        self.dialog_log.append({
            "type": dialog.type,
            "message": dialog.message,
        })
        dialog.accept()

    def assert_dialog_shown(self, expected_message: str):
        assert any(
            expected_message in d["message"] for d in self.dialog_log
        ), f"未找到包含'{expected_message}'的弹窗"

    # ---- 广告弹窗 ----

    def dismiss_ads(self):
        """尝试关闭所有广告弹窗"""
        for selector in self.COMMON_CLOSE_SELECTORS:
            close_btn = self.page.locator(selector)
            if close_btn.is_visible():
                try:
                    close_btn.click(timeout=2000)
                except Exception:
                    pass

    def register_auto_dismiss(self):
        """注册自动关闭：每次页面加载后自动检测广告"""
        self.page.on("load", lambda: self.dismiss_ads())

    # ---- Modal 弹窗 ----

    def wait_for_modal(
        self, modal_selector: str = ".el-dialog, .el-drawer, .modal",
        timeout: int = 10000,
    ) -> Locator:
        modal = self.page.locator(modal_selector)
        modal.wait_for(state="visible", timeout=timeout)
        return modal

    def close_modal(self, modal_selector: str = ".el-dialog, .el-drawer, .modal"):
        close_btn = self.page.locator(
            f"{modal_selector} .el-dialog__close, "
            f"{modal_selector} .close-btn, "
            f"{modal_selector} [aria-label='Close']"
        )
        if close_btn.is_visible():
            close_btn.click()
            self.page.locator(modal_selector).wait_for(state="hidden")

    # ---- Toast ----

    def wait_for_toast(
        self, expected_text: str = "",
        toast_selector: str = ".el-message, .el-notification, .toast, [role='alert']",
        timeout: int = 10000,
    ) -> str:
        toast = self.page.locator(toast_selector)
        toast.first.wait_for(state="visible", timeout=timeout)
        text = toast.first.text_content() or ""
        if expected_text:
            assert expected_text in text, f"期望包含'{expected_text}'，实际为'{text}'"
        return text

    def dismiss_all_toasts(
        self, toast_selector: str = ".el-message, .el-notification, .toast"
    ):
        toasts = self.page.locator(toast_selector)
        for _ in range(toasts.count()):
            close = toasts.first.locator(".el-message__closeBtn, .close")
            if close.is_visible():
                close.click()
