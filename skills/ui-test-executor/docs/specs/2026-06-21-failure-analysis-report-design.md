# 失败用例 Markdown 故障分析报告 — 设计文档

**Spec ID**: failure-analysis-report
**创建日期**: 2026-06-21
**所属 skill**: `ui-test-executor`
**状态**: 已通过 brainstorming，待 writing-plans
**关联能力**: 三能力中的第 1 项（其余两项为 Trace Viewer 快速打开、操作高亮，单独 spec）

---

## 1. 背景与目标

### 1.1 现状

`ui-test-executor` 当前生成的 `summary.md` 里只有"失败用例明细"段落，字段密度低：

- 失败摘要（message 首行）
- Traceback 末 20 行
- Artifacts 计数（仅展示"X 个"，不展示路径）

调试一个失败用例时，用户需要：

1. 看 summary.md 找到失败 nodeid
2. 切到 `test-results/artifacts/screenshots/` 找对应截图
3. 切到 `pytest-raw/<slug>/` 找 video/trace
4. 手动拼 `playwright show-trace <path>` 命令
5. 重新打开测试源码看断言上下文

这个流程冗长，且 summary.md 缺乏「这个用例本来应该验证什么」（判定规则）、「断言预期 vs 实际」（结构化对比）、「定位器/期望状态/实际状态」（playwright 错误结构化字段）这些对诊断最关键的信息。

### 1.2 目标

新增独立的 `failure_analysis.md`，仅在有失败用例时生成，每条失败用例一节，包含：

| 字段 | 来源 |
|------|------|
| 用例位置 (nodeid) + 阶段 + 耗时 + 浏览器 + 失败类型 | report.xml + sidecar JSON |
| **判定规则** | 测试 docstring 首行（弱约定，无 docstring 时 fallback 到函数名） |
| **断言原文**（带行号） | report.longrepr traceback |
| **预期 vs 实际**（pytest 内省展开） | report.longrepr.reprcrash.message |
| **页面元素校验**（locator/expected/received/action/hint） | 解析 playwright 错误消息 |
| 失败截图路径（视口 + 全页 + Playwright 原生） | sidecar JSON + glob |
| 失败录屏路径 | glob `pytest-raw/<slug>/video.webm` |
| Trace 路径 + `playwright show-trace` 复现命令 | glob `pytest-raw/<slug>/trace.zip` |
| 其他诊断材料（page-source / console-log / 失败时 URL） | sidecar JSON |

### 1.3 非目标（明确不做）

- **不做 AI 智能诊断**：「推断原因」是关键词匹配，不是 LLM。深度诊断由未来独立 skill 负责
- **不修改测试代码**：所有信息从 docstring/pytest/playwright 原生机制拿，零侵入
- **不替换 summary.md**：两份报告并存，summary.md = 概览，failure_analysis.md = 深度
- **不做模板主题化**：MD 渲染样式固定（YAGNI）

---

## 2. 用户故事

**作为** UI 自动化测试工程师，
**当我** 跑完一批用例看到有失败时，
**我希望** 打开 `failure_analysis.md` 就能看到每条失败用例的「判定规则 / 断言预期与实际 / 元素校验详情 / 截图录屏 Trace 路径」一应俱全，
**从而** 不用在多个目录之间跳来跳去，直接基于一份报告进入诊断。

**触发方式**：用户执行 `execute_tests.py` 后，若 report.xml 显示 ≥ 1 个失败，**自动生成** `failure_analysis.md`。无需任何额外参数。

---

## 3. 整体架构

### 3.1 目录结构

```
test-results/
├── report.xml                           ← 现有（JUnit）
├── report.json / summary.md             ← 现有（generate_report.py）
├── failure_analysis.md                  ← 新增（仅 ≥1 失败时生成）
└── artifacts/
    ├── screenshots/  page-source/  ...  ← 现有
    ├── failure-context/                 ← 新增目录
    │   └── <nodeid>.json                ←   每个失败用例一份 sidecar
    └── pytest-raw/<slug>/{trace.zip,video.webm}
```

### 3.2 数据流

