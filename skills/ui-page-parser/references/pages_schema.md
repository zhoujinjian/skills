# pages.yaml 标准 Schema 参考

本文件定义 `ui-page-parser` 输出的 `pages.yaml/json` 结构规范，
是后续所有 UI 自动化 Skill（ui-testcase-generator、ui-testscript-generator 等）的标准输入格式。

---

## 顶层结构

```yaml
meta:
  generated_at: "2024-01-01T00:00:00Z"   # 生成时间（ISO 8601）
  generator: "ui-page-parser"
  dom_source: "http://localhost:3000/login"   # DOM 来源（URL / 文件路径 / "none"）
  page_count: 3
  inference_mode: false   # true 表示使用 LLM 推断模式（无真实 DOM）

pages:
  - <PageDefinition>
  - <PageDefinition>
```

---

## PageDefinition

```yaml
page_name: "登录页"                    # 必填：页面业务名称（中文友好）
url: "/login"                          # 必填：页面路径（相对或绝对）
module: "用户认证"                      # 所属业务模块
page_type: "form"                      # 页面类型：form | list | detail | modal | dashboard | wizard
description: "用户输入用户名密码登录系统"  # 页面业务描述

# 页面状态机
states:
  - name: "初始态"
    description: "页面首次加载，表单为空"
  - name: "填写中"
    description: "用户正在输入凭证"
  - name: "提交中"
    description: "点击登录按钮，等待响应"
  - name: "登录成功"
    description: "跳转到首页"
  - name: "登录失败"
    description: "显示错误提示，表单可重新输入"

# 页面元素列表
elements:
  - <ElementDefinition>

# 交互链路
flows:
  - <FlowDefinition>

# 隐性规则
implicit_rules:
  - type: "async_load"
    description: "提交后需等待接口响应，最长 10 秒"
  - type: "permission"
    description: "未登录用户访问受保护页面会重定向到此页"
  - type: "iframe"
    description: "页面内嵌 captcha iframe"

# 来源信息
source:
  type: "url"           # url | dom_file | source_code | natural_language
  value: "http://localhost:3000/login"
  inference_mode: false  # false = 真实 DOM；true = LLM 推断
  confidence: "high"    # high | medium | low
```

---

## ElementDefinition

```yaml
element_name: "用户名输入框"       # 必填：业务语义名称
element_type: "input"              # 必填：input | button | select | textarea | checkbox | radio
                                   #        link | modal | table | tab | toast | form
                                   #        dropdown | datepicker | upload | icon | text
locator:                           # 必填：定位器
  strategy: "data-testid"          # 定位策略（优先级见 locator_strategy.md）
  value: "[data-testid='login-username']"   # 定位表达式
  fallback:                        # 备用定位器（可选，建议提供）
    - strategy: "id"
      value: "#username"
    - strategy: "xpath"
      value: "//input[@name='username']"

interaction:                       # 交互方式
  action: "fill"                   # fill | click | select | check | hover | upload | clear | press
  value: "${username}"             # 填写的值（支持变量占位符）

wait_condition:                    # 等待条件（可选）
  type: "visible"                  # visible | enabled | hidden | text_contains | url_change | response
  value: ""

validations:                       # 关联校验（可选）
  - type: "error_message"
    trigger: "empty_submit"
    expected: "用户名不能为空"
    locator: "[data-testid='username-error']"
  - type: "max_length"
    expected: 50

# 元素约束（可选）
constraints:
  required: true
  max_length: 50
  pattern: "^[a-zA-Z0-9_@.]+$"
  disabled_states: ["提交中"]

# 元数据
metadata:
  visible: true
  is_interactive: true
  dom_xpath: "//form[@id='login-form']//input[@name='username']"
  dom_css: "#login-form input[name='username']"
```

---

## FlowDefinition

```yaml
flow_name: "正常登录流程"
flow_type: "happy_path"            # happy_path | error_path | edge_case
steps:
  - step: 1
    action: "fill"
    element: "用户名输入框"
    value: "${valid_username}"
  - step: 2
    action: "fill"
    element: "密码输入框"
    value: "${valid_password}"
  - step: 3
    action: "click"
    element: "登录按钮"
    wait_after: "url_change"       # 步骤后等待条件
  - step: 4
    action: "assert"
    target: "url"
    expected: "/dashboard"
    description: "验证跳转到首页"

# 流程级断言
assertions:
  - type: "url"
    expected: "/dashboard"
  - type: "element_visible"
    locator: "[data-testid='welcome-message']"
  - type: "api_response"
    endpoint: "/api/login"
    status_code: 200
```

---

## 元素类型参考

| element_type | 说明 | 典型 action |
|---|---|---|
| `input` | 文本/密码/数字输入框 | fill, clear, press |
| `button` | 提交/操作按钮 | click |
| `select` | 下拉选择框 | select |
| `checkbox` | 复选框 | check, uncheck |
| `radio` | 单选按钮 | click |
| `textarea` | 多行文本 | fill |
| `link` | 超链接 | click |
| `modal` | 弹窗/对话框 | - (容器) |
| `table` | 数据表格 | - (容器) |
| `tab` | 标签页切换 | click |
| `toast` | 轻提示/通知 | assert (仅校验) |
| `form` | 表单容器 | - (容器) |
| `dropdown` | 级联/下拉菜单 | click, select |
| `datepicker` | 日期选择器 | fill, click |
| `upload` | 文件上传 | upload |
| `icon` | 图标按钮（无文字） | click |
| `text` | 纯展示文本 | assert (仅校验) |

---

## 推断模式标记规范

当 `inference_mode: true` 时，以下字段为 LLM 推断值，需人工校准：

```yaml
metadata:
  inference_note: "元素定位器为推断值，建议通过真实页面验证"
  confidence: "medium"   # high | medium | low
```

推断置信度说明：
- `high`：有明确的业务上下文支撑（如用例中明确提到元素名）
- `medium`：基于页面类型和业务语义推断
- `low`：无充足上下文，高度依赖常见模式推断
