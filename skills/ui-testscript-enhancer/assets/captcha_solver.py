from playwright.sync_api import Page, Locator
from typing import Optional


class CaptchaSolver:
    """验证码识别模块 — 支持图形验证码（OCR）"""

    _ocr = None

    @classmethod
    def solve_image(cls, image_bytes: bytes) -> str:
        """识别图形验证码（ddddocr）"""
        try:
            import ddddocr
        except ImportError:
            raise ImportError("请安装 ddddocr: pip install ddddocr")

        if cls._ocr is None:
            cls._ocr = ddddocr.DdddOcr(show_ad=False)
        result = cls._ocr.classification(image_bytes)
        return result.strip()

    @classmethod
    def solve_from_locator(cls, page: Page, locator: Locator) -> str:
        """从页面元素截图识别验证码"""
        image_bytes = locator.screenshot(type="png")
        return cls.solve_image(image_bytes)

    @classmethod
    def solve_math(cls, image_bytes: bytes) -> str:
        """识别计算题验证码"""
        import re
        text = cls.solve_image(image_bytes)
        expr = re.sub(r"[^0-9+\-*/()]", "", text)
        try:
            return str(int(eval(expr)))  # noqa: S307
        except Exception:
            return ""


class ThirdPartyCaptchaSolver:
    """第三方打码平台"""

    def __init__(self, platform: str = "2captcha", api_key: str = ""):
        self.platform = platform
        self.api_key = api_key

    def solve(self, image_bytes: bytes) -> str:
        if self.platform == "2captcha":
            return self._solve_2captcha(image_bytes)
        raise ValueError(f"不支持的平台: {self.platform}")

    def _solve_2captcha(self, image_bytes: bytes) -> str:
        import requests
        import base64
        import time

        resp = requests.post(
            "https://2captcha.com/in.php",
            data={
                "key": self.api_key,
                "method": "base64",
                "body": base64.b64encode(image_bytes).decode(),
                "json": 1,
            },
            timeout=30,
        )
        task_id = resp.json()["request"]

        for _ in range(30):
            time.sleep(5)
            resp = requests.get(
                f"https://2captcha.com/res.php?key={self.api_key}"
                f"&action=get&id={task_id}&json=1",
                timeout=30,
            )
            data = resp.json()
            if data["status"] == 1:
                return data["request"]
        raise TimeoutError("验证码识别超时")


class SmsCaptchaSolver:
    """短信验证码获取"""

    @staticmethod
    def solve_from_api(phone: str, api_base_url: str) -> str:
        import requests
        resp = requests.get(
            f"{api_base_url}/api/test/sms-code",
            params={"phone": phone},
            timeout=10,
        )
        return resp.json().get("code", "")