```
pytest 执行
  └─ conftest.py::pytest_runtest_makereport (hookwrapper, 失败时)
       ├─ _collect_failure_artifacts (现有：截图/page-source/console-log)
       └─ _dump_failure_context (新增：写 failure-context/<nodeid>.json)
            ├─ nodeid / phase / duration / browser / url / title
            ├─ rule           ← inspect.getdoc(test_func) 提取约定 docstring
            ├─ assertion      ← report.longrepr 拿 assert 语句 + pytest 原生 introspection
            ├─ expect_failure ← 解析 playwright 错误消息
            └─ artifacts      ← 已采集的所有 artifact 路径（video/trace 除外）

执行结束
  └─ execute_tests.py 在 pytest 进程结束后
       └─ 若 test-results/report.xml 显示有失败
            └─ 自动调用 generate_failure_analysis.py（用户可 --no-failure-analysis 关闭）

generate_failure_analysis.py (新脚本)
  ├─ 读 report.xml 拿失败用例列表（权威来源）
  ├─ 对每个失败用例读 failure-context/<nodeid>.json
  ├─ glob pytest-raw/*/<slug>/{video.webm,trace.zip} 补全 video/trace 路径
  ├─ fallback：JSON 不存在时从 report.xml 退化渲染
  └─ 渲染 failure_analysis.md（每条失败一节）
```

### 3.3 文件清单

| 文件 | 动作 | 职责 |
|------|------|------|
| `assets/conftest_template.py` | 修改 | 加 `_dump_failure_context` + `_extract_rule_from_docstring` + `_parse_assertion_from_longrepr` + `_parse_playwright_error` |
| `scripts/generate_failure_analysis.py` | 新增 | 扫描 failure-context + 读 report.xml + glob video/trace + 渲染 MD |
| `scripts/execute_tests.py` | 修改 | 在 pytest 进程结束后，若 report.xml 有失败，自动调 `generate_failure_analysis.py`；新增 `--no-failure-analysis` 开关 |
| `SKILL.md` | 修改 | Step 6 后追加 Step 6.5 失败报告章节 |
| `references/failure_report_schema.md` | 新增 | JSON sidecar schema 文档 |
| `references/failure_analysis_guide.md` | 新增 | docstring 约定 + playwright 错误解析规则 |
| `evals/failure_analysis/` | 新增 | 单测：docstring 提取、playwright 错误解析、降级渲染 |

### 3.4 与现有 generate_report.py 的边界

- `generate_report.py`：只负责"概览统计 + 简要失败明细"，不做深度解析
- `generate_failure_analysis.py`：只负责"深度失败报告"
- 两者独立，互不依赖，互不读取对方的输出

---

## 4. 详细设计

### 4.1 Markdown 报告模板

#### 4.1.1 文件顶部总览

```markdown
# 失败用例故障分析报告

**生成时间**: 2026-06-21 14:32:00
**测试执行**: shop-lab-ui-test (P0 and run_smoke) · chromium · headless
**失败统计**: 1/8 用例失败 (12.5%) · 总耗时 27.5s

> 本报告由 `ui-test-executor` 自动生成。每条失败用例一节，含判定规则、
> 断言详情、元素校验、失败截图与录屏路径。Trace 复现命令见每节末尾。

---
```

#### 4.1.2 单条失败用例章节模板

````markdown
## ❌ TC-004 搜索「小米」应返回至少 1 件商品

**位置**: `tests/product/test_search.py::TestSearchPositive::test_search_valid_keyword_shows_results[chromium-小米]`
**阶段**: main · **耗时**: 1.56s · **浏览器**: chromium
**失败类型**: AssertionError

### 判定规则
> 搜索「小米」应返回至少 1 件商品（与「手机」「手表」同列参数化）

> 📌 **来源**: `test_search_valid_keyword_shows_results` 的 docstring 第一行。
> 若测试无 docstring，本字段显示 *（未声明，详见断言原文）*。

### 断言原文
```python
# tests/product/test_search.py:55
assert count > 0, f"搜索 '{keyword}' 应返回商品，但结果数为 {count}"
```

