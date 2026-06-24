# Failure Analysis Report 用户指南

本指南面向**测试编写者**与**运维/CI 使用者**两类读者，帮助你：

- 看懂 `failure_analysis.md` 里每段在说什么
- 写出能让报告字段更丰富的测试代码
- 出问题时知道是哪一步降级了、怎么修

字段级 schema 见 `failure_report_schema.md`。本文件只讲「怎么用」。

---

## 一、给测试编写者的约定

### 1.1 docstring = 判定规则（弱约定）

每个测试函数首行 docstring 会被自动提取为报告里的「判定规则」：

```python
@pytest.mark.parametrize("keyword", ["手机", "小米", "手表"])
def test_search_valid_keyword_shows_results(self, authed_page, keyword):
    """搜索「{keyword}」应返回至少 1 件商品"""
    ...
```

报告渲染为：

> ### 判定规则
> > 搜索「小米」应返回至少 1 件商品
> > 📌 **来源**: 测试 docstring 首行

**约定细节：**

| 情况 | 报告里的来源标注 |
|------|----------------|
| 多行 docstring | 只取首行 |
| 含 `{param}` 占位符 + nodeid 有参数化值 | 用 nodeid 末尾参数替换（去掉 chromium/firefox/webkit 引擎段），标注 `docstring` |
| 无 docstring | fallback 到测试函数名人类化（`test_xxx_yyy` → `xxx yyy`），标注 `fallback_funcname` |
| 含占位符但 nodeid 无参数化 | 保留字面 `{param}`，标注 `docstring_unmatched_param` |

**写法建议**：用一句业务语义描述规则，含参数化占位符。避免「测试搜索功能」这种泛泛描述。

### 1.2 用 playwright expect 提升报告密度

playwright `expect()` 失败时（如 `expect(loc).to_be_visible()`），错误消息有结构化字段，报告自动填充：

| 字段 | 示例值 |
|------|--------|
| 定位器 | `.product-card` |
| 期望 | visible |
| 实际 | Timeout 30000ms |
| 推断原因 | 元素未在超时内出现/可见 |

原生 `assert` 失败时（如 `assert count > 0`），这些字段为空，报告会显示 `*(原生 assert，未提取)*` 占位。

**取舍：**

- `expect(loc).to_have_count(n)` > `assert loc.count() == n` — 报告字段更丰富
- 但**不要**为了报告字段把所有 assert 改成 expect — 只在断言确实是「页面元素状态」时用 expect
- 业务逻辑断言（如「搜索结果数应 > 0」）继续用原生 assert 没问题，报告会展示断言原文 + pytest 内省

### 1.3 推断原因（hint）的边界

报告里「推断原因」字段基于**正则 + 关键词匹配**，**仅作参考**，不是 AI 智能诊断：

| 触发模式 | 推断文本 |
|----------|---------|
| `Protocol error` + `navigate` | URL/base_url 配置问题（推断，仅作参考） |
| `Timeout \d+ms` + Locator 已知 | 元素未在超时内出现/可见（推断，仅作参考） |
| Expected ≠ Received | 文案变更（推断，仅作参考） |
| `count = 0` 类断言 + Locator 已知 | 定位器与实际 DOM class 不匹配（推断，仅作参考） |
| `count = 0` 类断言 + Locator 未知 | 结果数为 0（推断，仅作参考） |

如果你的失败模式不在上表，推断原因可能为空。这时请看「错误消息原文」或 Trace 做人工判断。

---

## 二、看懂报告：7 个子章节怎么读

打开 `failure_analysis.md`，每条失败用例一节，固定 7 个子章节。从上往下读：

### 2.1 判定规则

**看什么**：这条用例本来在验证什么业务规则。

**行动**：如果规则文字不清楚（如 `fallback_funcname`），回去给测试加 docstring。

### 2.2 断言原文

**看什么**：哪一行代码挂了，assert 长什么样。

**行动**：定位到源文件对应行号。如果断言里有动态值（`assert count > 0`），看下一节的 introspection 知道 `count` 当时是多少。

### 2.3 预期 vs 实际（pytest 内省）

**看什么**：pytest 展开的 assert 表达式 + 局部变量值。

例：`assert count > 0` 会展开为 `assert 0 > 0`，你就知道 count 当时是 0。

**行动**：如果 introspection 为空 `*(无内省信息)*`，说明 sidecar 缺失，走降级路径（见 §四）。

### 2.4 页面元素校验

**看什么**：

- **失败 URL**：失败瞬间的页面 URL — 直接复制到浏览器复现
- **定位器**：playwright 正在找的元素
- **期望/实际**：期望的状态 vs 实际状态
- **推断原因**：可能的问题原因（仅作参考）

