---
name: ui-visual-assert
description: "对已增强的 Playwright + POM + Pytest UI 测试脚本添加视觉回归、跨浏览器兼容性、响应式布局测试能力。使用 pixelmatch + Pillow 实现像素级截图比对（Python 原生方案），支持动态区域遮罩、元素级截图断言、多视口自适应、Chromium/Firefox/WebKit 三引擎差异容忍。当用户需要以下场景时触发：视觉回归测试、截图比对、UI 外观验证、跨浏览器测试、多浏览器兼容性、响应式测试、多视口测试、移动端适配测试、视觉快照、像素对比、baseline 更新、视觉差异检测、页面变形检测。即使用户只是说'页面改版了看看有没有变形'、'不同浏览器下样式一致吗'、'手机端布局对不对'，也应使用此技能。"
---

# ui-visual-assert — UI 视觉断言技能

## 技能定位

对 `ui-testscript-enhancer` 输出的增强测试脚本添加**视觉回归测试**能力，解决以下问题：

- 无法验证页面视觉展示是否符合预期（只有 DOM/文本断言）
- 页面改版后样式变形难以自动发现
- 不同浏览器下渲染差异无感知
- 移动端/平板布局错位无校验
- 动态内容（时间戳、验证码）干扰截图比对

**增强原则**：不改变已有测试逻辑，只新增视觉断言层。基于 Playwright 原生截图 + pixelmatch 像素比对实现，无需第三方云服务。

---

## 输入识别

| 输入 | 必需 | 说明 |
|------|------|------|
| 增强测试脚本 | 是 | ui-testscript-enhancer 输出的 POM + test + conftest 文件 |
| 视觉基线图 | 否 | 首次执行自动生成，后续执行自动比对 |
| 视觉断言规则 | 否 | 用户指定的动态区域、自定义阈值、特殊元素等 |

### 脚本定位

如果用户没有指定具体文件路径，按以下顺序查找：
1. 当前目录及子目录下的 `pages/` 和 `tests/` 目录
2. `ui-test-automation/` 项目目录
3. 用户直接提供的文件内容

---

## 技术背景

> **重要**：Python Playwright **没有** `to_have_screenshot()` 方法（该功能仅限 JavaScript/TypeScript 版本）。
> 本技能使用 `page.screenshot()` + **pixelmatch**（像素比对库）+ **Pillow**（图像处理库）实现等价能力，
> 并内置 Pillow + numpy 降级方案，确保 pixelmatch 不可用时仍可正常工作。

---

## 工作流程

### Phase 1：扫描脚本，识别视觉断言目标

读取现有 POM 类和测试脚本，分析需要视觉覆盖的场景：

#### 1.1 扫描 POM 类

对每个 `_page.py` 文件检查：

| 检查项 | 视觉测试动作 |
|--------|-------------|
| 页面有 `navigate()` 方法 | 生成该页面初始状态全页截图比对 |
| 页面含动态内容（验证码、时间戳、随机广告） | 生成动态区域遮罩配置 |
| 页面有表单元素 | 生成表单区域元素级截图比对 |
| 页面有状态切换（登录前/后、展开/收起） | 生成多状态截图比对 |

#### 1.2 扫描 conftest

读取 `browser_context_args` 了解当前视口配置，确定响应式测试的基准尺寸。

#### 1.3 输出视觉断言计划

```
📋 视觉断言计划:
  pages/auth/login_page.py:
    ✅ 全页截图: 登录页初始状态
    ✅ 元素截图: 登录表单区域
    ⚠️  动态区域: 验证码图片 → CSS 遮罩
  pages/home/home_page.py:
    ✅ 全页截图: 未登录状态 / 已登录状态
    ✅ 响应式测试: desktop / tablet / mobile
  全局:
    ✅ utils/visual_comparator.py → 像素级比对引擎
    ✅ 基线目录: tests/visual/baselines/
    ✅ 跨浏览器容差: chromium(0.10) / firefox(0.15) / webkit(0.12)
```

---

### Phase 2：生成视觉比对引擎

将 `assets/visual_comparator.py` 复制到项目 `utils/` 目录。

#### 核心类：VisualComparator