### 预期 vs 实际（pytest 内省）
```
assert 0 > 0
   ↑
   count = 0
   keyword = '小米'
   result_page = <SearchResultPage url=/search?q=小米>
```

> pytest 原生 assertion introspection。`count > 0` 这类表达式只能内省出
> 局部变量值，"预期 > 0" 是隐含的，无法显式提取。

### 页面元素校验
| 字段 | 值 |
|------|---|
| 失败 URL | `http://localhost:3000/search?q=小米` |
| 定位器 | *(原生 assert，无 playwright 错误结构)* |
| 期望 | *(原生 assert，未提取)* |
| 实际 | *(原生 assert，未提取)* |
| 推断原因 | 定位器与实际 DOM class 不匹配 |

> ⚠️ 本用例是**原生 `assert count > 0`** 失败（非 playwright expect）。
> 「定位器/期望/实际」字段仅在 playwright expect 失败时从错误消息结构化提取，
> 原生 assert 时这些字段留空，「推断原因」仍可基于 introspection 内的局部变量做关键词匹配。
> 「推断原因」**仅作参考**，不是 AI 智能诊断。

#### 原生 assert vs playwright expect 两种渲染示例

**A. 原生 assert 失败**（如 `assert count > 0`）：

| 字段 | 值 |
|------|---|
| 失败 URL | `...` |
| 定位器 | *(原生 assert，无 playwright 错误结构)* |
| 期望 | *(原生 assert，未提取)* |
| 实际 | *(原生 assert，未提取)* |
| 推断原因 | 定位器与实际 DOM class 不匹配 |

**B. playwright expect 失败**（如 `expect(loc).to_be_visible()`）：

| 字段 | 值 |
|------|---|
| 失败 URL | `...` |
| 定位器 | `.product-card` |
| 期望 | visible (LocatorAssertions.to_be_visible) |
| 实际 | not visible (Timeout 30000ms) |
| 推断原因 | 元素未在超时内出现/可见 |

判断逻辑：先跑 4.2.3 的正则匹配，4 个字段（locator/expected/received/action）至少命中 1 个 → 当 playwright expect 失败渲染（B）；全部未命中 → 当原生 assert 渲染（A）。

### 失败截图
| 类型 | 路径 |
|------|------|
| 视口截图 | `test-results/artifacts/screenshots/...-viewport.png` |
| 全页截图 | `test-results/artifacts/screenshots/...-fullpage.png` |
| Playwright 原生失败截图 | `test-results/artifacts/pytest-raw/.../test-failed-1.png` |

### 失败录屏与 Trace
| 类型 | 路径 | 复现命令 |
|------|------|---------|
| 录屏 | `test-results/artifacts/pytest-raw/.../video.webm` | `open <path>` |
| Trace | `test-results/artifacts/pytest-raw/.../trace.zip` | `python3 -m playwright show-trace <path>` |

### 其他诊断材料
- 页面源码: `test-results/artifacts/page-source/...html`
- Console 日志: `test-results/artifacts/console-logs/...log`
- 失败时 URL: `http://localhost:3000/search?q=%E5%B0%8F%E7%B1%B3`

---
````

#### 4.1.3 设计要点

1. 章节标题用「测试函数 docstring 首行」或「测试函数名做人类化转换」，比 nodeid 可读
2. 判定规则单独成块（引用块），方便扫读
3. 断言原文带行号，IDE 可点
4. 预期 vs 实际用代码块，pytest introspection 原样展示
5. 页面元素校验做成表，playwright 错误消息有结构就填，没结构就只展示 URL + 原文
6. 每个 artifact 路径独立成表，复制路径就能用
7. 「推断原因」明确标注「仅作参考」，不做 AI 智能诊断

### 4.2 数据采集规则

#### 4.2.1 判定规则（rule）

**docstring 约定**：测试函数第一行作为判定规则。

```python
def test_search_valid_keyword_shows_results(self, authed_page, keyword):
    """搜索「{keyword}」应返回至少 1 件商品（与「手机」「手表」同列参数化）"""
    ...
```

提取规则：

