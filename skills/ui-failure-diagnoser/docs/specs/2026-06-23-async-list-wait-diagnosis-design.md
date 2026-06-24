# 异步加载等待缺失故障诊断（两阶段） — Design Spec

**Date:** 2026-06-23
**Skill:** ui-failure-diagnoser
**Status:** Approved (awaiting implementation plan)
**Trigger:** shop-lab-ui-test 3 个搜索用例失败：`搜索 '手表' 应返回商品，但结果数为 0`，原归类 SCRIPT_ERROR 兜底，缺细分。

---

## 1. 背景与动机

### 1.1 现状

shop-lab-ui-test 6 个失败用例中，3 个表现为 `AssertionError: 搜索 'XXX' 应返回商品，但结果数为 0`：
- 页面跳转正常（URL 是 `/search?q=手表`）
- `get_product_count()` 立即调用 `.count()`
- 列表异步加载尚未完成 → count=0 → 断言失败

当前分类走 SCRIPT_ERROR 兜底分支（"原生 AssertionError"），fix_strategy=category_repair，无细分根因，无标准化修复。

### 1.2 期望

当诊断到「搜索断言期望 >0 实际 =0」时：
1. **不再**判定为 SCRIPT_ERROR 兜底
2. **自动归类**为 `missing_async_list_wait`
3. **自动应用**标准化 AST 修复：在搜索流程与结果断言之间插入"列表加载完成"等待逻辑
4. **verify 闭环**：修复后重跑单用例；若仍失败，升级为 `assertion_mismatch`，撤销修复，仅报告

---

## 2. 分类架构（不变）

仍为 6 类：`ENV_ERROR / LOCATOR_ERROR / TIMEOUT_ERROR / DATA_ERROR / SCRIPT_ERROR / BUG`

优先级不变：`ENV > BUG > LOCATOR/TIMEOUT > DATA > SCRIPT`

**决策理由：** 不新增 category。新根因挂在 SCRIPT_ERROR 下作为子根因，避免破坏现有 6 类架构、优先级表、所有 evals 的"6 类"断言。

---

## 3. 新增 2 个根因（都挂在 SCRIPT_ERROR 下）

| root_cause | 触发条件 | fix_strategy | 自动修复动作 |
|---|---|---|---|
| `missing_async_list_wait` | SCRIPT_ERROR + 三点信号匹配（§4） | `ast_rewrite` | 插入 `_wait_for_product_list_loaded()` 调用 + base_page helper |
| `assertion_mismatch` | `missing_async_list_wait` 修复后 verify 仍失败 | `none` | 无（rollback，仅报告） |

**判定优先级（在 SCRIPT_ERROR 内部）：**
```
SCRIPT_ERROR 进入细分:
  if 三点信号匹配(message):
      root_cause = missing_async_list_wait
  else:
      root_cause = script_error_unspecified  # 原兜底
```

---

## 4. 信号匹配（三点 AND）

### 4.1 三个正则模式

```python
_SEARCH_CONTEXT = re.compile(
    r"搜索|search|查询|检索",
    re.IGNORECASE,
)
_POSITIVE_EXPECTATION = re.compile(
    r"应返回|应为|应存在|应该有|should return|should have|expected",
    re.IGNORECASE,
)
_ZERO_ACTUAL = re.compile(
    r"结果数.{0,3}0(?![0-9])"
    r"|count.{0,5}=\s*0(?![0-9])"
    r"|count is 0"
    r"|returned 0"
    r"|数量为 0"
    r"|共 0 条"
    r"|实际.{0,5}0(?![0-9])",
    re.IGNORECASE,
)
```

### 4.2 触发条件

```python
def _is_search_zero_assertion(message: str) -> bool:
    return all(
        p.search(message) for p in
        (_SEARCH_CONTEXT, _POSITIVE_EXPECTATION, _ZERO_ACTUAL)
    )
```