```python
class VisualComparator:
    def __init__(
        self,
        threshold: float = 0.1,       # 逐像素颜色容差（0.0-1.0）
        max_diff_ratio: float = 0.01,  # 最大允许差异像素比例（1%）
        diff_color: tuple = (255, 0, 0),  # 差异像素高亮色（红色）
    ):
        ...

    def compare(
        self,
        baseline_path: str,
        actual_path: str,
        diff_path: str,
        mask_regions: list[tuple] | None = None,
    ) -> VisualResult:
        """像素级比对，返回比对结果"""
        ...
```

#### 返回数据类：VisualResult

```python
@dataclass
class VisualResult:
    passed: bool               # 是否通过
    mismatch_percentage: float # 差异百分比
    diff_path: str            # 差异图路径
    mismatched_pixels: int    # 差异像素数
    total_pixels: int         # 总像素数
```

#### 比对流程

1. 加载基线图和实际截图（Pillow）
2. 尺寸不一致时，将实际图缩放至基线尺寸（记录警告）
3. 如有遮罩区域，在两张图上绘制黑色矩形排除比对
4. 使用 pixelmatch 逐像素比对（或降级到 Pillow + numpy）
5. 生成差异图（红色标记差异像素）
6. 判断差异比例是否在阈值内

详细实现参考 `assets/visual_comparator.py`。

---

### Phase 3：生成响应式与跨浏览器 Fixtures

将 `assets/visual_conftest.py` 中的 fixtures 合并到项目 `tests/conftest.py`。

#### 响应式视口预设

```python
VIEWPORT_PRESETS = {
    "desktop": {"width": 1920, "height": 1080},
    "tablet":  {"width": 768,  "height": 1024},
    "mobile":  {"width": 375,  "height": 812},
}
```

#### 跨浏览器容差配置

```python
BROWSER_TOLERANCE = {
    "chromium": 0.10,   # 基准浏览器
    "firefox":  0.15,   # 字体渲染、滚动条宽度差异
    "webkit":   0.12,   # Safari 字体平滑差异
}
```

#### 新增 Fixtures

| Fixture | 作用 |
|---------|------|
| `viewport_preset` | 参数化视口选择（配合 `@pytest.mark.parametrize`） |
| `responsive_context` | 创建指定视口的浏览器上下文 + 禁用动画 |
| `visual_baseline_dir` | 确保基线目录存在 |
| `update_snapshots` | 读取 `UPDATE_SNAPSHOTS` 环境变量 |
| `cross_browser_tolerance` | 根据当前浏览器返回容差阈值 |

详细实现参考 `assets/visual_conftest.py`。

---

### Phase 4：生成视觉测试脚本

在 `tests/visual/` 下生成测试文件。

#### 4.1 增强现有 BasePage

将 `assets/visual_base_page.py` 中的方法合并到项目 `pages/base_page.py`：

```python
def assert_visual_match(
    self,
    snapshot_name: str,
    threshold: float | None = None,
    mask_regions: list[tuple] | None = None,
    full_page: bool = True,
) -> "BasePage":
    """全页截图视觉断言"""
    ...

def assert_element_visual(
    self,
    locator,
    snapshot_name: str,
    threshold: float | None = None,
) -> "BasePage":
    """元素级截图视觉断言"""
    ...

def mask_dynamic_regions(self, css_selectors: list[str]) -> "BasePage":
    """注入 CSS 隐藏动态内容（保留布局空间）"""
    ...
```

#### 4.2 生成视觉测试文件

测试文件模板参考 `assets/visual_test_template.py`，生成模式：

| 测试类型 | 方法名 | 说明 |
|---------|--------|------|
| 全页截图 | `test_<page>_full_visual` | 页面加载后整页与基线比对 |
| 元素截图 | `test_<page>_<element>_visual` | 特定元素区域与基线比对 |
| 响应式 | `test_<page>_responsive` | 参数化 desktop/tablet/mobile 三视口 |

#### 4.3 动态区域处理

截图前通过 CSS 注入隐藏动态内容：

```python
login_page.mask_dynamic_regions([
    "img[src*='captcha']",   # 验证码图片
    "img[src*='verify']",
    ".timestamp",            # 时间戳
])
```

