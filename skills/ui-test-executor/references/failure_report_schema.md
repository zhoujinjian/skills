# Failure Analysis Report Schema

`failure_analysis.md` 是 `ui-test-executor` 在测试出现失败时自动生成的 Markdown 故障分析报告。每条失败用例一节，含判定规则、断言原文、预期 vs 实际、页面元素校验、失败截图路径、录屏/Trace 路径、其他诊断材料。

本文件是字段级权威参考。用户指南见 `failure_analysis_guide.md`。

---

## 1. 触发与位置

| 项目 | 值 |
|------|---|
| 触发条件 | pytest 退出后，JUnit XML 中 `failures + errors > 0`；且未传 `--no-failure-analysis`；且非 `--dry-run` / `--list-only` |
| 生成器 | `scripts/generate_failure_analysis.py` |
| 自动调起方 | `scripts/execute_tests.py::main` 末尾的 `_maybe_generate_failure_analysis()` |
| 输出路径 | `<output-dir>/failure_analysis.md`（通常为 `test-results/failure_analysis.md`） |
| 编码 | UTF-8（`ensure_ascii=False`） |

报告依赖两份输入：

| 输入 | 路径 | 缺失时的行为 |
|------|------|-------------|
| JUnit XML | `<output-dir>/report.xml` | 生成器退出码 2，不产出 MD |
| sidecar JSON | `<artifacts-dir>/failure-context/<safe_nodeid>.json` | 降级模式：仅渲染 JUnit XML 里的 nodeid + message + traceback |

---

## 2. 顶层结构

整份 MD 由三部分组成：

```
# 失败用例故障分析报告

**生成时间**: YYYY-MM-DD HH:MM:SS
**测试执行**: <execution-summary>
**失败统计**: N 个失败用例

> 本报告由 ... 自动生成 ...

---

## ❌ <rule 或函数名>
... 7 个子章节 ...

---

## ❌ <下一条失败>
...
```

### 顶部字段

| 字段 | 来源 | 示例 |
|------|------|------|
| `生成时间` | `datetime.now().strftime('%Y-%m-%d %H:%M:%S')` | `2026-06-21 14:32:00` |
| `测试执行` | execute_tests.py 传入的 `--execution-summary` | `P0 and run_smoke · chromium · headless` |
| `失败统计` | `len(failures)` | `3 个失败用例` |

`--execution-summary` 由 `execute_tests.py::_maybe_generate_failure_analysis` 自动组装，按顺序拼接：

1. marker 表达式（若指定了 `--priority` / `--tags` / `--marker-expr`）
2. 浏览器列表（`--browser` 用 `+` 连接）
3. headless / headed

未指定任何筛选条件时显示 `(未指定)`。

---

## 3. 单条失败用例章节

每条失败用例渲染一节，固定 7 个子章节，顺序不可变。

### 章节标题

```markdown
## ❌ <rule 首行 或 函数名>
```

- 有 sidecar 且 `rule` 非空 → 取 `rule.splitlines()[0]`
- 否则 → 取 `case.name`（JUnit XML 里的 test method name）

### 元信息行

紧跟标题的两行：

```markdown
**位置**: `<完整 nodeid>`
**阶段**: <phase> · **耗时**: <duration>s · **浏览器**: <browser> · **失败类型**: <failure_type>
```

| 字段 | 来源 | 备注 |
|------|------|------|
| `位置` | `case.nodeid`（JUnit XML `classname::name` 拼回） | 含参数化方括号 |
| `阶段` | `sidecar.phase`（`main` / `pre-run`） | 缺失默认 `main` |
| `耗时` | `sidecar.duration` 回退 `case.duration` | 秒，保留 2 位小数 |
| `浏览器` | `sidecar.browser` | 空时省略 |
| `失败类型` | `sidecar.failure_type` | Exception 类名，空时省略 |

---

### 3.1 判定规则

```markdown
### 判定规则

> <rule 文本>

> 📌 **来源**: <来源说明>
```