### 4.3 反向断言保护（自动）

shop-lab-ui-test 负向断言：
```python
assert count == 0, f"搜索 '{keyword}' 应无结果，但返回 {count} 个商品"
```

- ✅ 匹配 `_SEARCH_CONTEXT`（"搜索"）
- ✅ 匹配 `_POSITIVE_EXPECTATION`（"应"）
- ❌ **不匹配** `_ZERO_ACTUAL`（"返回 N 个"，N>0）

三点 AND 自动排除负向断言。

### 4.4 命中样例

| 消息 | 命中？ | 原因 |
|---|---|---|
| `搜索 '手表' 应返回商品，但结果数为 0` | ✅ | 三点全中 |
| `search 'watch' should return items, count is 0` | ✅ | 三点全中 |
| `搜索 '飞机' 应无结果，但返回 3 个商品` | ❌ | ZERO_ACTUAL 不匹配 |
| `购物车商品数应为 0` | ❌ | SEARCH_CONTEXT 不匹配 |
| `登录成功，但 nickname 为空` | ❌ | 三点全不匹配 |

---

## 5. AST 修复模板

### 5.1 目标方法

`pages/product/search_result_page.py:35` `get_product_count()`

**选择理由：**
- 搜索流程与结果断言之间的天然桥梁
- 所有正向/负向搜索测试都经此调用
- 负向断言也调用会多等 networkidle（~1-3s），可接受

**排除方案：**
- ❌ `search()` 方法：HomePage 的 search 流程分散在多个 page object，统一改不可行
- ❌ `assert_on_page()`：导航断言不应混入业务等待
- ❌ `navigate_with_keyword()`：只覆盖 goto 入口，不覆盖 HomePage.search 链路

### 5.2 修改前

```python
# pages/product/search_result_page.py
def get_product_count(self) -> int:
    return self._product_cards.count()
```

### 5.3 修改后

```python
# pages/product/search_result_page.py
def get_product_count(self) -> int:
    self._wait_for_product_list_loaded()
    return self._product_cards.count()
```

### 5.4 base_page.py 新增 helper

```python
# pages/base_page.py
def _wait_for_product_list_loaded(self, timeout_ms: int = 10000) -> None:
    """等商品列表首屏渲染完成。

    修复异步加载导致 get_product_count() 立即返回 0 的误报。
    策略：先等 networkidle（请求完结），再等常见商品 selector 出现至少 1 个元素。
    失败不抛异常，让后续 count/assert 揭示真实状态。
    """
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

### 5.5 AST 识别与插入算法

```python
def apply_async_wait_fix(source_path: Path, ...) -> FixResult:
    """幂等插入 _wait_for_product_list_loaded 调用。"""
    # 1. 解析 AST，找 get_product_count 方法定义
    # 2. 检查方法体首行是否已是 self._wait_for_* 调用 → 已存在则跳过
    # 3. 在方法体首行插入 self._wait_for_product_list_loaded()
    # 4. 同文件或 base_page.py 检查 helper 是否已定义 → 不存在则追加
    # 5. backup=True，写 .bak
```

### 5.6 幂等保证

- 扫描 `get_product_count` 方法体首行，若已是 `self._wait_for_*`，跳过修改
- 扫描 `base_page.py` 是否已定义 `_wait_for_product_list_loaded`，已存在则跳过追加

---

## 6. 两阶段诊断流程

### 6.1 流程图

```
                          ┌─────────────────────┐
                          │ JUnit failure input │
                          └──────────┬──────────┘
                                     ▼
                          ┌─────────────────────┐
                          │ classify_failure     │
                          │ → category           │
                          └──────────┬──────────┘
                                     ▼
                          ┌─────────────────────┐
                          │ locate_root_cause    │
                          │ → root_cause         │
                          └──────────┬──────────┘
                                     ▼
              ┌──────────────────────┴──────────────────────┐
              ▼                                              ▼
    root_cause == missing_async_list_wait         其他根因（原流程）
              │
              ▼
    ┌─────────────────────┐
    │ apply_async_wait_fix │  (Stage 1 修复)
    └──────────┬──────────┘
               ▼
    ┌─────────────────────┐
    │ verify_fix           │  (重跑单用例)
    │ .verify_single_test  │
    └──────────┬──────────┘
               ▼
       ┌───────┴────────┐
       │ verify result? │
       └───┬────────┬───┘
        PASS        FAIL
           │           │
           ▼           ▼
   保留修改      rollback .bak
   报告 PASS     root_cause 升级
                 = assertion_mismatch
                 报告升级原因