---

### Phase 5：跨浏览器兼容处理

#### 基线命名策略

```
tests/visual/baselines/
├── login_page_initial_chromium_1920x1080.png
├── login_page_initial_firefox_1920x1080.png
├── login_page_responsive_chromium_375x812.png
└── home_page_guest_chromium_1920x1080.png
```

命名规则：`{snapshot_name}_{browser}_{width}x{height}.png`

每个浏览器+视口组合独立基线，避免不同引擎渲染差异导致误报。

#### 截图前预处理

所有视觉测试截图前自动执行：

1. 禁用 CSS 动画和过渡（消除动画状态不确定性）
2. 等待网络空闲（`networkidle`）
3. 等待字体加载完成（`document.fonts.ready`）
4. 统一滚动条样式（消除浏览器间滚动条宽度差异）

#### Firefox 特殊处理

- 元素截图时偏移修正 1px（Firefox 的元素边界渲染差异）
- 滚动条宽度差异（Firefox 17px vs Chromium 15px）→ 注入 `overflow: hidden`

详细方案参考 `references/cross_browser_guide.md`。

---

### Phase 6：生成增强报告

增强完成后，输出增强摘要：

```
📦 视觉测试增强完成:
  修改文件: 4 个
    ✅ pages/base_page.py（新增 6 个视觉断言方法）
    ✅ tests/conftest.py（新增 5 个 fixtures）
    ✅ requirements.txt（新增 pixelmatch, Pillow）
    ✅ pytest.ini（新增 visual marker）
  新增文件: 5 个
    ✅ utils/visual_comparator.py → 像素级比对引擎
    ✅ tests/visual/test_visual_login.py → 登录页视觉测试
    ✅ tests/visual/test_visual_home.py → 首页视觉测试
    ✅ tests/visual/baselines/ → 基线图目录（首次运行自动生成）
    ✅ .gitignore → 排除 actual/、diff/ 临时目录

🏃 运行方式:
  pytest tests/visual/ -m visual --headed
  UPDATE_SNAPSHOTS=true pytest tests/visual/ -m visual   # 更新基线
  pytest tests/visual/ -m visual --browser chromium --browser firefox  # 跨浏览器

⚠️ 提示:
    首次运行会自动创建基线图，请人工确认基线正确后再提交到 git
    动态区域遮罩选择器请根据实际页面调整
```

---

## 基线管理

### 生命周期

| 阶段 | 行为 |
|------|------|
| 首次运行 | 截图 → 保存为基线 → 测试通过 |
| 后续运行 | 截图 → 与基线比对 → 通过/失败 |
| UI 变更 | `UPDATE_SNAPSHOTS=true` → 覆盖基线 → 提交新基线 |
| 比对失败 | 保存差异图到 `diff/` → 人工排查 |

### 目录结构

```
tests/visual/
├── __init__.py
├── baselines/          # 基线图（提交到 git）
│   ├── login_page_initial_chromium_1920x1080.png
│   └── home_page_guest_chromium_1920x1080.png
├── actual/             # 实际截图（.gitignore）
├── diff/               # 差异图（.gitignore）
├── test_visual_login.py
└── test_visual_home.py
```

---

## 参考文件索引

| 文件 | 用途 | 读取时机 |
|------|------|---------|
| `references/visual_comparison_guide.md` | 比对策略、阈值调优、遮罩技巧 | Phase 2 生成比对引擎时 |
| `references/responsive_testing_guide.md` | 视口配置、设备模拟、响应式断言 | Phase 3 生成响应式 fixtures 时 |
| `references/cross_browser_guide.md` | 浏览器差异、容差配置、兼容性处理 | Phase 5 跨浏览器处理时 |
| `assets/visual_comparator.py` | 像素级比对引擎完整实现 | 复制到项目 utils/ |
| `assets/visual_base_page.py` | BasePage 视觉断言扩展方法 | 合并到项目 pages/base_page.py |
| `assets/visual_conftest.py` | 响应式/跨浏览器 fixtures | 合并到项目 tests/conftest.py |
| `assets/visual_test_template.py` | 视觉测试文件生成模板 | Phase 4 生成测试脚本时 |
