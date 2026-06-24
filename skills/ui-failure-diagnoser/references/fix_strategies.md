# 修复策略参考（Fix Strategies Reference）

## 修复策略总览（4 种）

| 策略 | 适用根因 | 实现方式 | 风险 |
|------|---------|---------|------|
| `ast_rewrite` | insufficient_wait / page_not_loaded / missing_iframe_switch / method_typo / deprecated_api | Python AST 改写 page 对象文件 | 🟢 低（确定性高，可回滚） |
| `claude_semantic` | locator_drift / shadow_dom_not_pierced | Claude 推断新 selector 并写入文件 | 🟡 中（需 verify） |
| `category_repair` | ENV / DATA / BUG 各子类 | 派发到类别专属模块（env_repair / data_repair / bug_repair） | 🟡 中（副作用操作走审计） |
| `none` | 兜底，无信号匹配 | 仅报告 | — |

## ast_rewrite 的 5 种确定性修复

### 1. insufficient_wait（等待不足）

**触发条件：** root_cause == `insufficient_wait`，evidence 含 `original_timeout_ms` 与 `suggested_timeout_ms`。

**实现：** `apply_fix.apply_insufficient_wait_fix()`

**修改规则：**

```python
# 原文件（pages/base_page.py）
class BasePage:
    def safe_fill(self, locator, text, timeout=10000):
        locator.wait_for(state="visible", timeout=timeout)

# 修改后
class BasePage:
    def safe_fill(self, locator, text, timeout=30000):  # ← 10000 → 30000
        locator.wait_for(state="visible", timeout=timeout)
```

**suggested_timeout_ms 计算公式：** `max(original_timeout_ms * 3, 30000)`

**扫描范围：** `pages/**/*.py`，找含 `timeout=<original>` 字面量的文件（通常是 `base_page.py`）。

### 2. page_not_loaded（页面未加载完）

**触发条件：** TIMEOUT_ERROR + message 含 `page.goto` / `page.wait_for_url`。

**实现：** 由 Claude 语义在 pages 层加 `page.wait_for_load_state("networkidle")`，AST 不自动改（避免破坏原有页面跳转流程）。

**建议位置：** pages 层的 `goto()` 调用之后、首条 locator 操作之前。

### 3. missing_iframe_switch（iframe 未切换）

**触发条件：** LOCATOR_ERROR + locator 在 iframe_contents 中能找到。

**实现：** `apply_fix.apply_iframe_switch_fix()`

**修改规则：**

```python
# 原文件
self._captcha_input = page.locator("input[name='captcha']")

# 修改后
self._captcha_input = page.frame_locator("iframe[src='/captcha']").locator("input[name='captcha']")
```

**AST 解析逻辑：**
1. `ast.parse(source)` 生成 AST
2. `ast.walk()` 找 `self.<target_var> = page.locator(X)` 形式的 Assign 节点
3. 用正则在源码中替换 `page.locator(` 为 `page.frame_locator("<iframe_css>").locator(`
4. 保留原始代码风格，不重新格式化

**幂等：** 若已用 `frame_locator(...)`，跳过修改。

### 4. method_typo（方法名拼写错误）

**触发条件：** SCRIPT_ERROR + message 含 `AttributeError: 'X' object has no attribute 'Y'`。

**实现：** `apply_fix.apply_method_typo_fix()`

**修改规则：**

```python
# 原文件
self._btn.clcik()  # ← 拼写错误

# 修改后
self._btn.click()
```

**AST 定位：**
- 用 `ast.Call` + `func.attr == typo_name` 精确定位方法调用
- 仅替换真实代码中的属性名，不误伤字符串字面量 / 注释 / 变量名
- 反向应用 offset（从文件末尾往前改，避免 offset 失效）

**智能推断：** `suggest_method_correction(typo)` 用 `difflib.get_close_matches` 从 Playwright 已知方法白名单（click / fill / wait_for / get_by_role 等 50+ 方法）中找最接近的。

### 5. deprecated_api（Playwright 已弃用 API）

**触发条件：** SCRIPT_ERROR + message 含 `DeprecationWarning: ... deprecated`。

**实现：** `apply_fix.apply_deprecated_api_fix()`

**修改规则（1:1 映射）：**

```python
# 原文件
element = self.page.query_selector("input")

# 修改后
element = self.page.locator("input")
```

**支持的映射（DEPRECATED_API_MAPPING）：**
- `query_selector` → `locator`
- `query_selector_all` → `locator`

> `dispatch_event` / `$eval` 系列需参数变换，MVP 不自动处理，由 Claude 语义改。