```

### 6.2 Stage 1：初次诊断

```python
# diagnose.py 伪代码
if root_cause == "missing_async_list_wait":
    fix_result = apply_async_wait_fix(target_file, backup=True)
    if args.verify:
        verify_result = verify_single_test(nodeid, ...)
        if not verify_result.passed:
            # Stage 2 升级
            rollback(fix_result.backup_path, target_file)
            record.upgraded_root_cause = "assertion_mismatch"
            record.upgrade_reason = (
                "已应用智能等待，verify 重跑仍失败。"
                "非异步加载问题，建议排查后端搜索接口/测试数据。"
            )
```

### 6.3 Stage 2：verify 失败升级

**升级触发条件：**
- 原根因是 `missing_async_list_wait`
- verify 重跑失败

**升级动作：**
1. `rollback()` 恢复 `.bak`（撤销 AST 修改）
2. 在 `DiagnosisRecord` 记录 `upgraded_root_cause = "assertion_mismatch"`
3. 报告中显示升级原因 + 建议
4. 不再尝试其他自动修复

**assertion_mismatch 不再修复的原因：**
- 已证明 wait 不是问题根因
- 可能的真实根因（超出 skill 范围）：
  - 后端搜索接口未返回数据（接口 bug）
  - 测试数据库无对应商品（数据问题）
  - 业务逻辑变更（应期望 0 而非 >0）
- 这些都需要人工介入，自动修复会误导

---

## 7. 报告字段扩展

### 7.1 概览新增字段

```markdown
| 维度 | 值 |
|------|-----|
| 分类：SCRIPT_ERROR | N |
| 根因：missing_async_list_wait | M |
| 根因：assertion_mismatch（升级）| K |  ← NEW
| 已应用 AST 修复 | M |
| 验证通过 | M-K |
| **验证失败 → 升级为 assertion_mismatch** | **K** |  ← NEW
| 回滚 | K |
```

### 7.2 明细新增字段

每个 `assertion_mismatch` 用例显示：

```markdown
### N. `tests/product/test_search.py::...`

