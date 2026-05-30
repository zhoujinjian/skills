---
name: ui-testscript-enhancer
description: "对已生成的 Playwright + POM + Pytest UI 测试脚本做自动化增强，补充智能等待、验证码识别、弹窗处理、iframe 切换、异常重试、失败截图录屏等能力，提升脚本运行稳定性。当用户需要以下场景时触发：增强测试脚本、脚本健壮性优化、添加智能等待、处理验证码、处理弹窗、iframe 处理、异常重试、失败截图、测试稳定性提升、脚本加固。即使用户只是说"脚本跑不稳定"、"经常失败"、"flaky test"，也应使用此技能。"
---

# ui-testscript-enhancer — UI 测试脚本增强技能

## 技能定位

对 `ui-testscript-generator` 输出的基础 UI 测试脚本做**健壮性增强**，解决以下常见问题：

- 页面加载慢 / 元素未就绪导致定位失败
- 验证码阻断自动化流程
- 意外弹窗（广告、权限申请）干扰执行
- iframe / Shadow DOM 内元素无法定位
- 网络抖动 / 页面无响应导致脚本中断
- 失败后缺乏追溯信息（截图、录屏、网络日志）

**增强原则**：不改变原有测试逻辑和业务断言，只在脚本外围包裹稳定性机制。

---

## 输入识别

| 输入 | 必需 | 说明 |
|------|------|------|
| 基础测试脚本 | 是 | ui-testscript-generator 输出的 POM + test 文件 |
| 页面交互规则 | 否 | 用户提供的特殊处理规则（验证码类型、弹窗触发条件、异步加载模式等） |

### 脚本定位

如果用户没有指定具体文件路径，按以下顺序查找：
1. 当前目录及子目录下的 `pages/` 和 `tests/` 目录
2. `ui-test-automation/` 项目目录
3. 用户直接提供的文件内容

---

## 工作流程

### Phase 1：扫描基础脚本，识别增强点

读取基础测试脚本，逐文件分析需要增强的场景：

#### 1.1 扫描 POM 类

对每个 `_page.py` 文件检查：

| 检查项 | 增强动作 |
|--------|---------|
| `navigate()` 方法使用 `page.goto(url)` | 替换为 `page.goto(url, wait_until="networkidle")` |
| 直接 `.click()` 无等待 | 替换为 `safe_click()`（先等待可见再点击） |
| 直接 `.fill()` 无等待 | 替换为 `safe_fill()`（先等待可编辑再填写） |
| 无异常捕获的操作方法 | 添加重试装饰器 |
| 页面跳转方法无等待目标页 | 添加 `expect(page).to_have_url()` 等待 |
| 含 iframe/Shadow DOM 的页面 | 生成 iframe 切换方法 |
| 登录页含验证码逻辑 | 接入验证码识别方案 |

#### 1.2 扫描测试脚本

对每个 `test_*.py` 文件检查：

| 检查项 | 增强动作 |
|--------|---------|
| 无失败截图机制 | 注入 pytest hook 自动截图 |
| 无 Trace 录制配置 | 添加 playwright.cfg 配置 |
| 弹窗未处理 | 添加 `page.on("dialog")` 监听 |
| 无网络请求监控 | 添加 `page.on("response")` 日志 |
| 无全局异常处理 | 添加 `pytest_exception_interact` hook |

#### 1.3 输出增强清单

```
📋 增强计划:
  pages/auth/login_page.py:
    ✅ navigate → 添加 networkidle 等待
    ✅ click_login → 替换为 safe_click + 重试
    ✅ fill_captcha → 接入验证码识别
    ⚠️  新增: _handle_unexpected_dialog 弹窗处理
  tests/auth/test_login.py:
    ✅ 添加 conftest 失败自动截图 hook
    ✅ 添加网络请求日志记录
  全局:
    ✅ enhanced_base_page.py → 替换原有 base_page.py
    ✅ utils/retry_decorator.py → 重试机制
    ✅ utils/captcha_solver.py → 验证码识别
```

---

### Phase 2：增强 BasePage 基类

将原有的 `base_page.py` 替换为增强版 `enhanced_base_page.py`，新增以下能力：

#### 智能等待方法

```python
def wait_for_page_ready(self, timeout: int = 30000):
    """等待页面完全加载（网络空闲 + DOM 稳定）"""
    self.page.wait_for_load_state("networkidle", timeout=timeout)
    self.page.wait_for_load_state("domcontentloaded", timeout=timeout)

def wait_for_ajax(self, api_pattern: str = "**/api/**", timeout: int = 15000):
    """等待指定 API 请求完成"""
    with self.page.expect_response(api_pattern, timeout=timeout) as resp:
        yield resp.value

def wait_for_animation(self, locator: Locator, timeout: int = 5000):
    """等待 CSS 动画/过渡完成"""
    locator.wait_for(state="visible", timeout=timeout)
    self.page.wait_for_timeout(300)  # transition buffer

def safe_click(self, locator: Locator, retries: int = 3):
    """安全点击：等待 → 重试 → 截图"""
    ...

def safe_fill(self, locator: Locator, value: str, retries: int = 3):
    """安全填写：等待可编辑 → 清空 → 填写"""
    ...
```