**playwright expect 失败 vs 原生 assert 失败**：

| 字段 | playwright expect | 原生 assert |
|------|-------------------|-------------|
| 定位器/期望/实际 | 从错误消息正则提取 | `*(原生 assert)*` 占位 |
| 推断原因 | 关键词匹配 | 关键词匹配（可能为空） |
| 错误消息原文 | 不显示（结构化字段已够） | 显示前 500 字符 |

**行动**：

- 看到 `*(原生 assert)*` 占位 → 报告密度低是正常的，看「错误消息原文」段
- 失败 URL 复现不出 → 可能是数据/登录态问题，看 console-log 里的 Network 段

### 2.5 失败截图

**看什么**：视口截图（当时可见区域） + 全页截图（整个页面） + Playwright 原生失败截图。

**行动**：

- 视口截图快速看元素布局是否错位
- 全页截图看整体页面是否加载完整
- Playwright 原生 `test-failed-N.png` 是 pytest-playwright 自己截的，位置可能与 conftest 截图略不同

路径显示 `*(未采集)*` → 见 §四 降级说明。

### 2.6 失败录屏与 Trace

**看什么**：`video.webm`（失败录屏） + `trace.zip`（Playwright Trace）。

**行动**：

- **看录屏**：`open <path>`（Mac）或直接拖到浏览器
- **看 Trace**：`python3 -m playwright show-trace <path>`，会打开 Trace Viewer UI，能逐帧看每个 Playwright action 的 DOM 快照、网络请求、控制台日志

⚠️ 警告「多个候选目录匹配，请人工确认」→ `pytest-raw/` 下有多个相似 slug 的目录，脚本不敢猜。打开 `pytest-raw/` 目录看时间戳或目录名后缀，手动选一个用 `show-trace` 打开。

### 2.7 其他诊断材料

**看什么**：

- **页面源码** HTML 快照：失败瞬间的 DOM，用浏览器打开看结构
- **Console 日志**：5 段合并（Page Errors / Console ERROR\|WARN / Console 其他 / Network / Performance）
- **失败时 URL**：再次列出，方便复制

**行动**：

- Page Error 段有红色错误 → 前端代码抛异常，找前端
- Network 段有 4xx/5xx → 接口挂了，找后端
- Console 段有 vue/react 警告 → 不一定致命，但值得看

---

## 三、常见失败模式速查

| 报告里的信号 | 可能原因 | 排查动作 |
|-------------|---------|---------|
| `Protocol error ... navigate` + URL 为 base_url | 服务起没起 / base_url 配错 | `curl <base_url>` 验证 |
| `Timeout 30000ms` + 定位器非空 | 元素没出来（DOM 慢 / 选择器过时 / 数据问题） | 打开 Trace 看 action 序列；检查页面源码 |
| Expected="visible" Received="hidden" | 元素存在但不可见（CSS display / 父元素 overflow） | 看全页截图 + 页面源码 |
| Expected text ≠ Received text | 文案变更（i18n / 产品改版） | 对比需求文档 |
| `count = 0` + 推断「定位器不匹配」 | 选择器过时（class 名变了） | 打开页面源码，Ctrl+F 找原选择器 |
| `count = 0` + 推断「结果数为 0」 | 数据问题 / 搜索逻辑问题 | 看接口返回（console-log Network 段） |
| `AssertionError` + 原生 assert | 业务逻辑挂了，不是 UI 问题 | 看 introspection 里的变量值 |
| setup 阶段失败（page 为 None） | fixture 挂了（登录失败 / page 没初始化） | 报告里 URL/title 都为空；看 console-log |

---

## 四、给运维 / CI 的约定

### 4.1 自动触发条件

| 触发条件 | 行为 |
|---------|------|
| pytest 退出后 `report.xml` 显示 ≥1 failure/error | 自动生成 `failure_analysis.md` |
| 全通过 | **不生成文件**（文件不存在 = 跑绿） |
| `--dry-run` / `--list-only` | 不生成（没真正跑测试） |
| `--no-failure-analysis` | 不生成（显式关闭） |

**文件位置**：`<output-dir>/failure_analysis.md`（通常 `test-results/failure_analysis.md`）

### 4.2 降级行为

报告**永远会生成**（除非全通过或显式关闭）。降级路径：

| 失败点 | 报告行为 |
|--------|---------|
| sidecar JSON 缺失（conftest 未集成） | 退到 JUnit XML 渲染：仅显示 nodeid + message + traceback；其他字段为 `*(未采集)*` 或 `*(原生 assert)*` 占位 |
| sidecar JSON 损坏 | 同上 |
| video/trace 文件未生成 | 显示「*(未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off)*」 |
| `pytest-raw/` 下多个候选目录 | 显示「⚠️ 多个候选目录匹配，请人工确认」 |
| `generate_failure_analysis.py` 本身崩溃 | `execute_tests.py` 打印 `[WARN]`，不修改退出码；pytest 的退出码照常返回 |