- **失败阶段：** call
- **分类：** SCRIPT_ERROR
- **根因：** assertion_mismatch（由 missing_async_list_wait 升级）  ← NEW
- **升级原因：** 已应用智能等待，verify 重跑仍失败  ← NEW
- **建议：** 非异步加载问题，排查后端搜索接口/测试数据  ← NEW
- **原始错误：** `AssertionError: 搜索 '手表' 应返回商品，但结果数为 0`
- **AST 修复：** 已应用 → 已回滚  ← NEW
```

---

## 8. 影响范围

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `scripts/classify_failure.py` | 不动 | category 仍为 SCRIPT_ERROR |
| `scripts/locate_root_cause.py` | 新增 | `_locate_script_error()` 分支，处理三点信号匹配 |
| `scripts/apply_fix.py` | 新增 | `apply_async_wait_fix()` + 幂等扫描 + base_page helper 注入 |
| `scripts/verify_fix.py` | 扩展 | 失败回调支持 root_cause 升级标记 |
| `scripts/diagnose.py` | 扩展 | 编排两阶段流程，新增 `upgraded_root_cause` 字段 |
| `SKILL.md` | 扩展 | 根因表 12→14，新增两阶段流程章节 |
| `references/fix_strategies.md` | 扩展 | 新增 missing_async_list_wait + assertion_mismatch 章节 |
| `evals/core/test_locate_root_cause.py` | 扩展 | SCRIPT_ERROR 子根因测试 |
| `evals/core/test_apply_fix.py` | 新增 | `apply_async_wait_fix` 测试（插入、幂等、回滚） |
| `evals/core/test_diagnose.py` | 新增 | 两阶段流程测试（verify 通过/失败两条路径） |

---

## 9. 安全约束

- ✅ 只改 `pages/**/*.py`（`get_product_count` + `base_page._wait_for_product_list_loaded`）
- ✅ AST rewrite 必 backup，幂等（扫描已存在则跳过）
- ✅ verify 失败自动 rollback
- ✅ assertion_mismatch 不再自动修复（避免误导）
- 🚫 不改 `tests/**` 断言
- 🚫 不改 `conftest.py`（这次不需要 marker）

---

## 10. 验收标准（DoD）

### 10.1 功能验收

- [ ] 信号匹配：搜索正向断言 + 0 结果 → 命中 `missing_async_list_wait`
- [ ] 信号排除：搜索负向断言（应 0 实际 N）→ 不命中
- [ ] 信号排除：购物车断言（无 SEARCH_CONTEXT）→ 不命中
- [ ] AST 修复：`get_product_count` 首行插入 `self._wait_for_product_list_loaded()`
- [ ] AST 幂等：重复运行不重复插入
- [ ] base_page helper：自动追加 `_wait_for_product_list_loaded` 方法
- [ ] verify 通过：保留修改，报告 "已修复"
- [ ] verify 失败：rollback，升级为 `assertion_mismatch`，报告升级原因

### 10.2 实际用例验收

在 shop-lab-ui-test 上跑 `diagnose.py --verify`，对 3 个 `test_search_valid_keyword_shows_results` 失败用例：

- **理想路径**（后端有数据）：3 个用例 verify 通过，报告标记 "已修复 missing_async_list_wait"
- **现实路径**（后端确实没商品）：3 个用例 verify 失败，升级为 `assertion_mismatch`，rollback，报告建议人工排查后端

### 10.3 evals 验收

- 所有现有 evals（193 个）继续通过
- 新增 evals ≥ 8 个：
  - `test_locate_script_error_*`：信号匹配/排除（≥ 4 个）
  - `test_apply_async_wait_fix_*`：插入/幂等/helper 注入（≥ 3 个）
  - `test_diagnose_verify_upgrade_*`：两阶段流程（≥ 1 个）

---

## 11. 风险与缓解

| 风险 | 概率 | 缓解 |
|---|---|---|
| 信号误报：非搜索场景命中 | 低 | 三点 AND + SEARCH_CONTEXT 限定，§4.3 验证反向断言不命中 |
| helper selector 不匹配项目 | 中 | 6 个通用 selector 兜底 + wait 失败不抛异常 |
| 负向断言被 wait 拖慢 | 低 | networkidle 通常 1-3s，可接受 |
| verify 在 CI 不可用 | 低 | `--verify` 是可选 flag，不传则只 Stage 1 |
| 升级后用户看不懂 | 低 | 报告明确显示"升级原因"+"建议" |

---

## 12. 后续扩展（YAGNI，本次不做）

- **多个 list 方法的通用化**：当前只针对 `get_product_count`。未来可扩展到 `get_order_list_count` / `get_cart_item_count` 等。本次仅做商品列表。
- **pages.yaml 驱动的 selector**：当前 helper 用通用 selector 列表。未来可从 pages.yaml 提取项目专属 selector。本次保持通用。
- **网络抓包验证**：当前只看 DOM。未来可看 console-log 的 Network 段判断接口是否返回数据。本次不做。
