---
name: ui-testscript-generator
description: "基于 pages.yaml 页面定义和业务测试用例，生成 Playwright + POM + Pytest 的 UI 自动化测试脚本。当用户需要以下场景时触发：生成测试脚本、创建 POM 页面对象、编写 UI 自动化测试、搭建测试项目骨架、将测试用例转化为 Playwright 代码。也适用于用户提到：测试脚本生成、POM 生成、UI 自动化、Playwright 测试、pytest 测试生成、元素定位器、测试数据工厂，或用户提供了 pages.yaml 文件和业务测试用例文档（Excel/Word/TXT）希望转化为可执行测试代码。即使用户没有明确说"生成测试脚本"，只要提供了业务测试用例并希望得到自动化测试代码，就应使用此技能。"
---

# ui-testscript-generator — UI 测试脚本生成技能

## 技能定位

将 `pages.yaml`（页面对象定义）与业务测试用例（自然语言/Excel）转化为可执行的 Playwright + POM + Pytest 自动化测试代码。

**核心原则：以业务测试用例为唯一生成范围，pages.yaml 仅作为元素定位的查询数据库。**

这意味着：
- 测试用例涉及哪些页面和操作，就只为这些内容生成代码
- pages.yaml 中的其余页面和元素，不论有多少，一律不生成任何代码
- 生成范围由测试用例决定，不由 pages.yaml 决定

---

## 输入识别

接收任务时，首先确认以下输入：

| 输入 | 必需 | 说明 |
|------|------|------|
| pages.yaml | 是 | Skill 1（ui-page-parser）输出的页面对象定义文件，作为元素定位查询源 |
| 业务测试用例 | 是 | Excel/Word/TXT 格式的自然语言测试用例，决定生成范围 |
| 测试数据规则 | 否 | 自定义数据构造规则（基于 faker），用于 DataFactory |

### 输入文件定位

如果用户没有明确指定文件路径，按以下顺序查找：
1. 当前目录及子目录下的 `pages.yaml` 或 `pages.json`
2. 用户直接提供的文件内容
3. 如果找不到 pages.yaml，提示用户先运行 ui-page-parser 技能

---

## 工作流程

### Phase 1：解析输入，建立生成范围

#### Step 1.1：解析测试用例，提取业务范围

读取业务测试用例文件，提取以下信息：

1. **涉及的页面名称**：如"登录页"、"注册页"、"商品列表页"
2. **每个页面的操作步骤**：如"输入用户名"、"点击登录按钮"
3. **操作涉及的数据**：如用户名、密码、商品名称
4. **预期的断言结果**：如"跳转到首页"、"显示错误提示"
5. **页面间跳转关系**：如"登录成功后跳转到首页"

将提取结果整理为**生成范围清单**：

```
生成范围清单:
  页面:
    - 登录页: 输入用户名、输入密码、点击登录、错误提示断言
    - 首页: 验证页面加载、搜索商品
  页面间跳转:
    - 登录页 → 首页（登录成功）
  测试数据需求:
    - 有效用户名/密码
    - 无效用户名/密码
    - 空值
```

#### Step 1.2：匹配 pages.yaml，获取元素定位

用生成范围清单中的页面名称和操作描述，到 `pages.yaml` 中查找对应的：

1. **页面定义**：匹配 `page_name` 或 `url`
2. **元素定位器**：匹配 `element_name` 或 `interaction.action`
3. **页面状态**：参考 `states` 定义
4. **交互流程**：参考 `flows` 定义

**匹配策略**（按优先级）：
- 精确匹配 `page_name`（如"登录页"）
- 模糊匹配操作描述中的关键词与 `element_name`（如"输入用户名" → "用户名输入框"）
- 匹配 `interaction.action` 与操作动词（如 fill → 输入，click → 点击）
- 参考 `text_structure` 和 `interaction_hint` 进行语义推断

**未匹配处理**：
- 如果测试用例中的操作在 pages.yaml 中找不到对应元素，标记为"缺失元素"
- 对于缺失元素，基于操作描述推断合理的定位器，并标注 `inference_note`
- 在生成结果的注释中明确标注哪些是推断的定位器

