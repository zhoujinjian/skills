# 元素定位策略优先级参考

UI 自动化测试中，定位器的稳定性直接影响测试脚本的维护成本。
以下优先级规则适用于 `ui-page-parser` 解析和 `ui-testscript-generator` 生成脚本时的定位器选择。

---

## 定位策略优先级（由高到低）

| 优先级 | 策略 | 示例 | 稳定性 | 说明 |
|--------|------|------|--------|------|
| P1 | `data-testid` | `[data-testid='login-btn']` | ★★★★★ | 专为测试设计，不受 UI 重构影响，**首选** |
| P2 | `data-test-id` / `data-qa` | `[data-test-id='submit']` | ★★★★★ | 同 data-testid 变体 |
| P3 | `aria-label` | `[aria-label='用户名']` | ★★★★☆ | 语义化，兼顾无障碍，稳定性高 |
| P4 | `id` | `#username` | ★★★★☆ | 全局唯一，稳定性高，但动态 ID 除外 |
| P5 | `name` | `[name='username']` | ★★★☆☆ | 表单元素有效，非表单元素慎用 |
| P6 | `role + text` | `role=button[name='登录']` | ★★★☆☆ | 语义化组合，适合按钮 |
| P7 | CSS Selector | `#login-form .submit-btn` | ★★☆☆☆ | 受样式重构影响，尽量使用结构性选择器 |
| P8 | XPath | `//form[@id='x']//input` | ★★☆☆☆ | 最后兜底，可读性差，DOM 结构变化即失效 |

---

## Playwright 定位器写法参考

### data-testid（推荐）
```python
page.get_by_test_id("login-username")
page.locator("[data-testid='login-username']")
```

### aria-label / role
```python
page.get_by_label("用户名")
page.get_by_role("button", name="登录")
page.get_by_role("textbox", name="密码")
page.get_by_role("link", name="忘记密码")
```

### 文本内容
```python
page.get_by_text("登录")           # 精确文本
page.get_by_text("登录", exact=True)
page.get_by_placeholder("请输入用户名")
```

### id / name
```python
page.locator("#username")
page.locator("[name='username']")
```

### CSS Selector
```python
page.locator(".login-form input[type='text']")
page.locator("#login-form .error-message")
```

### XPath（兜底）
```python
page.locator("//form[@id='login-form']//input[@name='username']")
page.locator("xpath=//button[text()='登录']")
```

---

## 动态元素处理策略

### 动态 ID（如 `id="el_123456"`）
- **识别特征**：ID 包含数字序列或随机字符串
- **处理方式**：跳过 id 策略，优先使用 `data-testid` 或 `aria-label`
- **降级方案**：使用父级容器 + 相对选择器

### 动态列表/表格行
```python
# 按行索引（不稳定）
page.locator("table tbody tr").nth(0)

# 按行内容（推荐）
page.locator("table tbody tr").filter(has_text="张三")
page.get_by_role("row", name="张三")
```

### 弹窗/Modal 内元素
```python
# 先定位弹窗容器，再相对定位
modal = page.locator("[data-testid='confirm-modal']")
modal.get_by_role("button", name="确认")
```

### iframe 内元素
```python
frame = page.frame_locator("#captcha-iframe")
frame.locator("[data-testid='captcha-input']")
```

---

## 等待策略参考

| 等待类型 | Playwright 写法 | 适用场景 |
|----------|----------------|----------|
| 元素可见 | `expect(locator).to_be_visible()` | 动态渲染元素 |
| 元素可交互 | `expect(locator).to_be_enabled()` | 按钮等待激活 |
| URL 变更 | `expect(page).to_have_url(pattern)` | 页面跳转 |
| 文本出现 | `expect(locator).to_have_text("...")` | Toast/消息 |
| 网络响应 | `page.wait_for_response("/api/xxx")` | AJAX 完成 |
| 加载完成 | `page.wait_for_load_state("networkidle")` | SPA 初始化 |

---

## pages.yaml 中的定位器字段填写规范

```yaml
locator:
  strategy: "data-testid"          # 使用的定位策略名称
  value: "[data-testid='login-btn']"   # CSS/XPath/role 表达式（可直接用于 page.locator()）
  playwright_method: "get_by_test_id"  # 推荐的 Playwright API（可选）
  playwright_args: ["login-btn"]       # 对应参数（可选）
  fallback:
    - strategy: "aria-label"
      value: "[aria-label='登录']"
    - strategy: "xpath"
      value: "//button[text()='登录']"
```

---

## 推断模式下的定位器生成规则

当无法访问真实 DOM 时（`inference_mode: true`），按以下规则生成推断定位器：

1. **优先使用业务语义命名**：如"用户名输入框" → 推断 `[data-testid='username']` 或 `[name='username']`
2. **参考行业通用模式**：登录表单、搜索框等常见组件有标准命名惯例
3. **标注置信度**：在 `metadata.confidence` 中标记 `medium` 或 `low`
4. **提供多个备选**：推断时提供 2-3 个 fallback 定位器
5. **添加校准提示**：在 `metadata.inference_note` 中明确提示需人工校准
