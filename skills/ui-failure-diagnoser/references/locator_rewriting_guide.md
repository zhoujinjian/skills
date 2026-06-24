# 定位器重写指南（Locator Rewriting Guide）

## Playwright 定位器层级

按可维护性从高到低：

| 层级 | API | 抗 DOM 变化能力 | 推荐度 |
|------|-----|----------------|-------|
| 1 | `get_by_role(role, name=...)` | 极强（语义稳定） | ⭐⭐⭐⭐⭐ |
| 2 | `get_by_label(text)` / `get_by_placeholder(text)` | 强（用户可见文本） | ⭐⭐⭐⭐ |
| 3 | `get_by_test_id(id)` | 极强（需开发配合） | ⭐⭐⭐⭐⭐ |
| 4 | `get_by_text(text)` | 中（文本易变） | ⭐⭐⭐ |
| 5 | `page.locator("css")` | 弱（CSS 类易重构） | ⭐⭐ |
| 6 | `page.locator("xpath")` | 极弱（维护噩梦） | ⭐ |

## locator_drift 时的重写决策树

```
原 locator 失效
│
├─ 原本 get_by_role("button", name="登录")？
│   ├─ 找到新 button + "登录" 文本 → 保持 get_by_role
│   └─ 没找到 → 降级到 locator("button[type='submit']")
│
├─ 原本 get_by_placeholder("账号")？
│   ├─ 找到新 placeholder="用户名" → 改 get_by_placeholder("用户名")
│   └─ 找到 aria-label="账号" → 改 get_by_label("账号")
│
├─ 原本 page.locator(".login-btn")？
│   ├─ 类还在但改了名 → 替换 CSS 类
│   └─ 改用 button[type='submit'] + 文本兜底
│
└— 原本 xpath？→ 强烈建议重写为 get_by_role / CSS
```

## candidates 字段的利用

`locate_root_cause.locate()` 返回的 `evidence.candidates` 是从 page-source 提取的相似元素列表：

```json
{
  "original_locator": "get_by_placeholder(\"账号\")",
  "candidates": [
    {"kind": "placeholder", "value": "用户名"},
    {"kind": "placeholder", "value": "密码"},
    {"kind": "aria_label", "value": "账号"},
    {"kind": "button_text", "value": "登录"}
  ]
}
```

**Claude 推断流程：**

1. 阅读原 locator_hint（确定意图：填什么、点什么）
2. 在 candidates 中找语义最接近的元素
3. 生成新 locator 字符串
4. 用 Edit 工具替换 page 对象中的原 locator
5. 验证（`--verify`）

## 重写示例

### 示例 1：placeholder 漂移

**原 page 对象：**

```python
class LoginPage:
    def __init__(self, page):
        self._username = page.get_by_placeholder("账号")
```

**candidates：**

```
[{"kind": "placeholder", "value": "用户名"}, {"kind": "placeholder", "value": "密码"}]
```

**重写：**

```python
class LoginPage:
    def __init__(self, page):
        self._username = page.get_by_placeholder("用户名")
```

### 示例 2：button 重构为 a 标签

**原 page 对象：**

```python
self._login_btn = page.get_by_role("button", name="登录")
```

**candidates：**

```
[{"kind": "button_text", "value": ""}, {"kind": "text_node", "value": "登录"}]
```

**推断：** 原 button 已不存在，但"登录"文本还在。降级为 `get_by_text`：

```python
self._login_btn = page.get_by_text("登录", exact=True)
```

### 示例 3：CSS 类重命名

**原 page 对象：**

```python
self._search_box = page.locator(".search-input-v1")
```

**candidates：**

```
[{"kind": "class", "value": "search-input-v2"}, {"kind": "class", "value": "search-input-v2 active"}]
```

**重写：**

```python
self._search_box = page.locator(".search-input-v2")
```

## iframe 内元素的定位

当 `missing_iframe_switch` 触发时，`apply_iframe_switch_fix()` 自动包 `frame_locator`：

```python
# 原代码
self._captcha = page.locator("input[name='captcha']")

# 自动重写后
self._captcha = page.frame_locator("iframe[src='/captcha']").locator("input[name='captcha']")
```

**iframe_css 的推断规则：**

1. 从 `iframe_contents` 字典遍历每个 iframe 的 HTML
2. 若目标元素的核心文本（placeholder / label）出现在某个 iframe 内 → 选中该 iframe
3. 生成 CSS：`iframe[src='<url>']` 或 `iframe[src$='<path_tail>']`

## 重写后的验证

**强制要求：** 所有 `claude_semantic` 重写**必须**配合 `--verify`：

```bash
python3 diagnose.py ... --verify --base-url http://localhost:3000
```

**verify 失败时的行为：**

1. 自动 `rollback()` 恢复 `.bak`
2. 报告中标记 `rolled_back: true`
3. 建议用户人工介入

## 常见误判与处理

| 误判 | 现象 | 处理 |
|------|------|------|
| 候选元素过多 | candidates > 20 | 报告中提示"候选过多，建议人工确认" |
| 候选为空 | page-source 缺失 | 跳过 claude_semantic，标记为 `SCRIPT_ERROR` |
| 多个候选语义相近 | "用户名" vs "账号名" | Claude 依据原 locator_hint 上下文推断 |

## 与 ui-testscript-enhancer 的协作

当 `locator_drift` 频繁出现（同一元素多次失效），应考虑：

1. 调用 `ui-testscript-enhancer` 增强 page 对象（加 wait 策略、fallback locator）
2. 与开发团队沟通添加 `data-testid`（彻底解决漂移问题）

本技能不做增强，只做一次性修复。系统性增强是 `ui-testscript-enhancer` 的职责。