- 优先用 `inspect.getdoc(test_func)` 拿首行
- 若含 `{param}` 占位符，用 nodeid 末尾的参数化值替换（如 `[chromium-小米]` → 替换 `{keyword}` 为「小米」）。多个占位符按 nodeid 中 `[a-b-c]` 的顺序匹配（去掉第一个 chromium/firefox/webkit 引擎段）
- 无 docstring → fallback 到测试函数名做人类化转换（`test_search_valid_keyword_shows_results` → "Search valid keyword shows results"），并在 sidecar 里 `rule_source: "fallback_funcname"`
- 多行 docstring 只取首行；首行后内容忽略

**为什么不在 docstring 里写专门的 `:rule:` 标记**：用户已有 docstring 就是首行写意图，多加语法反而累赘。先按"首行即规则"的弱约定走，需要时再演进。

#### 4.2.2 断言原文（assertion）

从 `report.longrepr` 提取：

```python
def _parse_assertion_from_longrepr(report) -> dict:
    longrepr = report.longrepr
    if not hasattr(longrepr, "reprcrash"):
        return {"statement": "", "message": str(longrepr), "file": "", "introspection": ""}
    
    # 拿 traceback 最后一帧的源码行（assert 语句）
    tb_entry = longrepr.reprtraceback.reprentries[-1]
    statement = tb_entry.reprfileloc.source_line  # 'assert count > 0, f"..."'
    file_loc = f"{tb_entry.reprfileloc.path}:{tb_entry.reprfileloc.lineno}"
    
    # pytest 原生 introspection（reprcrash.message 含展开后的断言 + 局部变量）
    introspection = longrepr.reprcrash.message
    
    return {
        "statement": statement,
        "file": file_loc,
        "introspection": introspection,
        "message": report.longreprtext.split("\n")[-1] if report.longreprtext else "",
    }
```

**异常路径**：longrepr 是字符串（如 setup 阶段失败）→ 全部字段置空，message = str(longrepr)。

#### 4.2.3 页面元素校验（expect_failure）

playwright 失败消息有固定结构。用 4 个正则 + fallback：

```python
PATTERNS = {
    "locator":  re.compile(r'(?:Locator\(selector="([^"]+)"\)|locator[:=]\s*["\']([^"\']+)["\'])'),
    "expected": re.compile(r'Expected(?: value)?:\s*"?([^"\n]+)"?'),
    "received": re.compile(r'Received(?: value)?:\s*"?([^"\n]+)"?'),
    "action":   re.compile(r'(LocatorAssertions|PageAssertions)\.(\w+)'),
}
```

**fallback**：4 个字段都没匹配上 → 整段 playwright 错误消息原文存到 `expect_failure.raw`，渲染时表格只展示 URL + 整段消息。

**rule_hint（推断原因）**：基于已知字段做关键词匹配：

| 模式 | hint |
|------|------|
| Timeout + Locator | 元素未在超时内出现/可见 |
| Expected ≠ Received + 文本不匹配 | 文案变更 |
| count = 0 类断言 + locator 已知 | 定位器与实际 DOM class 不匹配 |
| Protocol error + navigate | URL/base_url 配置问题 |
| 网络请求 4xx/5xx（从 console-log/network 段） | 后端接口异常 |

匹配命中存到 `expect_failure.hint`，渲染时加 ⚠️ 提示。多重匹配按优先级取第一条。

#### 4.2.4 artifact 路径聚合

在 `_dump_failure_context` 时，已采集的 artifact 路径收集到一起：

```python
artifacts = {
    "screenshots": [
        str(screenshots_dir / f"{safe_nodeid}-viewport.png"),
        str(screenshots_dir / f"{safe_nodeid}-fullpage.png"),
    ],
    "page_source": str(page_source_dir / f"{safe_nodeid}.html"),
    "console_log": str(console_dir / f"{safe_nodeid}.log"),
}
```

**video/trace 延迟解析**：pytest-playwright 在用例结束时把 video/trace 写到 `--output/<slug>/`，但 hook 触发时这些文件还没生成。conftest **不写** video/trace 路径，让 `generate_failure_analysis.py` 在 session 结束后用 glob 匹配。