| `rule_source` 值 | 渲染为 |
|------------------|--------|
| `docstring` | `测试 docstring 首行` |
| `fallback_funcname` | `函数名 fallback（无 docstring）` |
| `docstring_unmatched_param` | `docstring（含未匹配的参数化占位符）` |
| `no_test_func` / 空 | `测试 docstring 首行`（实际 rule 为空，会显示「无 sidecar」提示） |

降级模式（sidecar 缺失）下整段替换为：

```markdown
> *(无 sidecar，rule 字段缺失，详见断言原文)*
```

---

### 3.2 断言原文

```markdown
### 断言原文

```python
# <file>
<statement>
```
```

| 字段 | 来源 |
|------|------|
| `file` | `sidecar.assertion.file`，格式 `路径:行号` |
| `statement` | `sidecar.assertion.statement`，带 message 字面值的 assert 语句 |

降级模式：`*(sidecar 缺失或解析失败)*`

---

### 3.3 预期 vs 实际（pytest 内省）

```markdown
### 预期 vs 实际（pytest 内省）

```
<introspection>
```
```

`introspection` = pytest 原生 `reprcrash.message`，通常含 `assert X > Y` 展开式 + 局部变量值。降级模式：`*(无内省信息)*`

---

### 3.4 页面元素校验

表格形式：

```markdown
### 页面元素校验

| 字段 | 值 |
|------|---|
| 失败 URL | `<url>` |
| 定位器 | `<locator 或 原生 assert 占位>` |
| 期望 | `<expected 或 占位>` |
| 实际 | `<received 或 占位>` |
| 推断原因 | <hint 或 「（无）」> |
```

**判断逻辑**：`_is_playwright_expect_failure(sidecar)` = locator/expected/received/action 四字段中至少 1 个非空 → playwright expect 失败；否则为原生 assert 失败。

| 失败类型 | 定位器/期望/实际 | 推断原因 |
|---------|----------------|---------|
| playwright expect | 从 `_PW_PATTERNS` 正则提取的结构化值 | `_infer_hint` 规则匹配结果 |
| 原生 assert | `*(原生 assert，...)*` 占位 | 关键词匹配的 hint（可能为空） |

原生 assert 失败时追加提示：

```markdown
> ⚠️ 本用例是**原生 assert** 失败（非 playwright expect）。
> 「定位器/期望/实际」仅在 playwright expect 失败时从错误消息结构化提取。
```

若 `expect_failure.raw` 非空且为原生 assert 失败，追加错误消息原文（前 500 字符）：

```markdown
**错误消息原文**：

```
<raw[:500]>
```
```

---

### 3.5 失败截图

```markdown
### 失败截图

| 类型 | 路径 |
|------|------|
| 视口截图 | `<path 或 *(未采集)*>` |
| 全页截图 | `<path 或 *(未采集)*>` |
| Playwright 原生失败截图 | `<test-failed-N.png>`（仅当存在时显示） |
```

| 来源 | 字段 |
|------|------|
| 视口 + 全页 | `sidecar.artifacts.screenshots`（2 元素数组：`[viewport, fullpage]`） |
| Playwright 原生 | `<pytest_raw_dir>/<slug>/test-failed-N.png`（由 `_resolve_video_trace` 用 glob 补全） |

---

### 3.6 失败录屏与 Trace

```markdown
### 失败录屏与 Trace

| 类型 | 路径 | 复现命令 |
|------|------|---------|
| 录屏 | `<path 或 提示>` | `open <path>` |
| Trace | `<path 或 提示>` | `python3 -m playwright show-trace <path>` |
```

路径解析由 `_resolve_video_trace(sidecar)` 完成，策略（按优先级）：

1. **精确匹配**：`<pytest_raw_dir>/<slug_hint>/` 存在 → 直接用
2. **glob fallback**：`pytest_raw_dir` 下唯一子目录 → 用该目录（容错 slug 转义差异）
3. **多候选**：`pytest_raw_dir` 下多个子目录 → 不选，渲染 `⚠️ 多个候选目录匹配，请人工确认`

录屏/Trace 未生成时的提示：

```
*(未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off)*
```

---

### 3.7 其他诊断材料

无序列表：

```markdown
### 其他诊断材料

- 页面源码: `<path>`
- Console 日志: `<path>`
- 失败时 URL: `<url>`
```