#### Step 1.3：向用户确认生成范围

输出**生成计划摘要**给用户确认：

```
📋 生成计划:
  POM 页面类:
    ✅ LoginPage（来自 pages.yaml，confidence: high）
    ✅ HomePage（来自 pages.yaml，confidence: high）
  测试脚本:
    ✅ test_login.py（3 个测试用例）
    ✅ test_home_search.py（2 个测试用例）
  测试数据:
    ✅ 登录相关数据（有效/无效用户）
  跳过（未在测试用例中出现）:
    ⏭ 注册页、商品列表页、购物车页...
```

---

### Phase 2：初始化项目结构

确认生成范围后，创建测试项目目录。

读取 `assets/project_structure.txt` 获取完整目录结构，使用以下方式初始化：

1. 如果当前目录是已有项目，仅补充缺失的目录和文件
2. 如果是新项目，创建完整目录结构

**必须创建的基础文件**（从 `assets/` 目录复制模板）：
- `pages/base_page.py` — BasePage 基类
- `tests/conftest.py` — pytest fixtures
- `pytest.ini` — pytest 配置
- `requirements.txt` — 依赖清单

可使用脚本快速生成骨架：

```bash
SCRIPT_DIR=~/.claude/skills/ui-testscript-generator/scripts
python3 "${SCRIPT_DIR}/generate_project.py" --output ./ui-test-automation
```

---

### Phase 3：生成 POM 页面对象

为生成范围内的每个页面创建 POM 类。

#### POM 生成规则

1. **一对一映射**：一个页面生成一个 POM 类文件
2. **文件路径**：`pages/<module>/<page_name>.py`，module 按业务模块划分
3. **类名**：大驼峰，如 `LoginPage`、`ProductDetailPage`
4. **继承 BasePage**：所有 POM 类继承 `pages.base_page.BasePage`
5. **定位器私有化**：元素定位器定义为 `self._element_name` 私有属性
6. **方法封装**：每个操作封装为一个方法，方法名见名知意
7. **链式调用**：方法返回 `self`（同页操作）或目标 Page 对象（页面跳转）
8. **方法不写断言**：POM 方法只封装动作，不包含业务断言逻辑

#### 定位器选择

从 pages.yaml 中的 `locator` 字段提取定位器，按以下优先级选择：

| 优先级 | Playwright API | 适用场景 |
|--------|---------------|---------|
| 1 | `page.get_by_role()` | 有 role 或 aria 信息时 |
| 2 | `page.get_by_test_id()` | 有 data-testid 时 |
| 3 | `page.get_by_label()` | 表单元素关联 label 时 |
| 4 | `page.get_by_placeholder()` | 输入框有 placeholder 时 |
| 5 | `page.get_by_text()` | 按钮等有明确文本时 |
| 6 | `page.locator(css)` | 上述都不适用时的兜底 |

**禁止使用**：动态 id（如 `el-id-xxxx`）、XPath、深层嵌套 CSS。

详细规则参考 `references/pom_templates.md`。

#### 生成示例

根据 pages.yaml 中的元素定义，生成 POM 类。每个元素生成：
- 私有定位器属性（`self._xxx`）
- 公开操作方法（`def fill_xxx()`、`def click_xxx()`）
- 导航方法（`def navigate()`）
- 页面跳转方法返回目标 Page 对象

模板和完整示例参考 `references/pom_templates.md`。

---

### Phase 4：生成测试脚本

为每条/每组业务测试用例生成 pytest 测试脚本。

#### 测试脚本生成规则

1. **文件命名**：`tests/<module>/test_<page_name>.py`
2. **方法命名**：`test_<verb>_<expected_result>`，如 `test_login_with_valid_credentials_shows_dashboard`
3. **用例独立性**：每个测试方法独立，不依赖其他测试的执行状态
4. **一个用例一个核心业务点**：必要时使用多个 expect 但保持同一主题
5. **结构**：前置操作 → 执行步骤 → 断言 → 清理（可选）
6. **不直接写定位器**：所有元素操作通过 POM 类方法调用
7. **断言使用 pytest + Playwright expect**：`assert actual == expected, "失败说明"`
8. **禁止 time.sleep**：统一使用 Playwright 自动等待

