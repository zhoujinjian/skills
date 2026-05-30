# 团队 UI 自动化测试框架规范

本文件定义了团队统一的 UI 自动化测试框架标准，所有生成的测试代码必须遵循此规范。

---

## 一、框架技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| 开发语言 | Python 3.10+ | 类型注解、match-case 等现代特性 |
| 自动化驱动 | Playwright | 多浏览器、自动等待、稳定定位 |
| 设计模式 | POM（页面对象模型） | 元素与逻辑分离 |
| 测试框架 | Pytest | 用例管理、断言、夹具、参数化 |
| 报告工具 | Allure（可选） | 可视化测试报告 |
| 配置管理 | YAML | 环境、元素、测试数据统一管理 |

---

## 二、目录结构

```
ui-test-automation/
├── config/                     # 配置管理
│   ├── __init__.py
│   ├── settings.py             # 全局配置（环境、超时、浏览器）
│   └── environments/           # 环境隔离配置
│       ├── dev.yaml
│       ├── staging.yaml
│       └── prod.yaml
├── pages/                      # 页面对象层（POM）
│   ├── __init__.py
│   ├── base_page.py            # 所有 Page 的基类
│   ├── components/             # 可复用 UI 组件
│   │   ├── header.py
│   │   ├── modal.py
│   │   └── sidebar.py
│   └── [module]/               # 按业务模块划分
│       ├── __init__.py
│       ├── login_page.py
│       └── dashboard_page.py
├── workflows/                  # 业务工作流（跨页面操作组合）
│   ├── __init__.py
│   └── user_journey.py
├── tests/                      # 测试用例层
│   ├── __init__.py
│   ├── conftest.py             # pytest fixtures 定义
│   ├── fixtures/               # 自定义 fixtures
│   │   ├── auth_fixture.py
│   │   └── data_fixture.py
│   └── [module]/               # 按模块对应 pages
│       ├── test_login.py
│       └── test_dashboard.py
├── utils/                      # 工具层
│   ├── __init__.py
│   ├── logger.py               # 日志封装
│   ├── screenshot_helper.py    # 截图辅助
│   └── data_factory.py         # 测试数据生成
├── data/                       # 测试数据
│   ├── test_data.json
│   └── test_data.yaml
├── reports/                    # 测试报告输出（gitignore）
├── traces/                     # Playwright trace（gitignore）
├── screenshots/                # 失败截图（gitignore）
├── pytest.ini                  # pytest 配置
├── requirements.txt
└── README.md
```

---

## 三、POM 页面类编写规范

### 规范要求

1. **单一职责**：每个页面对应一个 class，类名大驼峰（`LoginPage`、`HomePage`）
2. **定位器私有化**：元素定位统一写在类顶部，使用 `self._element_name`，禁止在测试文件中直接使用
3. **行为封装**：每个操作封装为一个方法，方法名见名知意（`fill_username()`、`click_login()`）
4. **方法只做动作封装，不写业务断言**
5. **参数化**：方法接受输入参数，支持多数据集复用
6. **链式调用**：同页操作返回 `self`，页面跳转返回目标 Page 对象

### 定位器选择优先级

| 优先级 | Playwright API | 示例 | 适用场景 |
|--------|---------------|------|---------|
| 1 | `get_by_role()` | `page.get_by_role("button", name="提交")` | 有 role/aria 信息 |
| 2 | `get_by_test_id()` | `page.get_by_test_id("submit-btn")` | 有 data-testid |
| 3 | `get_by_label()` | `page.get_by_label("邮箱地址")` | 表单 label |
| 4 | `get_by_placeholder()` | `page.get_by_placeholder("请输入邮箱")` | 输入框 placeholder |
| 5 | `get_by_text()` | `page.get_by_text("确认删除")` | 精确文本匹配 |
| 6 | `locator(css)` | `page.locator(".submit-btn")` | 兜底方案 |

**禁止使用**：
- 动态 id（如 `el-id-3286-1`）
- XPath
- 深层嵌套 CSS（如 `div.x > span.y:nth-child(2)`）
- 纯数字索引定位

### BasePage 基类规范

所有 Page 类继承 `BasePage`，BasePage 封装：
- `wait_for_locator()` — 显式等待元素可见
- `safe_click()` — 安全点击（等待 + 点击）
- `take_screenshot()` — 截图保存
- `get_page_title()` — 获取页面标题
- `refresh()` / `go_back()` — 导航操作

---

## 四、测试用例编写规范

1. 文件以 `test_*.py` 命名
2. 方法以 `test_*` 命名，格式：`test_<verb>_<expected_result>`
3. **测试独立性**：每个测试独立，不依赖其他测试状态
4. **一个用例一个核心业务点**
5. 结构：前置操作 → 执行步骤 → 断言 → 清理（可选）
6. **不直接写定位器**，全部调用 POM 类方法
7. 断言使用 pytest + Playwright expect

### 断言规范

```python
# 推荐：使用 Playwright expect
from playwright.sync_api import expect
expect(page).to_have_url("/dashboard")
expect(locator).to_be_visible()
expect(locator).to_have_text("登录成功")

# 也支持：pytest 断言 + 失败说明
assert "成功" in message, f"期望包含'成功'，实际为: {message}"
```

---

## 五、等待规范

**禁止使用 `time.sleep()`**，统一使用 Playwright 自动等待：

```python
# 等待元素可见
locator.wait_for(state="visible", timeout=10000)

# 等待 URL 变化
expect(page).to_have_url("/dashboard")

# 等待网络空闲
page.wait_for_load_state("networkidle")

# 等待 API 响应
with page.expect_response("/api/login") as response:
    login_button.click()
```

---

## 六、Fixtures 规范

```python
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "locale": "zh-CN",
    }

@pytest.fixture
def auth_page(page, test_user) -> LoginPage:
    """已认证页面"""
    login_page = LoginPage(page)
    login_page.navigate().login(test_user.username, test_user.password)
    return login_page
```

---

## 七、运行与调试

### 运行命令

```bash
# 本地调试（有头模式 + 慢动作）
pytest tests/ --headed --slow-mo=200

# CI 运行（无头模式 + 报告）
pytest tests/ --browser chromium --headless --alluredir=./report

# 指定浏览器
pytest tests/ --browser chromium
pytest tests/ --browser firefox --browser webkit

# 运行指定模块
pytest tests/auth/ -v
pytest tests/auth/test_login.py::test_login_with_valid_credentials -v
```

### 调试配置

| 能力 | 配置 | 使用场景 |
|------|------|---------|
| Trace Viewer | `trace="retain-on-failure"` | 失败时查看执行轨迹 |
| 截图 | `screenshot="only-on-failure"` | 失败自动全页截图 |
| 视频录制 | `video="retain-on-failure"` | 失败保留执行视频 |
| 慢动作 | `slow_mo=500` | 本地调试观察细节 |

### 调试流程

1. 查看 reports/ 中的 Allure 报告
2. 检查 traces/ 中的 `.zip`，使用 `playwright show-trace trace.zip`
3. 查看 screenshots/ 中的失败截图
4. 本地复现：`pytest --headed --slow-mo=500`