**slug 规则（关键，避免 glob 失败）**：pytest-playwright 0.8.0 的 sanitize 逻辑：

1. nodeid 转小写不（保留原 case）
2. 替换：`/` → `-`, `::` → `-`, `[` → `-`, `]` → ``, `(` → `-`, `)` → `-`, 空格 → `-`
3. **非 ASCII 字符**（含中文）→ `_uXXXX_` 形式转义（如 `小` → `u5c0f`，`米` → `u7c73`），具体由 `_pytest.pathlib.sanitize_name` 实现
4. 连续 `-` 折叠成单个 `-`

示例：`tests/product/test_search.py::TestSearchPositive::test_search_valid_keyword_shows_results[chromium-小米]` →
`tests-product-test-search-py-testsearchpositive-test-search-valid-keyword-shows-results-chromium-u5c0f-u7c73`

**conftest 落 JSON 时**：调一份独立的 `_sanitize_nodeid_to_slug(nodeid)` 函数（不依赖 pytest-playwright 内部 API），同时把 `--output` 选项值（pytest-playwright 的 `--output` 参数）一起写到 sidecar：`"pytest_raw_dir": "<--output 值>"`。`generate_failure_analysis.py` 拼路径 `<pytest_raw_dir>/<slug>/video.webm` 后用 `os.path.exists` 校验。

**容忍 unicode 转义差异**：如果 `_pytest.pathril.sanitize_name` 在不同 pytest 版本下转义规则变化（如 `_u5c0f_` vs `u5c0f`），`generate_failure_analysis.py` 用 fallback：直接 `glob("<pytest_raw_dir>/*/")` 列出所有目录，按"目录名与 nodeid sanitize 后的预期 slug 最长公共前缀"匹配。命中多个时报告渲染时加警告 `⚠️ 多个候选目录匹配，请人工确认`。

#### 4.2.5 phase（main / pre-run）

execute_tests.py 调 pytest 时，给前置阶段注入环境变量 `PYTEST_RUN_PHASE=pre-run`，主阶段不注入或注入 `main`。conftest 读取后写到 JSON。

### 4.3 JSON sidecar schema

```json
{
  "nodeid": "tests/product/test_search.py::TestSearchPositive::test_search_valid_keyword_shows_results[chromium-小米]",
  "slug_hint": "tests-product-test-search-py-testsearchpositive-test-search-valid-keyword-shows-results-chromium-u5c0f-u7c73",
  "phase": "main",
  "duration": 1.56,
  "browser": "chromium",
  "url": "http://localhost:3000/search?q=小米",
  "title": "搜索结果 - ShopLab",
  "failure_type": "AssertionError",
  "rule": "搜索「{keyword}」应返回至少 1 件商品（与「手机」「手表」同列参数化）",
  "rule_source": "docstring",
  "assertion": {
    "statement": "assert count > 0, f\"搜索 '{keyword}' 应返回商品，但结果数为 {count}\"",
    "file": "tests/product/test_search.py:55",
    "introspection": "assert 0 > 0\ncount = 0\nkeyword = '小米'",
    "message": "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0"
  },
  "expect_failure": {
    "locator": "",
    "expected": "",
    "received": "",
    "action": "",
    "hint": "定位器与实际 DOM class 不匹配（推断，仅作参考）",
    "raw": "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0\nassert 0 > 0\ncount = 0\nkeyword = '小米'"
  },
  "artifacts": {
    "screenshots": [".../viewport.png", ".../fullpage.png"],
    "page_source": ".../...html",
    "console_log": ".../...log"
  },
  "pytest_raw_dir": "test-results/artifacts/pytest-raw"
}
```

**字段填充规则（关键）**：

| 字段 | playwright expect 失败时 | 原生 assert 失败时 |
|------|--------------------------|---------------------|
| `locator` | 由正则提取 | 空 |
| `expected` | 由正则提取 | 空 |
| `received` | 由正则提取 | 空 |
| `action` | 由正则提取（如 `to_be_visible`） | 空 |
| `hint` | 关键词匹配得出 | 关键词匹配得出（基于 introspection 内的局部变量） |
| `raw` | 空 | 整段错误消息原文 |