详细实现参考 `assets/enhanced_base_page.py`。

#### 弹窗自动处理

```python
def dismiss_unexpected_dialog(self):
    """自动关闭意外弹窗（alert/confirm/prompt）"""
    self.page.on("dialog", lambda dialog: dialog.dismiss())
```

#### iframe 穿透

```python
def enter_iframe(self, iframe_selector: str) -> FrameLocator:
    return self.page.frame_locator(iframe_selector)

def leave_iframe(self):
    """自动回到主框架"""
    # FrameLocator 操作完自动回主框架
```

详细方法参考 `references/popup_iframe_guide.md`。

---

### Phase 3：添加重试与容错机制

#### 3.1 操作级重试装饰器

为 POM 方法添加 `@retry_on_failure` 装饰器：

```python
@retry_on_failure(max_retries=3, delay=1.0, screenshot=True)
def click_login(self) -> "HomePage":
    self._login_button.click()
    return HomePage(self.page)
```

- 元素未找到 → 重试
- 超时 → 重试
- 重试耗尽 → 自动截图 + 记录日志 + 抛出异常

详细实现参考 `assets/retry_decorator.py`。

#### 3.2 页面级恢复机制

```python
def recover_page(self):
    """页面崩溃/无响应时自动恢复"""
    try:
        self.page.reload(wait_until="networkidle")
    except Exception:
        self.page.goto(self.page.url, wait_until="networkidle")
```

---

### Phase 4：验证码识别方案

根据用户提供的验证码类型，选择对应的识别策略：

| 验证码类型 | 识别方案 | 说明 |
|-----------|---------|------|
| 图形验证码 | OCR（ddddocr） | 开源 OCR，离线识别 |
| 滑动验证码 | 视觉分析 + 模拟拖拽 | 计算滑块偏移量 |
| 文字点选验证码 | OCR + 坐标匹配 | 识别文字位置 |
| 计算题验证码 | 表达式解析 | 提取并计算 |
| 短信验证码 | API/数据库查询 | 从后端获取 |
| 第三方验证码 | 打码平台 API | 2Captcha / 超级鹰等 |

#### 集成方式

在 POM 类中替换硬编码的验证码值：

```python
# 增强前
def fill_captcha(self, code: str) -> "LoginPage":
    self._captcha_input.fill(code)
    return self

# 增强后
def fill_captcha(self) -> "LoginPage":
    code = self._solve_captcha()
    self._captcha_input.fill(code)
    return self

def _solve_captcha(self) -> str:
    """自动识别验证码"""
    captcha_image = self._captcha_image.screenshot()
    return CaptchaSolver.solve_image(captcha_image)
```

详细方案参考 `references/captcha_guide.md`。

---

### Phase 5：失败追溯增强

#### 5.1 自动截图

在 `conftest.py` 中添加 pytest hook：

```python
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page:
            screenshot_path = f"screenshots/{item.name}.png"
            page.screenshot(path=screenshot_path, full_page=True)
            report.extra = [{"name": "screenshot", ...}]
```

#### 5.2 Trace 录制配置

在 `conftest.py` 的 browser context 配置中添加：

```python
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "record_trace": True,
        "record_video": True,
        "screenshot": "only-on-failure",
        "trace": "retain-on-failure",
        "video": "retain-on-failure",
    }
```

#### 5.3 网络请求日志

```python
@pytest.fixture(autouse=True)
def log_network_requests(page, request):
    """自动记录每个测试的网络请求"""
    logs = []
    page.on("response", lambda resp: logs.append(
        f"{resp.status} {resp.url}"
    ))
    yield
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        with open(f"reports/network_{request.node.name}.log", "w") as f:
            f.write("\n".join(logs))
```

详细配置参考 `references/failure_trace_guide.md`。

---

### Phase 6：生成增强报告

增强完成后，输出增强摘要：

```
📦 增强完成:
  修改文件: 4 个
    ✅ pages/base_page.py → enhanced_base_page.py（新增 8 个方法）
    ✅ pages/auth/login_page.py（3 处增强）
    ✅ pages/auth/register_page.py（2 处增强）
    ✅ tests/conftest.py（新增 3 个 hook）
  新增文件: 3 个
    ✅ utils/retry_decorator.py
    ✅ utils/captcha_solver.py
    ✅ utils/popup_handler.py
  增强统计:
    智能等待: 6 处
    重试机制: 3 个方法
    弹窗处理: 2 处
    失败截图: 全局 hook
    Trace 录制: 全局配置

⚠️ 需要手动确认:
    验证码类型 → 当前按"图形验证码"处理，如类型不同请告知
    打码平台 API Key → 需在 config/settings.py 中配置
```

