# 失败分类参考（Failure Classification Reference）

## 6 种分类的总览

`classify_failure.classify()` 依据错误消息、traceback、page-source、console-log 把失败归入以下 6 类之一。分类优先级：**ENV > BUG > LOCATOR / TIMEOUT > DATA > SCRIPT**。

| 分类 | 含义 | 典型信号 | 是否 MVP 修复目标 |
|------|------|---------|------------------|
| `ENV_ERROR` | 环境问题（浏览器、网络、依赖） | "browser not found"、ECONNREFUSED、ImportError、playwright install | ❌ 仅诊断 |
| `LOCATOR_ERROR` | 定位失败（元素不在 DOM） | "Locator not found"、`get_by_*`、AssertionError + visible | ✅ MVP |
| `TIMEOUT_ERROR` | 等待超时（元素在但未满足条件） | "Timeout Nms exceeded"、wait_for | ✅ MVP |
| `DATA_ERROR` | 测试数据问题 | "key error"、jsonschema、unique constraint | ❌ 仅诊断 |
| `SCRIPT_ERROR` | 脚本逻辑错误 | AssertionError（非 visible）、AttributeError、TypeError | ❌ 仅诊断 |
| `BUG` | 产品缺陷 | 5xx 响应、pageerror、console.error | ❌ 仅诊断 |

## 各分类的判定细则

### ENV_ERROR

**信号源：** traceback + message

匹配关键字（不区分大小写）：

- `browser` + (`not found` | `launch` | `executable doesn't exist`)
- `net::ERR_CONNECTION_REFUSED` | `ECONNREFUSED` | `Connection refused`
- `playwright install` | `browser was not found`
- `ImportError` | `ModuleNotFoundError`（含 `playwright`、`pytest_playwright`）
- `ENOTDIR` | `EACCES`（文件系统级）

**示例：**

```
playwright._impl._errors.Error: BrowserType.launch: Executable doesn't exist at ...
```

→ 归类为 `ENV_ERROR`，confidence=0.95

### LOCATOR_ERROR

**信号源：** message + page_source

匹配关键字：

- "Locator resolution failed" / "selector resolved to no elements"
- Playwright `get_by_*` 函数名出现在错误消息中
- `page.locator("...")` + "not found"
- "element handle is null"

**DOM 存在性校验：** 当 page_source 可用时，从 locator_hint 中提取关键文本（如 placeholder 值），在 DOM 中搜索。若存在则降级为 `TIMEOUT_ERROR`（元素在但等待策略有问题）。

**示例：**

```
playwright._impl._errors.Error: Error: locator.fill: Test failed: get_by_placeholder("账号") | selector resolved to no elements
```

→ 归类为 `LOCATOR_ERROR`，confidence=0.85

### TIMEOUT_ERROR

**信号源：** message + page_source

匹配关键字：

- "Timeout Nms exceeded"（N 为具体毫秒数）
- "TimeoutError" + `wait_for` | `expect` | `fill` | `click`
- 10000ms / 30000ms / 60000ms 常见值

**与 LOCATOR_ERROR 的区别：** TIMEOUT_ERROR 表示元素**已在 DOM**，但等待状态（visible / enabled / stable）未达成。当 page_source 显示元素存在时，优先归 TIMEOUT；否则归 LOCATOR。

### DATA_ERROR

**信号源：** traceback + message + console_log（含 Network）

匹配关键字：

- `KeyError` | `IndexError` | `jsonschema.ValidationError`
- `IntegrityError` | `UniqueViolation` | `Conflict`
- `status_code=4**` | `HTTP 409`
- "test data" / "fixture not found"

### SCRIPT_ERROR

**信号源：** traceback

默认 fallback：所有未匹配上述分类的 `AssertionError` / `AttributeError` / `TypeError` / `ValueError` / `NameError`。

排除规则：若 message 中含 `TimeoutError` 或 `Locator` 则不归此类。

### BUG

**信号源：** console_log + message + traceback

匹配关键字（任一触发）：

- console_log 段 `## Page Errors` 非空
- console_log 段 `## Console Errors` 含 `uncaught`、`ReferenceError`
- Network 段含 `status=5\d\d`（500、502、503）
- message 含 `Server Error` | `Internal Server Error`

## 分类置信度（confidence）

| 情况 | confidence |
|------|-----------|
| 强关键字命中（如 "Browser was not found"）| 0.95 |
| 弱关键字命中（如 "Timeout"） | 0.85 |
| fallback（默认 SCRIPT_ERROR） | 0.50 |
| 多信号交叉验证 | +0.05（封顶 0.99） |

置信度低于 0.5 的分类在报告中标记"低置信度"，建议人工复查。

## 多信号冲突的处理

当一个失败同时命中多个分类（如 `Locator.click: Timeout 10000ms exceeded` 同时含 LOCATOR 和 TIMEOUT 关键字），按以下规则：

1. **优先 DOM 存在性：** 若 page_source 显示元素存在 → TIMEOUT；不存在 → LOCATOR
2. **无 page_source 时：** 按 traceback 顶端判定（wait_for → TIMEOUT；fill/click without timeout → LOCATOR）

## 与根因定位的关系

只有 `LOCATOR_ERROR` 和 `TIMEOUT_ERROR` 会进入 `locate_root_cause.locate()` 流程。其他分类在报告中直接给出"建议人工介入"，不尝试 AST 修复。