判断逻辑：4 个字段（locator/expected/received/action）至少命中 1 个 → playwright expect 失败；全未命中 → 原生 assert 失败，所有结构化字段为空，raw 保留原文。

---

## 5. 错误处理与降级

failure_analysis 是辅助诊断工具，绝不能因为它的失败影响主测试流程。

| 失败点 | 处理 |
|--------|------|
| conftest hook 里 `inspect.getdoc` 抛异常 | try/except，rule = ""，rule_source = "fallback_funcname" |
| 解析 playwright 错误的正则全没命中 | `expect_failure.raw = <错误消息原文>`，渲染时表格只展示 URL + 原文 |
| `_dump_failure_context` 写 JSON 失败 | catch 后 `report.sections.append(("ui-test-executor", "[WARN] failure-context 写入失败: ..."))`，主测试结果不受影响 |
| `generate_failure_analysis.py` 找不到 report.xml | 报错退出，提示"请先跑 execute_tests.py" |
| report.xml 显示有失败但 failure-context/*.json 一个都没有 | 渲染"降级模式"：每条失败用例只展示 nodeid + message + traceback 末 20 行（≈ 现有 summary.md 失败段），顶部加警告 `⚠️ failure-context sidecar 缺失，报告以 JUnit XML 为唯一来源` |
| docstring 含 `{param}` 但 nodeid 没参数化 | 占位符原样保留，渲染时加 `（参数化值未匹配）` 提示 |
| video/trace 文件 glob 没匹配到 | 渲染时该行显示 `（未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off）` |
| `generate_failure_analysis.py` 本身崩 | execute_tests.py 在调用处 try/except，失败仅打印 `[WARN] failure_analysis 生成失败`，不改变 execute_tests.py 退出码 |

**降级原则**：永远能产出 MD 文件（即使内容只有 nodeid+message）。没有 sidecar JSON 就退到 JUnit XML；JUnit XML 也读不出细节就只显示 nodeid。三层降级。

---

## 6. 测试策略

| 测试目标 | 方式 |
|---------|------|
| docstring 提取（含 `{param}` 占位替换） | 纯 Python 单测：构造 fake test_func + nodeid，验证输出 |
| playwright 错误消息解析（locator/expected/received） | 纯 Python 单测：用预录的真实错误消息字符串作为输入 |
| rule_hint 关键词匹配 | 纯 Python 单测 |
| failure_analysis.md 渲染（给定 JSON + XML，验证输出包含期望字段） | 集成测试：构造 fixture 数据，跑 generate_failure_analysis.py，断言输出 MD 含关键字段 |
| 端到端（跑一个故意失败的测试） | 手动验证（用户 shop-lab-ui-test 项目，故意改坏一个断言，跑一遍看 MD 输出） |

**测试目录**：`evals/failure_analysis/`（与 skill 现有 evals 对齐）。

**3 个核心单测必须覆盖**：

1. docstring 提取 + 参数化占位替换
2. playwright 错误消息解析（locator + expected + received 全部命中）
3. JSON sidecar 缺失时的降级渲染

---

## 7. 边界与不做的事

- 不做 AI 智能诊断：「推断原因」是关键词匹配
- 不修改测试代码：所有信息从 docstring/pytest/playwright 原生拿，零侵入
- 不替换 summary.md：两份报告并存
- 不替代 Trace Viewer：MD 里只放 trace.zip 路径和复现命令，实际打开 Trace Viewer 是第 2 个能力的事
- 不做模板主题化：MD 样式固定（YAGNI）

---

## 8. 后续 spec 钩子

本 spec 是三能力中的第 1 项。后续两项会在各自 spec 中：

- **能力 2（Trace Viewer 快速打开）**：会消费本 spec 产出的 trace.zip 路径与复现命令
- **能力 3（操作高亮）**：会在 conftest 的失败采集环节注入高亮 overlay，本 spec 的截图路径字段会自动包含带高亮的截图

---

## 9. 实施路径

下一步进入 `writing-plans` skill，基于本 spec 编写分步骤实施计划（含文件改动顺序、单测编写顺序、集成测试节点、手动验证节点）。
