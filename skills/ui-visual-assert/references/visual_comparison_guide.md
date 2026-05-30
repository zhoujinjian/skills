# 视觉比对策略指南

## 为什么不用 to_have_screenshot()

Python Playwright **没有** `to_have_screenshot()` / `to_have_screenshot()` 方法。该功能仅限 JavaScript/TypeScript 版本的 Playwright 测试运行器，与 JS 测试框架深度绑定。

Python 方案使用等价组合：`page.screenshot()` + **pixelmatch** + **Pillow**。

---

## pixelmatch 比对原理

pixelmatch 是 JS 库 pixelmatch 的 Python 移植版，逐像素计算颜色距离（YIQ 色彩空间）：

```
对每个像素:
  color_distance = 加权RGB差异
  if color_distance > threshold:
    标记为差异像素
```

### API

```python
from pixelmatch import pixelmatch

mismatched = pixelmatch(
    img1,           # PIL Image（基线）
    img2,           # PIL Image（实际）
    output,         # PIL Image（差异图，会被修改）
    width,
    height,
    threshold=0.1,  # 逐像素颜色容差
    includeAA=False # 是否包含抗锯齿像素
)
# 返回: 差异像素数
```

---

## 阈值调优

### 逐像素阈值（threshold）

| 值 | 含义 | 适用场景 |
|----|------|---------|
| 0.05 | 5% 色差容忍 | 简单形状、图标、纯色背景 |
| 0.10 | 10% 色差容忍（默认） | 大多数页面，平衡灵敏度和稳定性 |
| 0.15 | 15% 色差容忍 | 含渐变、阴影的复杂页面 |
| 0.20 | 20% 色差容忍 | 抗锯齿文本多的页面 |

### 差异比例阈值（max_diff_ratio）

| 值 | 含义 | 适用场景 |
|----|------|---------|
| 0.001 (0.1%) | 极严格 | 图标、Logo 等不允许任何偏差 |
| 0.005 (0.5%) | 严格 | 单个组件、按钮等小元素 |
| 0.01 (1%) | 默认 | 整页截图 |
| 0.02 (2%) | 宽松 | 动态内容较多的页面 |
| 0.05 (5%) | 跨浏览器 | Chromium vs Firefox 全页比对 |

### 调优策略

1. **先用默认值运行**（threshold=0.1, max_diff_ratio=0.01）
2. **查看差异图**：如果差异集中在非功能性区域（字体渲染、阴影），放宽阈值
3. **如果差异在功能性区域**（布局、颜色、间距），保持严格阈值，排查 UI 缺陷
4. **跨浏览器场景**：使用 `cross_browser_tolerance` fixture 提供的浏览器特定容差

---

## 动态区域遮罩

### 方式一：CSS 注入（推荐）

截图前隐藏动态内容，保留布局空间：

```python
login_page.mask_dynamic_regions([
    "img[src*='captcha']",     # 验证码图片
    "img[src*='verify']",
    ".timestamp",              # 时间戳
    ".live-data",              # 实时数据
    ".ad-banner",              # 广告
])
```

原理：注入 `el.style.visibility = 'hidden'`，元素不可见但占据布局空间。

### 方式二：Pillow 像素遮罩

比对时排除指定坐标区域：

```python
page_obj.assert_visual_match(
    "login_page",
    mask_regions=[
        (100, 50, 200, 40),   # (x, y, width, height) — 验证码区域
        (0, 0, 300, 30),      # 顶部时间栏
    ],
)
```

在两张图上绘制相同颜色的矩形，使该区域自动匹配。

### 常见需要遮罩的元素

| 元素类型 | CSS 选择器示例 |
|---------|---------------|
| 验证码图片 | `img[src*='captcha']`, `img[alt*='验证码']` |
| 时间/日期 | `.time`, `.date`, `.timestamp`, `[class*='clock']` |
| 实时数据 | `.live-data`, `.realtime`, `[class*='ticker']` |
| 广告 | `.ad-banner`, `.advertisement`, `[id*='ad-']` |
| 用户名/头像 | `.user-avatar`, `.username`, `[class*='profile']` |
| 随机推荐 | `.recommend`, `.random-list` |

---

## 基线管理

### 生命周期

```
首次运行 → 自动创建基线 → 测试通过
后续运行 → 与基线比对 → 通过/失败
UI 变更  → UPDATE_SNAPSHOTS=true → 覆盖基线 → 提交到 git
比对失败 → 保存差异图 → 人工排查 → 更新基线或修复 UI
```

### 更新基线

```bash
# 方法一：环境变量（推荐）
UPDATE_SNAPSHOTS=true pytest tests/visual/ -m visual

# 方法二：删除特定基线后重新运行
rm tests/visual/baselines/login_page_initial_chromium_1920x1080.png
pytest tests/visual/test_visual_login.py -m visual
```

### 差异图解读

差异图中红色像素标记了不匹配的区域：
- **零星红色像素**：字体渲染差异，可适当放宽阈值
- **大面积红色块**：布局或颜色有显著变化，需要排查
- **边缘红色线**：可能是边框或阴影差异

---

## 截图稳定性保障

截图前确保页面处于稳定状态：

```python
# 1. 等待网络空闲
page.wait_for_load_state("networkidle")

# 2. 等待特定元素可见
page.locator(".main-content").wait_for(state="visible")

# 3. 等待字体加载
page.evaluate("document.fonts.ready")

# 4. 禁用动画（自动注入）
# *, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }

# 5. 统一 device_scale_factor=1（避免 DPR 差异）
```

### 图片格式

始终使用 **PNG** 格式（`type="png"`）。JPEG 有损压缩会引入不可控的像素差异。

### 全页 vs 视口截图

| 模式 | 适用场景 |
|------|---------|
| `full_page=True` | 验证完整页面布局，适合首页、列表页 |
| `full_page=False` | 只截取视口区域，适合验证首屏效果 |

---

## 性能优化

对于大型页面，全页截图可能很大（>5MB），影响比对速度：

1. **只截取关键区域**：使用 `assert_element_visual()` 只比对重要组件
2. **限制全页高度**：通过 `page.screenshot(clip={"x": 0, "y": 0, "width": 1920, "height": 1080})` 只截取首屏
3. **numpy 加速**：安装 numpy 后自动使用数组运算加速像素比对
