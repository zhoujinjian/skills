# 跨浏览器兼容性测试指南

## 浏览器引擎差异

三大浏览器引擎在截图时会产生固有渲染差异：

### Chromium (Blink)

- 字体渲染：ClearType / DirectWrite（Windows）、CoreText（macOS）
- 滚动条宽度：15px（Windows）
- 表单控件：标准样式
- **作为视觉基线的基准浏览器**，差异容差最低（0.10）

### Firefox (Gecko)

- 字体渲染：与 Chromium 有细微差异（抗锯齿算法不同）
- 滚动条宽度：17px（比 Chromium 宽 2px）
- 表单控件：`<select>`、`<input type="range">` 样式不同
- 差异容差：0.15（比 Chromium 宽松 50%）

### WebKit (Safari)

- 字体渲染：字体平滑（-webkit-font-smoothing）差异
- 部分浏览器前缀 CSS 行为不同
- 表单控件：iOS 风格滚动和按钮
- 差异容差：0.12

---

## 基线命名策略

每个浏览器维护独立基线，避免渲染差异导致误报：

```
tests/visual/baselines/
├── login_page_initial_chromium_1920x1080.png
├── login_page_initial_firefox_1920x1080.png
├── login_page_initial_webkit_1920x1080.png
├── home_page_responsive_chromium_375x812.png
└── home_page_responsive_firefox_375x812.png
```

命名规则：`{snapshot_name}_{browser}_{width}x{height}.png`

---

## 跨浏览器容差配置

`cross_browser_tolerance` fixture 自动根据当前浏览器返回适当阈值：

```python
BROWSER_TOLERANCE = {
    "chromium": 0.10,
    "firefox":  0.15,
    "webkit":   0.12,
}
```

### 在测试中使用

```python
def test_login_visual(self, page, cross_browser_tolerance):
    login_page = LoginPage(page).navigate()
    login_page.assert_visual_match(
        "login_page_initial",
        threshold=cross_browser_tolerance,  # 自动适配当前浏览器
    )
```

### 自定义容差

```python
# 覆盖默认容差
def test_login_strict(self, page):
    login_page = LoginPage(page).navigate()
    login_page.assert_visual_match(
        "login_page_initial",
        threshold=0.05,  # 所有浏览器使用相同严格阈值
    )
```

---

## 浏览器特定问题处理

### Firefox 滚动条宽度差异

Firefox 滚动条比 Chromium 宽 2px，可能导致全页截图宽度和布局微小差异。

**处理方式**：截图前注入 CSS 统一滚动条：

```python
page.add_style_tag(content="""
    ::-webkit-scrollbar { width: 0 !important; }
    * { scrollbar-width: none !important; }
""")
```

### Firefox 元素点击偏移

Firefox 中元素边界渲染有 1px 偏移，影响元素级截图的比对。

**处理方式**：元素截图前确保元素无滚动、无部分遮挡：

```python
# 滚动到元素可见区域
locator.scroll_into_view_if_needed()
page.wait_for_timeout(100)  # 等待滚动稳定
```

### WebKit 字体平滑

Safari/WebKit 的字体平滑（font smoothing）与 Chromium 不同，导致文字渲染像素差异。

**处理方式**：在响应式/跨浏览器测试中放宽阈值即可，或在截图前统一字体平滑：

```python
page.add_style_tag(content="""
    * {
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }
""")
```

### 表单控件样式差异

`<select>`、`<input type="range">`、`<progress>` 在各浏览器中默认样式差异显著。

**处理方式**：
1. 元素级截图时避免包含原生表单控件的外框
2. 或者只比对自定义样式的表单元素

---

## 运行跨浏览器测试

### 安装浏览器

```bash
# 安装所有浏览器
python3 -m playwright install

# 或单独安装
python3 -m playwright install firefox
python3 -m playwright install webkit
```

### 运行命令

```bash
# 单个浏览器
pytest tests/visual/ -m visual --browser chromium

# 多个浏览器（串行）
pytest tests/visual/ -m visual --browser chromium --browser firefox --browser webkit

# 多浏览器 + 并行（需要 pytest-xdist）
pip install pytest-xdist
pytest tests/visual/ -m visual \
    --browser chromium --browser firefox --browser webkit \
    --numprocesses auto

# 更新特定浏览器的基线
UPDATE_SNAPSHOTS=true pytest tests/visual/ -m visual --browser firefox
```

### CI/CD 集成

```yaml
# .github/workflows/visual-tests.yml
name: Visual Regression
on: [push, pull_request]
jobs:
  visual:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        browser: [chromium, firefox, webkit]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python -m playwright install --with-deps
      - run: pytest tests/visual/ -m visual --browser ${{ matrix.browser }}
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: visual-diffs-${{ matrix.browser }}
          path: tests/visual/diff/
```

---

## 容差调优建议

| 场景 | Chromium | Firefox | WebKit | 说明 |
|------|----------|---------|--------|------|
| 简单页面（文字+色块） | 0.05 | 0.08 | 0.06 | 渲染差异很小 |
| 表单页面 | 0.10 | 0.15 | 0.12 | 表单控件样式差异 |
| 复杂页面（渐变+阴影） | 0.10 | 0.15 | 0.12 | 默认值 |
| 含抗锯齿文字 | 0.15 | 0.20 | 0.18 | 字体渲染差异大 |
| 含动态内容（需遮罩） | 0.10 | 0.15 | 0.12 | 遮罩后使用默认值 |

---

## 已知限制

1. **WebKit 在 Linux 上不支持**：Playwright 的 WebKit 仅在 macOS 上完整支持，Linux 上行为可能异常
2. **系统字体差异**：不同操作系统的系统字体不同，影响文字渲染。CI 环境应统一安装测试字体
3. **GPU 渲染差异**：无头模式下 GPU 加速行为不同，可能影响 Canvas、WebGL 内容的截图
4. **时区/语言**：确保所有浏览器使用相同的 locale 和时区设置