#### 用例到脚本的转换逻辑

读取测试用例中的每个步骤，转换为代码：

| 用例步骤 | 代码转换 |
|---------|---------|
| "打开登录页" | `login_page = LoginPage(page).navigate()` |
| "输入用户名 xxx" | `login_page.fill_username("xxx")` |
| "点击登录按钮" | `dashboard = login_page.click_login()` |
| "验证跳转到首页" | `expect(page).to_have_url("/")` |
| "验证显示错误提示" | `assert "用户名不能为空" in login_page.get_error_message()` |

详细模板参考 `references/test_script_templates.md`。

#### Fixtures 生成

根据测试用例需要，生成 fixtures：
- **已登录状态 fixture**：用于需要认证的测试（如 `auth_page`）
- **测试数据 fixture**：参数化的测试数据
- **浏览器配置 fixture**：视口、语言等

---

### Phase 5：生成测试数据

根据测试用例中的数据需求，生成测试数据文件和 DataFactory。

#### 静态测试数据

生成 `data/test_data.yaml` 或 `data/test_data.json`：

```yaml
login:
  valid_user:
    username: "test_user_001"
    password: "Test@1234"
  invalid_user:
    username: "wrong_user"
    password: "wrong_pass"
  empty_fields:
    username: ""
    password: ""
```

#### 动态数据工厂

如果用户提供了自定义数据规则，或测试用例需要随机数据，生成 `utils/data_factory.py`。

底层基于 faker 库，支持：
- 随机用户信息（姓名、邮箱、手机号）
- 随机地址
- 自定义规则的数据生成

详细规则参考 `references/data_factory_guide.md`。

---

### Phase 6：生成配置文件

根据 pages.yaml 中的 `base_url` 和框架规范，生成：

- `config/settings.py` — 全局配置
- `config/environments/dev.yaml` — 开发环境配置
- `pytest.ini` — pytest 配置
- `requirements.txt` — 依赖清单

---

## 输出规范

### 文件命名

```
ui-test-automation/
├── pages/<module>/
│   └── <page_name>_page.py          # POM 页面类
├── tests/<module>/
│   └── test_<page_name>.py           # 测试脚本
├── tests/fixtures/
│   └── <module>_fixture.py           # Fixtures
├── utils/
│   └── data_factory.py               # 数据工厂
└── data/
    └── test_data.yaml                # 测试数据
```

### 代码质量要求

- 所有生成的代码必须可直接执行，不能有语法错误
- 类型注解完整（Python 3.10+）
- import 路径正确，不遗漏依赖
- 定位器策略优先使用 Playwright 内置 API
- 每个测试方法有清晰的 docstring 说明测试意图

### 交付清单

生成完成后，输出交付清单：

```
📦 生成完成:
  POM 页面类: 3 个文件
  测试脚本: 3 个文件，8 个测试方法
  Fixtures: 2 个文件
  测试数据: 1 个文件
  配置文件: 3 个文件

🏃 运行测试:
  pytest tests/ --headed --slow-mo=200
  pytest tests/ --browser chromium --headless --alluredir=./report
```

---

## 参考文件索引

生成代码时，按需读取以下参考文件：

| 文件 | 用途 | 读取时机 |
|------|------|---------|
| `references/framework_standards.md` | 团队框架规范全文 | Phase 2 初始化项目时 |
| `references/pom_templates.md` | POM 类编写模板和完整示例 | Phase 3 生成 POM 时 |
| `references/test_script_templates.md` | 测试脚本模板和示例 | Phase 4 生成测试脚本时 |
| `references/data_factory_guide.md` | 数据工厂编写指南 | Phase 5 生成测试数据时 |
| `assets/base_page.py` | BasePage 基类模板 | 复制到项目 |
| `assets/conftest.py` | conftest 模板 | 复制到项目 |
| `assets/pytest.ini` | pytest 配置模板 | 复制到项目 |
| `assets/requirements.txt` | 依赖清单模板 | 复制到项目 |
| `assets/project_structure.txt` | 项目目录结构 | Phase 2 创建目录时 |
