# 验证码识别方案

## 目录

1. [图形验证码（OCR）](#图形验证码ocr)
2. [滑动验证码](#滑动验证码)
3. [文字点选验证码](#文字点选验证码)
4. [计算题验证码](#计算题验证码)
5. [短信验证码](#短信验证码)
6. [第三方打码平台](#第三方打码平台)
7. [POM 集成模式](#pom-集成模式)

---

## 图形验证码（OCR）

使用 `ddddocr`（开源 OCR 库，离线识别）：

```python
# utils/captcha_solver.py
import ddddocr

class CaptchaSolver:
    _ocr = None

    @classmethod
    def solve_image(cls, image_bytes: bytes) -> str:
        """识别图形验证码"""
        if cls._ocr is None:
            cls._ocr = ddddocr.DdddOcr(show_ad=False)
        result = cls._ocr.classification(image_bytes)
        return result.strip()

    @classmethod
    def solve_from_locator(cls, page, locator) -> str:
        """直接从页面元素截图识别"""
        image_bytes = locator.screenshot(type="png")
        return cls.solve_image(image_bytes)
```

POM 集成：

```python
from utils.captcha_solver import CaptchaSolver

class LoginPage(BasePage):
    def fill_captcha_auto(self) -> "LoginPage":
        code = CaptchaSolver.solve_from_locator(self.page, self._captcha_image)
        self._captcha_input.fill(code)
        return self
```

依赖：`pip install ddddocr`

---

## 滑动验证码

计算滑块偏移量并模拟拖拽：

```python
class SliderCaptchaSolver:
    @staticmethod
    def solve(page, slider_track_locator, bg_image_locator, slider_locator):
        """滑动验证码处理"""
        # 1. 获取背景图和滑块图的偏移量
        bg_image = bg_image_locator.screenshot(type="png")
        offset = SliderCaptchaSolver._calculate_offset(bg_image)

        # 2. 模拟人类拖拽轨迹
        box = slider_locator.bounding_box()
        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] + box["height"] / 2

        # 3. 按下 → 拖拽 → 释放（带随机轨迹）
        page.mouse.move(start_x, start_y)
        page.mouse.down()

        current_x = start_x
        steps = random.randint(20, 40)
        for i in range(steps):
            # 模拟人类拖拽：先快后慢 + 轻微上下抖动
            progress = (i + 1) / steps
            ease = 1 - (1 - progress) ** 3  # ease-out
            target_x = start_x + offset * ease
            jitter_y = start_y + random.uniform(-2, 2)
            page.mouse.move(target_x, jitter_y)
            page.wait_for_timeout(random.randint(5, 20))

        page.mouse.up()

    @staticmethod
    def _calculate_offset(bg_image_bytes: bytes) -> float:
        """通过图像对比计算偏移量"""
        import cv2
        import numpy as np
        img = cv2.imdecode(np.frombuffer(bg_image_bytes, np.uint8), cv2.IMREAD_COLOR)
        # 检测缺口位置（灰度 + 边缘检测）
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        # 寻找缺口区域的 x 坐标
        # ... 具体实现视验证码类型调整
        return offset_x
```

---

## 文字点选验证码

识别文字位置并点击：

```python
class ClickCaptchaSolver:
    @staticmethod
    def solve(page, captcha_image_locator, target_text: str, click_area_locator):
        """文字点选验证码"""
        # 1. 截取验证码图片
        image_bytes = captcha_image_locator.screenshot(type="png")

        # 2. OCR 识别文字及坐标
        positions = ClickCaptchaSolver._detect_text_positions(image_bytes)

        # 3. 点击目标文字
        for text, x, y in positions:
            if text in target_text:
                box = click_area_locator.bounding_box()
                click_x = box["x"] + x
                click_y = box["y"] + y
                page.mouse.click(click_x, click_y)
                break
```

---

## 计算题验证码

提取表达式并计算：

```python
class MathCaptchaSolver:
    @staticmethod
    def solve(image_bytes: bytes) -> str:
        """识别并计算数学表达式"""
        text = CaptchaSolver.solve_image(image_bytes)
        # 清理文本：移除非数学字符
        expr = re.sub(r"[^0-9+\-*/()=]", "", text.replace("=", ""))
        try:
            result = eval(expr)  # 仅限数学表达式
            return str(int(result))
        except Exception:
            return ""
```

---

## 短信验证码

从后端 API 或数据库获取：

```python
class SmsCaptchaSolver:
    @staticmethod
    def solve_from_api(phone: str, api_base_url: str = "") -> str:
        """从测试环境 API 获取短信验证码"""
        import requests
        resp = requests.get(f"{api_base_url}/api/test/sms-code?phone={phone}")
        return resp.json().get("code", "")

    @staticmethod
    def solve_from_db(phone: str, db_config: dict) -> str:
        """从数据库查询验证码"""
        import pymysql
        conn = pymysql.connect(**db_config)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT code FROM sms_codes WHERE phone=%s ORDER BY created_at DESC LIMIT 1",
            (phone,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else ""
```

---

## 第三方打码平台

```python
class ThirdPartyCaptchaSolver:
    """第三方打码平台（2Captcha / 超级鹰 / 联众）"""

    def __init__(self, platform: str = "2captcha", api_key: str = ""):
        self.platform = platform
        self.api_key = api_key

    def solve(self, image_bytes: bytes) -> str:
        if self.platform == "2captcha":
            return self._solve_2captcha(image_bytes)
        elif self.platform == "chaojiying":
            return self._solve_chaojiying(image_bytes)
        raise ValueError(f"不支持的平台: {self.platform}")

    def _solve_2captcha(self, image_bytes: bytes) -> str:
        import requests, base64, time
        # 上传验证码
        resp = requests.post("https://2captcha.com/in.php", data={
            "key": self.api_key,
            "method": "base64",
            "body": base64.b64encode(image_bytes).decode(),
            "json": 1,
        })
        task_id = resp.json()["request"]
        # 轮询结果
        for _ in range(30):
            time.sleep(5)
            resp = requests.get(
                f"https://2captcha.com/res.php?key={self.api_key}&action=get&id={task_id}&json=1"
            )
            data = resp.json()
            if data["status"] == 1:
                return data["request"]
        raise TimeoutError("验证码识别超时")
```

---

## POM 集成模式

### 方案 1：自动识别（推荐用于图形验证码）

```python
class LoginPage(BasePage):
    def fill_captcha_auto(self) -> "LoginPage":
        """自动识别并填写验证码"""
        code = CaptchaSolver.solve_from_locator(self.page, self._captcha_image)
        self._captcha_input.fill(code)
        return self
```

### 方案 2：策略模式（多种验证码类型）

```python
class LoginPage(BasePage):
    _captcha_strategy = None

    def set_captcha_strategy(self, strategy):
        self._captcha_strategy = strategy

    def fill_captcha_auto(self) -> "LoginPage":
        if self._captcha_strategy:
            code = self._captcha_strategy.solve(self.page, self._captcha_image)
            self._captcha_input.fill(code)
        return self
```

### 方案 3：conftest 全局配置

```python
@pytest.fixture
def captcha_strategy():
    """全局验证码策略"""
    return CaptchaSolver()  # 或 ThirdPartyCaptchaSolver(api_key="...")
```