## claude_semantic 策略（2 种）

### locator_drift（DOM 改了）

**触发条件：** LOCATOR_ERROR + locator 既不在主文档也不在 iframe。

**工作流程：**
1. `locate_root_cause._collect_candidates()` 从 page-source 提取候选：
   - `placeholder="xxx"` → `{"kind": "placeholder", "value": "xxx"}`
   - `<label>xxx</label>` → `{"kind": "label", "value": "xxx"}`
   - `<button>xxx</button>` → `{"kind": "button_text", "value": "xxx"}`
   - `class="xxx"`、`id="xxx"` 同理
2. **pages.yaml 对比（可选）：** 若提供 `--pages-yaml`，`pages_yaml_resolver.resolve_locator_from_yaml()` 找同身份元素的 canonical locator
3. Claude 阅读候选 + yaml 推荐，推断新 selector
4. Claude 用 Edit 工具修改 page 对象
5. 后续走 `verify_fix.verify_single_test()` 验证

**pages.yaml 优先级：** `data-testid` > `role` > `label/placeholder/text` > `id` > `css` > `xpath`

### shadow_dom_not_pierced（Shadow DOM 未穿透）

**触发条件：** LOCATOR_ERROR + page-source 含 Shadow DOM 标志（`shadowRoot` / `attachShadow` / `customElements` / `<my-` / `data-v-`）。

**建议：** 使用 `>>>` piercing selector：

```python
# 原文件
self._btn = page.locator("button.submit")

# 推荐修改
self._btn = page.locator("my-component >>> button.submit")
```

由 Claude 语义完成（需读 page-source 找 shadow host）。

### 6. async_wait（异步列表加载等待缺失）

**触发条件：** SCRIPT_ERROR + message 含三点信号：
- 搜索语境（搜索/search/查询/检索）
- 正向期望（应返回/应为/should return/expected）
- 实际为 0（结果数为 0/count is 0/returned 0）

**实现：** `apply_fix.apply_async_wait_fix()`

**修改规则：**

```python
# pages/product/search_result_page.py（修改前）
class SearchResultPage(BasePage):
    def get_product_count(self) -> int:
        return self._product_cards.count()

# 修改后
class SearchResultPage(BasePage):
    def get_product_count(self) -> int:
        self._wait_for_product_list_loaded()  # ← AST 插入
        return self._product_cards.count()
```

```python
# pages/base_page.py（自动追加 helper）
class BasePage:
    ...
    def _wait_for_product_list_loaded(self, timeout_ms: int = 10000) -> None:
        """等商品列表首屏渲染完成。"""
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass
        try:
            self.page.wait_for_function(
                """() => {
                    const sels = ['.product-card', '.goods-card', '.search-result-item',
                                  '.item-card', '[data-product-id]', '.product-item'];
                    return sels.some(s => document.querySelectorAll(s).length > 0);
                }""",
                timeout=timeout_ms,
            )
        except Exception:
            pass
```

**幂等：** 若 `get_product_count` 方法体首行已是 `self._wait_for_*()`，跳过修改。
**目标方法选择：** `get_product_count` 是搜索流程与结果断言的天然桥梁，所有正/负向搜索测试都经此调用。
**verify 失败升级：** 若修复后 verify 重跑仍失败，自动 rollback 并升级根因为 `assertion_mismatch`（fix_strategy=none，仅报告）。

### 7. assertion_mismatch（verify 失败升级状态）

**触发条件：** `missing_async_list_wait` 修复后 `--verify` 重跑单用例仍失败。

**实现：** 无自动修复（fix_strategy=none）。

**升级动作（在 `_verify_and_maybe_rollback` 中）：**
1. rollback `.bak`（撤销 `apply_async_wait_fix` 的 AST 修改）
2. 在 `DiagnosisRecord` 记录 `upgraded_root_cause = "assertion_mismatch"`
3. 报告中显示升级原因 + 建议

**不再自动修复的原因：** 已证明 wait 不是根因，可能的真实根因（超出 skill 范围）：
- 后端搜索接口未返回数据（接口 bug）
- 测试数据库无对应商品（数据问题）
- 业务逻辑变更（应期望 0 而非 >0）

这些都需要人工介入，自动修复会误导。

**建议：** 报告中给出"建议排查后端搜索接口/测试数据"的指引，由用户决定下一步。

---

## category_repair 策略（3 类模块）

### ENV_ERROR（env_repair.py，4 子类）

