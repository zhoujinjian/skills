### Task 12: references/failure_report_schema.md

**Files:**
- Create: `references/failure_report_schema.md`

- [ ] **Step 1: 写文档**

文件 `references/failure_report_schema.md`：

````markdown
# failure-context sidecar JSON Schema

每个失败用例生成一份 sidecar JSON，路径：`<artifact-root>/failure-context/<safe_nodeid>.json`

## 字段说明

| 字段 | 类型 | 必填 | 来源 | 说明 |
|------|------|------|------|------|
| `nodeid` | string | ✅ | pytest | 失败用例完整 nodeid（含参数化方括号） |
| `slug_hint` | string | ✅ | conftest `_sanitize_nodeid_to_slug` | nodeid 转 pytest-playwright 目录名格式，供 glob 匹配 |
| `phase` | string | ✅ | 环境变量 `PYTEST_RUN_PHASE` | `main` / `pre-run` |
| `duration` | float | ✅ | pytest `report.duration` | 用例耗时秒 |
| `browser` | string | ✅ | `page.context.browser.browser_type.name` | chromium / firefox / webkit |
| `url` | string | ✅ | `page.url` | 失败时页面 URL |
| `title` | string | ✅ | `page.title()` | 失败时页面标题（可能为空） |
| `failure_type` | string | ✅ | `assertion.message` 解析 | Exception 类名（如 AssertionError） |
| `rule` | string | ✅ | docstring 首行（含参数化占位替换） | 判定规则 |
| `rule_source` | string | ✅ | docstring 提取过程 | `docstring` / `fallback_funcname` / `docstring_unmatched_param` / `no_test_func` |
| `assertion` | object | ✅ | 见下 | 断言解析 |
| `expect_failure` | object | ✅ | 见下 | playwright 错误解析 |
| `artifacts` | object | ✅ | 见下 | 已采集 artifact 路径 |
| `pytest_raw_dir` | string | ✅ | execute_tests 透传 | pytest-playwright `--output` 目录 |
| `dumped_at` | string | ✅ | `datetime.now().isoformat()` | 写入时间 |

### `assertion` 子字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `statement` | string | assert 语句原文（带 message 字面值） |
| `file` | string | `文件:行号` |
| `introspection` | string | pytest 原生 introspection（含局部变量值） |
| `message` | string | 错误消息（ExceptionClass: msg） |

### `expect_failure` 子字段

| 字段 | 类型 | playwright expect 失败 | 原生 assert 失败 |
|------|------|------------------------|------------------|
| `locator` | string | 由正则提取 | 空 |
| `expected` | string | 由正则提取 | 空 |
| `received` | string | 由正则提取 | 空 |
| `action` | string | 由正则提取（如 `to_be_visible`） | 空 |
| `hint` | string | 关键词匹配得出 | 关键词匹配得出 |
| `raw` | string | 空 | 整段错误消息原文 |

判断逻辑：4 个结构化字段至少命中 1 个 → playwright expect 失败；全未命中 → 原生 assert 失败。

### `artifacts` 子字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `screenshots` | string[2] | 视口截图 + 全页截图绝对路径 |
| `page_source` | string | DOM 快照 HTML 路径 |
| `console_log` | string | console 日志合并文件路径 |

注：`video.webm` / `trace.zip` 不在此字段内，由 `generate_failure_analysis.py` 用 `slug_hint` + `pytest_raw_dir` 在渲染时 glob 补全。

## 示例

```json
{
  "nodeid": "tests/product/test_search.py::TestSearchPositive::test_search_valid_keyword_shows_results[chromium-小米]",
  "slug_hint": "tests-product-test-search-py-testsearchpositive-test-search-valid-keyword-shows-results-chromium-u5c0f-u7c73",
  "phase": "main",
  "duration": 1.56,
  "browser": "chromium",
  "url": "http://localhost:3000/search?q=小米",
  "title": "搜索结果",
  "failure_type": "AssertionError",
  "rule": "搜索「小米」应返回至少 1 件商品",
  "rule_source": "docstring",
  "assertion": {
    "statement": "assert count > 0",
    "file": "tests/product/test_search.py:55",
    "introspection": "assert 0 > 0\ncount = 0",
    "message": "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0"
  },
  "expect_failure": {
    "locator": "",
    "expected": "",
    "received": "",
    "action": "",
    "hint": "定位器与实际 DOM class 不匹配（推断，仅作参考）",
    "raw": "..."
  },
  "artifacts": {
    "screenshots": [".../viewport.png", ".../fullpage.png"],
    "page_source": ".../...html",
    "console_log": ".../...log"
  },
  "pytest_raw_dir": "/abs/path/test-results/artifacts/pytest-raw",
  "dumped_at": "2026-06-21T14:32:00"
}
```
````

- [ ] **Step 2: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git add references/failure_report_schema.md
git commit -m "docs(failure-analysis): sidecar JSON schema reference"
```

---