字段缺失时对应行省略。来源：

| 字段 | 来源 |
|------|------|
| 页面源码 | `sidecar.artifacts.page_source` |
| Console 日志 | `sidecar.artifacts.console_log` |
| 失败时 URL | `sidecar.url`（3.4 表格里的同字段） |

每节以 `---` 分隔。

---

## 4. Sidecar JSON Schema

路径：`<artifact-root>/failure-context/<safe_nodeid>.json`

文件名由 `_sanitize_filename(report.nodeid)` 生成（与 screenshots 命名一致）：

- 方括号 / 空白 / 路径分隔符 / 冒号 → `-`
- 其他非 `[A-Za-z0-9_.-]` 字符 → `-`（中文等非 ASCII 字符也会被替换为 `-`）
- 截断到 120 字符

### 顶层字段

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| `nodeid` | string | ✅ | pytest | 完整 nodeid（含参数化方括号） |
| `slug_hint` | string | ✅ | conftest `_sanitize_nodeid_to_slug` | nodeid 转 pytest-playwright 目录名格式，供 glob 匹配 |
| `phase` | string | ✅ | 环境变量 `PYTEST_RUN_PHASE` | `main` / `pre-run` |
| `duration` | float | ✅ | `report.duration` | 用例耗时秒 |
| `browser` | string | ✅ | `page.context.browser.browser_type.name` | chromium / firefox / webkit |
| `url` | string | ✅ | `page.url` | 失败时页面 URL |
| `title` | string | ✅ | `page.title()` | 失败时页面标题（可能为空） |
| `failure_type` | string | ✅ | `assertion.message` 解析 | Exception 类名（如 `AssertionError`） |
| `rule` | string | ✅ | docstring 首行（含参数化占位替换） | 判定规则 |
| `rule_source` | string | ✅ | docstring 提取过程 | 见 §3.1 |
| `assertion` | object | ✅ | 见下 | 断言解析 |
| `expect_failure` | object | ✅ | 见下 | playwright 错误解析 |
| `artifacts` | object | ✅ | 见下 | 已采集 artifact 路径 |
| `pytest_raw_dir` | string | ✅ | execute_tests 透传 | pytest-playwright `--output` 目录绝对路径 |
| `dumped_at` | string | ✅ | `datetime.now().isoformat()` | 写入时间 |

### `assertion` 子字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `statement` | string | assert 语句原文（带 message 字面值） |
| `file` | string | `文件:行号` |
| `introspection` | string | pytest 原生 introspection（`reprcrash.message`，含局部变量值） |
| `message` | string | 错误消息（`ExceptionClass: msg`） |

### `expect_failure` 子字段

| 字段 | 类型 | playwright expect 失败 | 原生 assert 失败 |
|------|------|------------------------|------------------|
| `locator` | string | 正则提取 | 空 |
| `expected` | string | 正则提取 | 空 |
| `received` | string | 正则提取 | 空 |
| `action` | string | 正则提取（如 `to_be_visible`） | 空 |
| `hint` | string | 关键词匹配得出 | 关键词匹配得出 |
| `raw` | string | 空 | 整段错误消息原文（前 500 字符） |

判断逻辑：4 个结构化字段至少命中 1 个 → playwright expect 失败；全未命中 → 原生 assert 失败。

### `artifacts` 子字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `screenshots` | string[2] | 视口截图 + 全页截图绝对路径 |
| `page_source` | string | DOM 快照 HTML 路径 |
| `console_log` | string | console 日志合并文件路径（5 段：Page Errors / Console ERROR\|WARN / Console 其他 / Network / Performance） |

注：`video.webm` / `trace.zip` / `test-failed-N.png` 不在 sidecar 里，由 `generate_failure_analysis.py::_resolve_video_trace` 用 `slug_hint` + `pytest_raw_dir` 在渲染时 glob 补全。这样 sidecar 不受 pytest-playwright 内部目录命名变更影响。

### 完整示例