| 子类 | 触发信号 | 修复动作 | 风险 |
|------|---------|---------|------|
| `missing_playwright_browser` | `Executable doesn't exist` | `python -m playwright install <browser>` | 🟢 自动 |
| `missing_python_package` | `ModuleNotFoundError` | `pip install <package>` | 🟡 自动（可关闭） |
| `port_conflict` | `Address already in use <port>` | `lsof -i :<port>` 提示 kill | 🔴 仅提示 |
| `service_unavailable` | `ECONNREFUSED <host>:<port>` | 提示启动后端服务 | 🔴 仅提示 |

**模块映射：** `yaml` → `pyyaml`，`cv2` → `opencv-python`，`PIL` → `Pillow`，`dotenv` → `python-dotenv` 等

### DATA_ERROR（data_repair.py，4 子类）

| 子类 | 触发信号 | 修复动作 |
|------|---------|---------|
| `unique_constraint_conflict` | `UNIQUE constraint failed: <table.col>` | 调 api-testdata-cleaner 清理脏数据 |
| `fixture_init_fail` | `fixture 'X' not found` | 提示排查 conftest + 跑 seed 脚本 |
| `test_user_consumed` | `user not found / disabled` | 提示在 pages 层加注册 fallback |
| `external_api_drift` | console-log 多次 4xx | 提示加 mock |

### BUG（bug_repair.py，4 子类）

| 子类 | 触发信号 | 修复动作 |
|------|---------|---------|
| `known_bug` | 命中 KNOWN_BUG_SIGNATURES | conftest.py 加 `xfail` marker |
| `intermittent_bug` | 历史记录 mixed pass/fail | conftest.py 加 `flaky` marker |
| `network_5xx_retry` | console-log 含 5xx | conftest.py 加 `flaky` marker |
| `stable_bug_report` | 稳定 Page Error | 仅强化报告（不自动 skip） |

**marker 注入机制（`_apply_conftest_marker`）：**
- 写到 `tests/conftest.py` 末尾
- 通过 `pytest_runtest_setup` hook 给匹配 nodeid 的 item 加 marker
- 幂等：signature 注释 `# ui-failure-diagnoser: marker <name> on <nodeid>`
- 同 marker + 同 nodeid 不重复注入

**核心约束：** 不改产品代码、不改测试断言；只在 conftest 加 marker、在 pages 层加 retry decorator。

## none 策略

适用于：`script_error_unspecified` / `env_error_unspecified` / `data_error_unspecified`（兜底分类）。

报告中给出分类与证据，由用户决定下一步。

## 验证流程

`ast_rewrite` 修复完成后，可选 `--verify` 触发单用例重跑：

```bash
python3 diagnose.py --junit-xml ... --verify --browser chromium
```

**verify 行为：**
1. `verify_single_test(nodeid)` 调起 `python3 -m pytest <nodeid>`
2. 解析 exit code：0 → passed；1 → failed；其他 → error
3. 失败或 error 时，自动 `rollback()` 恢复 `.bak`

**category_repair 不重跑** —— 副作用操作（pip install / 清理数据）不通过重跑单用例验证。

## 修复范围的安全约束

| 文件 | 是否修改 | 说明 |
|------|---------|------|
| `pages/**/*.py` | ✅ 修改 | AST rewrite（locator / timeout / iframe / typo / deprecated） |
| `tests/conftest.py` | ✅ 修改 | 仅加 marker hook（不改 fixture / setup 语义） |
| `tests/**/*.py`（除 conftest） | 🚫 永不修改 | 断言与业务语义神圣不可侵犯 |
| 任何非 pages / 非 conftest 文件 | 🚫 永不修改 | |

违反此约束会导致用户测试用例的语义被悄悄改变，是 **绝对禁止** 的行为。

## 风险分级执行策略

| 级别 | 操作示例 | 默认行为 | audit_log |
|------|---------|---------|-----------|
| 🟢 低风险 | `playwright install`、AST rewrite、conftest marker | 自动执行 | ✅ 记录 |
| 🟡 中风险 | `pip install`、调 api-testdata-cleaner | 默认执行，可 `auto_run=False` 关闭 | ✅ 记录 |
| 🔴 高风险 | `lsof kill -9`、数据库 seed、改 CI 配置 | 仅输出建议，不自动执行 | ✅ dry-run 记录 |
| 🚫 禁止 | 改 `tests/**` 断言、`rm -rf`、force push | 永不执行 | — |

所有 🟢🟡🔴 操作都通过 `AuditLogger.run_shell()` 走 JSONL 审计日志，路径默认 `<project>/.ui-failure-diagnoser/audit.log`。
