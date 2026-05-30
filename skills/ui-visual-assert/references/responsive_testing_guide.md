# 响应式布局测试指南

## 视口预设

内置三种常用视口，覆盖桌面、平板、手机：

| 预设名 | 尺寸 | 对应设备 |
|--------|------|---------|
| `desktop` | 1920×1080 | 标准桌面显示器 |
| `tablet` | 768×1024 | iPad 竖屏 |
| `mobile` | 375×812 | iPhone X / 11 Pro |

### 自定义视口

在 `conftest.py` 中扩展 `VIEWPORT_PRESETS`：

```python
VIEWPORT_PRESETS = {
    "desktop":  {"width": 1920, "height": 1080},
    "laptop":   {"width": 1366, "height": 768},
    "tablet":   {"width": 768,  "height": 1024},
    "mobile_l": {"width": 414,  "height": 896},   # iPhone XR
    "mobile":   {"width": 375,  "height": 812},   # iPhone X
    "mobile_s": {"width": 320,  "height": 568},   # iPhone SE
}
```

---

## 参数化测试模式

使用 `@pytest.mark.parametrize` + `indirect=True` 实现多视口测试：

```python
@pytest.mark.parametrize(
    "viewport_preset",
    ["desktop", "tablet", "mobile"],
    indirect=True,
)
def test_login_responsive(self, responsive_context, viewport_preset, cross_browser_tolerance):
    page = responsive_context.new_page()
    login_page = LoginPage(page).navigate()
    login_page.assert_visual_match(
        "login_page_responsive",
        threshold=cross_browser_tolerance,
    )
```

每个视口生成独立基线：
```
baselines/
├── login_page_responsive_chromium_1920x1080.png
├── login_page_responsive_chromium_768x1024.png
└── login_page_responsive_chromium_375x812.png
```

---

## 设备模拟

除了视口尺寸，还可以模拟完整的移动设备特征：

### 使用 Playwright 内置设备

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    # 获取设备配置（含 user-agent、DPR、触摸支持等）
    iphone = p.devices["iPhone 13"]
    context = browser.new_context(**iphone)
```

### 常用设备列表

| 设备名 | 视口 | DPR | 触摸 |
|--------|------|-----|------|
| `iPhone 13` | 390×844 | 3 | Yes |
| `iPhone SE` | 375×667 | 2 | Yes |
| `iPad Pro 11` | 834×1194 | 2 | Yes |
| `Pixel 5` | 393×851 | 2.75 | Yes |
| `Galaxy S5` | 360×640 | 3 | Yes |

### 在 fixture 中集成设备模拟

```python
@pytest.fixture
def device_context(browser, request):
    """使用 Playwright 设备配置创建上下文"""
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    device_config = pw.devices[request.param]
    context = browser.new_context(**device_config)
    yield context
    context.close()
    pw.stop()
```

---

## 响应式断言要点

### 布局一致性检查

| 检查项 | 桌面 | 平板 | 手机 |
|--------|------|------|------|
| 导航栏 | 水平展开 | 可能折叠 | 汉堡菜单 |
| 表单布局 | 多列 | 双列 | 单列 |
| 按钮尺寸 | 正常 | 正常 | 放大（触摸友好） |
| 字体大小 | 标准 | 标准 | 可能放大 |
| 间距 | 标准 | 缩减 | 进一步缩减 |

### 常见响应式问题

1. **导航溢出**：桌面导航在窄屏下溢出，需要检查折叠逻辑
2. **表格水平滚动**：宽表格在移动端需要横向滚动
3. **图片溢出**：固定宽度图片超出视口
4. **触摸目标过小**：按钮/链接在移动端点击区域不足 44×44px
5. **文字截断**：标题或标签在窄屏下被截断

---

## CSS 注入确保截图一致

`responsive_context` fixture 自动注入以下 CSS：

```css
/* 禁用动画 */
*, *::before, *::after {
    animation-duration: 0s !important;
    animation-delay: 0s !important;
    transition-duration: 0s !important;
    transition-delay: 0s !important;
}
```

如需额外注入（如隐藏滚动条），在测试中添加：

```python
page.add_style_tag(content="::-webkit-scrollbar { display: none; }")
page.add_style_tag(content="* { scrollbar-width: none; }")  /* Firefox */
```

---

## device_scale_factor 统一

视觉测试中统一设置 `device_scale_factor=1`，避免不同设备的 DPR 差异导致截图像素不一致：

```python
context = browser.new_context(
    viewport={"width": 375, "height": 812},
    device_scale_factor=1,  # 强制 DPR=1
)
```

---

## 运行方式

```bash
# 运行所有响应式视觉测试
pytest tests/visual/ -m visual -k "responsive"

# 只测试移动端
pytest tests/visual/ -m visual -k "responsive" --browser chromium

# 跨浏览器 + 响应式
pytest tests/visual/ -m visual --browser chromium --browser firefox -k "responsive"
```
