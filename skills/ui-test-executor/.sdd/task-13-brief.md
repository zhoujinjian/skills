### Task 13: references/failure_analysis_guide.md

**Files:**
- Create: `references/failure_analysis_guide.md`

- [ ] **Step 1: 写文档**

文件 `references/failure_analysis_guide.md`：

````markdown
# 失败分析报告使用指南

## 给测试编写者的约定

### 1. docstring 写判定规则（弱约定）

每个测试函数第一行 docstring 会被提取为「判定规则」：

```python
@pytest.mark.parametrize("keyword", ["手机", "小米", "手表"])
def test_search_valid_keyword_shows_results(self, authed_page, keyword):
    """搜索「{keyword}」应返回至少 1 件商品"""
    ...
```

报告里渲染为：

> ### 判定规则
> > 搜索「小米」应返回至少 1 件商品

**约定细节**：

- 第一行即规则，多行 docstring 只取首行
- 含 `{param}` 占位符时，用 nodeid 末尾参数化值替换（去掉 chromium/firefox/webkit 引擎段）
- 无 docstring → fallback 到测试函数名做人类化转换，标注 `fallback_funcname`
- 含占位符但 nodeid 无参数化 → 标注 `docstring_unmatched_param`

### 2. 用 playwright expect 提升报告密度

playwright expect 失败时（如 `expect(loc).to_be_visible()`），错误消息有结构化字段，报告会自动填充：

| 字段 | 例 |
|------|---|
| 定位器 | `.product-card` |
| 期望 | visible |
| 实际 | Timeout 30000ms |
| 推断原因 | 元素未在超时内出现/可见 |

原生 `assert` 失败时（如 `assert count > 0`），这些字段为空，只展示断言原文 + pytest introspection。

**写测试时的取舍**：
- 用 `expect(loc).to_have_count(n)` 比 `assert loc.count() == n` 报告更丰富
- 但不要为了报告字段把所有 assert 改成 expect——只在断言确实是"页面元素状态"时用 expect

### 3. 推断原因（hint）

报告里「推断原因」字段基于关键词匹配，**仅作参考**，不是 AI 智能诊断：

| 触发模式 | 推断 |
|----------|------|
| Protocol error + navigate | URL/base_url 配置问题 |
| Timeout + Locator 已知 | 元素未在超时内出现/可见 |
| Expected ≠ Received | 文案变更 |
| count = 0 类断言 + locator 已知 | 定位器与实际 DOM class 不匹配 |

---

## 给运维 / CI 的约定

### 1. failure_analysis.md 生成时机

- 仅当 `report.xml` 显示 ≥1 失败时生成
- 全通过 → 不生成（文件不存在 = 跑绿）
- 由 `execute_tests.py` 在 pytest 进程结束后自动调起
- 可用 `--no-failure-analysis` 关闭

### 2. 降级行为

| 失败点 | 渲染 |
|--------|------|
| conftest hook 异常未写 sidecar | 退到 JUnit XML 渲染（nodeid + message + traceback） |
| sidecar JSON 损坏 | 同上 |
| video/trace 文件未生成 | 显示「（未生成，可能此用例未失败到 call 阶段）」 |
| video/trace 多候选目录 | 显示「⚠️ 多个候选目录匹配，请人工确认」 |

### 3. 手动重新生成

```bash
python3 <skill_dir>/scripts/generate_failure_analysis.py \
    --junit-xml test-results/report.xml \
    --artifacts-dir test-results/artifacts \
    --output-dir test-results \
    --execution-summary "P0 and run_smoke · chromium · headless"
```

### 4. playwright 错误消息解析失败时

`_parse_playwright_error` 的 4 个正则全没命中 → 报告里「定位器/期望/实际」字段为空，raw 字段保留整段错误消息原文。

如果你用的是较新版本的 playwright（错误消息格式有变），需要更新 `assets/conftest_template.py` 里 `_PW_PATTERNS` 字典。

---

## 常见问题

### Q1: 报告里 rule 字段显示「fallback_funcname」

A: 测试函数没写 docstring，或 docstring 是空的。给测试函数加一行 docstring 即可。

### Q2: 截图/录屏路径显示「（未采集）」

A: 可能原因：
1. 用例在 setup 阶段失败（page 还没初始化）
2. conftest hook 未集成到项目的 `tests/conftest.py`（参考 SKILL.md Step 5）
3. execute_tests.py 未传 `--artifact-root`

### Q3: video/trace 显示「多个候选目录匹配」

A: `pytest-raw/` 下有多个相似 slug 的目录，脚本无法自动选。打开 `pytest-raw/` 看 目录列表，确认哪个是当前失败用例的，手动用 `playwright show-trace` 打开。
````

- [ ] **Step 2: Commit**

```bash
git add references/failure_analysis_guide.md
git commit -m "docs(failure-analysis): user-facing guide for docstring convention + degradation"
```

---