---

## 验证码识别专项检测（独立使用）

提供独立脚本，可脱离测试项目单独运行，快速验证验证码识别功能是否有效。

### 使用场景

- 验证码集成到 POM 之前，先确认 OCR 识别准确率
- 页面验证码类型变更后，快速校验识别是否仍然有效
- 对比不同识别方案（OCR vs 打码平台）的准确率

### 运行方式

```bash
SCRIPT_DIR=~/.claude/skills/ui-testscript-enhancer/scripts

# 基础用法：单次识别
python3 "${SCRIPT_DIR}/test_captcha.py" http://localhost:3000/login

# 多轮识别（刷新验证码，统计准确率）
python3 "${SCRIPT_DIR}/test_captcha.py" http://localhost:3000/login --rounds 5

# 自定义验证码选择器（自动定位失败时）
python3 "${SCRIPT_DIR}/test_captcha.py" http://localhost:3000/login --selector "img.captcha-img"

# 有头模式（观察浏览器行为）
python3 "${SCRIPT_DIR}/test_captcha.py" http://localhost:3000/login --headed

# 指定输出目录
python3 "${SCRIPT_DIR}/test_captcha.py" http://localhost:3000/login -o ./my_captcha_test
```

### 输出示例

```
============================================================
  验证码识别专项测试
============================================================
  目标 URL:  http://localhost:3000/login
  识别轮数:  3
  输出目录:  ./captcha_test_output/20260529_100000

--- 第 1/3 轮 ---
  定位选择器: img[src*='captcha']
  图片尺寸:   120x40
  图片 src:   /api/captcha?t=1748...
  识别结果:   【a7k2】
  页面截图:   ./captcha_test_output/20260529_100000/round_1/page_context.png

--- 第 2/3 轮 ---
  ...

============================================================
  识别汇总
============================================================
  总轮数:     3
  成功识别:   3
  识别失败:   0

  各轮识别结果:
    轮 1: 【a7k2】
    轮 2: 【x9m4】
    轮 3: 【p3f8】

  📂 所有截图保存在: ./captcha_test_output/20260529_100000
  请打开截图与识别结果对比，验证识别准确度
```

### 输出文件结构

```
captcha_test_output/20260529_100000/
├── round_1/
│   ├── captcha_raw.png       # 验证码图片原始截图
│   └── page_context.png      # 页面完整截图（含验证码上下文）
├── round_2/
│   ├── captcha_raw.png
│   └── page_context.png
└── round_3/
    ├── captcha_raw.png
    └── page_context.png
```

用户打开 `captcha_raw.png` 可直接看到验证码原图，与终端输出的 `识别结果` 文字对比，即可判断 OCR 准确度。

### 定位器优先级

脚本内置多种验证码选择器，按优先级依次尝试：

1. `img[src*='captcha']` — src 包含 captcha
2. `img[src*='verify']` — src 包含 verify
3. `img[src*='code']` — src 包含 code
4. `img[src*='CheckCode']` — src 包含 CheckCode
5. `#captcha-img`, `img.captcha-img` — id/class 匹配
6. `img[alt*='验证码']` — alt 文本匹配
7. 通用 `img` + 尺寸/属性过滤兜底

如果所有选择器都无法匹配，使用 `--selector` 参数手动指定。

---

## 参考文件索引

| 文件 | 用途 | 读取时机 |
|------|------|---------|
| `references/smart_wait_guide.md` | 智能等待策略详解 | Phase 2 增强 BasePage 时 |
| `references/captcha_guide.md` | 验证码识别方案 | Phase 4 处理验证码时 |
| `references/popup_iframe_guide.md` | 弹窗与 iframe 处理 | Phase 2/3 时 |
| `references/failure_trace_guide.md` | 失败追溯配置 | Phase 5 时 |
| `assets/enhanced_base_page.py` | 增强版 BasePage 完整实现 | 替换项目中的 base_page.py |
| `assets/retry_decorator.py` | 重试装饰器 | 添加到项目 utils/ |
| `assets/captcha_solver.py` | 验证码识别模块 | 添加到项目 utils/ |
| `assets/popup_handler.py` | 弹窗处理器 | 添加到项目 utils/ |
| `assets/enhanced_conftest.py` | 增强版 conftest hooks | 合并到项目 conftest.py |
| `scripts/test_captcha.py` | 验证码识别专项测试脚本 | 独立运行，验证 OCR 识别准确率 |