```json
{
  "nodeid": "tests/product/test_search.py::TestSearchPositive::test_search_valid_keyword_shows_results[chromium-小米]",
  "slug_hint": "tests-product-test-search-py-testsearchpositive-test-search-valid-keyword-shows-results-chromium-u5c0f-u7c73",
  "phase": "main",
  "duration": 1.56,
  "browser": "chromium",
  "url": "http://localhost:3000/search?q=%E5%B0%8F%E7%B1%B3",
  "title": "搜索结果",
  "failure_type": "AssertionError",
  "rule": "搜索「小米」应返回至少 1 件商品",
  "rule_source": "docstring",
  "assertion": {
    "statement": "assert count > 0, f\"搜索 '小米' 应返回商品，但结果数为 {count}\"",
    "file": "tests/product/test_search.py:55",
    "introspection": "assert 0 > 0\nassert 0 > 0\n +  where 0 = len([...])",
    "message": "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0"
  },
  "expect_failure": {
    "locator": "",
    "expected": "",
    "received": "",
    "action": "",
    "hint": "结果数为 0（推断，仅作参考）",
    "raw": "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0\nassert 0 > 0"
  },
  "artifacts": {
    "screenshots": [
      "/abs/test-results/artifacts/screenshots/tests-product-test-search-py-...-viewport.png",
      "/abs/test-results/artifacts/screenshots/tests-product-test-search-py-...-fullpage.png"
    ],
    "page_source": "/abs/test-results/artifacts/page-source/tests-product-test-search-py-....html",
    "console_log": "/abs/test-results/artifacts/console-logs/tests-product-test-search-py-....log"
  },
  "pytest_raw_dir": "/abs/test-results/artifacts/pytest-raw",
  "dumped_at": "2026-06-21T14:32:00.123456"
}
```

---

## 5. 降级模式

sidecar JSON 缺失时，`_load_sidecar` 返回 `{}`，`render_failure_section` 退化为：

| 子章节 | 降级渲染 |
|--------|---------|
| 判定规则 | `*(无 sidecar，rule 字段缺失，详见断言原文)*` |
| 断言原文 | `*(sidecar 缺失或解析失败)*` |
| 预期 vs 实际 | `*(无内省信息)*` |
| 页面元素校验 | URL 回退 `case.message`；定位器/期望/实际为 `*(原生 assert)*` 占位 |
| 失败截图 | `*(未采集)*` |
| 失败录屏与 Trace | `*(未生成)*`（无 `pytest_raw_dir` 则 `_resolve_video_trace` 返回空） |
| 其他诊断材料 | 仅显示 `case.message` 里的 URL（如有） |

降级模式典型场景：

1. 项目 `tests/conftest.py` 未集成 `_dump_failure_context` hook（旧项目）
2. setup 阶段失败（`page` fixture 没建立 → 无法读 `page.url` / `page.title()`）
3. sidecar JSON 写入时抛异常（磁盘满等极端情况，conftest 会记录 `[WARN]` 但不阻塞）

---

## 6. 与其他 artifact 的交叉引用

| MD 里出现的路径 | 对应 SKILL.md 章节 |
|----------------|-------------------|
| `artifacts/screenshots/<nodeid>-{viewport,fullpage}.png` | Step 0.5 artifact 表第 1 行 |
| `artifacts/page-source/<nodeid>.html` | Step 0.5 artifact 表第 6 行 |
| `artifacts/console-logs/<nodeid>.log` | Step 0.5 artifact 表第 5 行 |
| `artifacts/pytest-raw/<slug>/video.webm` | Step 0.5 artifact 表第 2 行 |
| `artifacts/pytest-raw/<slug>/trace.zip` | Step 0.5 artifact 表第 3 行 |
| `artifacts/pytest-raw/<slug>/test-failed-N.png` | Step 0.5 artifact 表第 1 行（pytest-playwright 原生） |

artifact 系统的完整说明见 `references/artifact_collection.md`（如存在）与 SKILL.md Step 0.5。

---

## 7. 相关文档

- 用户指南：`references/failure_analysis_guide.md`
- 主流程：`SKILL.md` Step 6.5
- 生成器源码：`scripts/generate_failure_analysis.py`
- Sidecar 写入逻辑：`assets/conftest_template.py::_dump_failure_context`
- 自动调起逻辑：`scripts/execute_tests.py::_maybe_generate_failure_analysis`