### 4.3 关闭自动触发

```bash
# CI 只想要 JUnit XML，不要 MD 报告
python3 execute_tests.py tests/ --priority P0 --no-failure-analysis
```

常见场景：CI 流水线已有自己的报告渲染（Allure / ReportPortal 等），不希望 ui-test-executor 也产 MD。

### 4.4 手动重新生成

不重跑测试，直接基于已有 `report.xml` + artifacts 重新生成 MD：

```bash
python3 <skill_dir>/scripts/generate_failure_analysis.py \
    --junit-xml test-results/report.xml \
    --artifacts-dir test-results/artifacts \
    --output-dir test-results \
    --execution-summary "P0 and run_smoke · chromium · headless"
```

常见场景：

1. 你改了 `generate_failure_analysis.py` 的渲染逻辑，想重新出报告看效果
2. 项目 conftest 第一次集成 `_dump_failure_context` hook 后，想让旧 report.xml 也享受 sidecar 加成（前提 artifacts 还在）

### 4.5 failure_analysis.md vs summary.md

两个报告各司其职：

| 报告 | 字段密度 | 触发条件 | 用途 |
|------|---------|---------|------|
| `summary.md` | 低（概览统计 + 简要失败明细） | **每次执行都生成** | CI 看板、流水线摘要、build description |
| `failure_analysis.md` | 高（每条失败一节，含 rule/assertion/playwright 字段/artifact 路径） | **仅 ≥1 失败时生成** | 深度故障诊断、人工排障 |

CI 摘要抓 `summary.txt` 的单行；开发排障看 `failure_analysis.md`。

---

## 五、常见问题

### Q1：报告里 rule 字段显示「fallback_funcname」

**A**：测试函数没写 docstring，或 docstring 是空的。给测试函数加一行 docstring 即可：

```python
def test_login_with_valid_credentials(self, page):
    """有效账号密码登录后应跳转到首页"""
    ...
```

### Q2：截图/录屏路径显示「（未采集）」

**A**：可能原因：

1. 用例在 setup 阶段失败（page fixture 还没初始化，`_collect_failure_artifacts` 早 return）
2. 项目 `tests/conftest.py` 未集成失败采集 hook（参考 `SKILL.md` Step 5）
3. `execute_tests.py` 没传 `--artifact-root`（默认 `./test-results/artifacts`）

### Q3：video/trace 显示「多个候选目录匹配」

**A**：`pytest-raw/` 下有多个相似 slug 的目录。常见原因：

- 跑了多次同一用例（旧目录没清理）
- nodeid 里含特殊字符，`_sanitize_nodeid_to_slug` 在不同 pytest-playwright 版本转义规则略不同

**解决**：

```bash
# 清掉 pytest-raw 重跑
rm -rf test-results/artifacts/pytest-raw
python3 execute_tests.py ...
```

或手动看 `pytest-raw/` 下目录列表，用最新的那个：

```bash
ls -lt test-results/artifacts/pytest-raw/ | head
python3 -m playwright show-trace test-results/artifacts/pytest-raw/<手选目录>/trace.zip
```

### Q4：playwright 错误消息字段为空，但我知道是 expect 失败

**A**：`_parse_playwright_error` 的 4 个正则（locator / expected / received / action）全没命中。

可能原因：你用的 Playwright 版本错误消息格式变了。检查 `assets/conftest_template.py` 里的 `_PW_PATTERNS` 字典，可能需要加新 pattern。

**临时方案**：报告会退化为「错误消息原文」展示前 500 字符，仍可人工阅读。

### Q5：sidecar JSON 在哪？我没看到 failure-context 目录

**A**：sidecar 由 conftest 的 `_dump_failure_context` 写入。目录不存在说明：

1. 项目 `tests/conftest.py` 没集成此 hook（报告会走降级模式）
2. 所有失败都在 setup 阶段（page 为 None 时 `_collect_failure_artifacts` 早 return，不会调 `_dump_failure_context`）

集成方式见 `SKILL.md` Step 5。

---

## 六、相关文档

- 字段级 schema：`references/failure_report_schema.md`
- 主流程：`SKILL.md` Step 6.5
- 设计文档：`docs/specs/2026-06-21-failure-analysis-report-design.md`
- artifact 采集机制：`SKILL.md` Step 0.5（6 类 artifact 总览）
