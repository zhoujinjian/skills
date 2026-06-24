# Task 11 Report: 自动调起 generate_failure_analysis.py + `--no-failure-analysis` 开关

**Status**: DONE
**Phase**: 3 (集成层)
**Files modified**: `scripts/execute_tests.py`（仅此一个）

## What I Implemented

在 `scripts/execute_tests.py` 中完成三处改动，让 `execute_tests.py` 在主测试结束后自动调起 `generate_failure_analysis.py` 生成 `failure_analysis.md`：

1. **`parse_args` 追加 `--no-failure-analysis` 开关**（紧跟 `--dry-run` 之后）
   - `dest="no_failure_analysis"`, `action="store_true"`
   - 默认 `False`（即默认开启自动生成）
   - 帮助文案：「关闭自动生成 failure_analysis.md（默认开启：有失败时自动生成）」

2. **`main()` 末尾追加条件调用**
   - 在 `main_exit = run_pytest(...)` 之后、`return main_exit` 之前插入
   - 三重守卫：`not args.no_failure_analysis` / `not args.dry_run` / `not args.list_only`
   - 调用 `_maybe_generate_failure_analysis(output_dir, args, main_exit)`
   - 不接收返回值，不改 `main_exit`

3. **新增函数 `_maybe_generate_failure_analysis(output_dir, args, main_exit)`**
   - 放在 `if __name__ == "__main__":` 之前
   - 解析 `output_dir/report.xml` 的 `failures` + `errors` 总和，都为 0 时直接 return
   - XML 解析失败 → 不中断，继续尝试调用子脚本（让子脚本自己报错）
   - 子脚本缺失 → 静默 return
   - 子脚本崩溃 / 超时 → 仅打印 `[WARN]`，绝不向上抛异常
   - 子脚本 stdout/stderr 全部透传到 stderr（不污染 pytest stdout）
   - 构造 `execution-summary` 字符串：marker 表达式 · 浏览器 · headless/headed

## TDD/Validation Evidence

### 1. 语法 + flag 注册

```
$ /usr/local/bin/python3.13 -c "import ast; ast.parse(open('.../execute_tests.py').read())"
SYNTAX OK

$ python3 execute_tests.py --help | grep -A2 no-failure-analysis
  --no-failure-analysis
                        关闭自动生成 failure_analysis.md（默认开启：有失败时自动生成）
```

### 2. Flag 解析（默认 vs 显式关闭）

```
default no_failure_analysis: False (expected False)
with --no-failure-analysis: True (expected True)
```

### 3. 静态 smoke test（Step 6 of brief，shop-lab-ui-test 已有 report.xml）

```
$ python3 generate_failure_analysis.py \
    --junit-xml test-results/report.xml \
    --artifacts-dir test-results/artifacts \
    --output-dir test-results \
    --execution-summary "smoke test"
[INFO] 检测到 1 个失败用例，开始生成 failure_analysis.md
[OK] 已生成 /Users/zhoujinjian/ai_project/shop-lab-ui-test/test-results/failure_analysis.md
```

### 4. 直接调 `_maybe_generate_failure_analysis`（带 1 个失败的 mock XML）

```
[INFO] 检测到 1 个失败用例，开始生成 failure_analysis.md
[OK] 已生成 /private/tmp/t11_test/failure_analysis.md
failure_analysis.md exists: True
```

### 5. 边缘 case 三连（不抛异常合约验证）

| Case | 输入 | 预期 | 实际 |
|------|------|------|------|
| 零失败 | `failures=0 errors=0` | 静默 return，不生成 md | OK（未生成） |
| 缺 XML | `report.xml` 不存在 | 静默 return | OK（无异常） |
| XML 损坏 | `not valid xml <<<` | 容忍 parse error，调用子脚本，子脚本失败时打印 [WARN] | OK（打印 `[WARN] generate_failure_analysis.py 退出码 1`） |

### 6. 端到端 execute_tests.py（Step 4 of brief）

尝试在 shop-lab-ui-test 跑完整流程，命中一个**预先存在的环境问题**：项目 pytest 环境缺 `pytest-html`，导致 pytest 退出码 4，未生成 report.xml，因此 `_maybe_generate_failure_analysis` 在第一道 guard（`report_xml.exists()`）就静默 return。此为环境层问题，非 Task 11 改动缺陷。Step 6 的静态 smoke test 和直接调用验证已覆盖集成逻辑。

## Files Changed

- `/Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/execute_tests.py`
  - `parse_args`: 追加 `--no-failure-analysis` 参数
  - `main`: 在 `main_exit = run_pytest(...)` 后追加 3-guard 条件调用
  - 新增 `_maybe_generate_failure_analysis` 函数（约 55 行）

## Self-Review Findings

- [x] `parse_args` 末尾追加了 `--no-failure-analysis`（`dest="no_failure_analysis"`, `action="store_true"`）
- [x] `main` 函数末尾追加了对 `_maybe_generate_failure_analysis` 的条件调用
- [x] 条件调用包含三个守卫：`not args.no_failure_analysis` / `not args.dry_run` / `not args.list_only`
- [x] `_maybe_generate_failure_analysis` 函数定义放在 `if __name__ == "__main__":` 之前
- [x] 函数先扫 JUnit XML 的 `failures` 和 `errors` 总和，都为 0 时直接 return
- [x] 脚本缺失时不抛异常，静默 return
- [x] 子脚本崩溃时只打印 `[WARN]`，不改 `execute_tests.py` 的退出码
- [x] 子脚本的 stdout/stderr 都透传到 stderr（不污染 pytest stdout 报告）
- [x] 端到端验证：`failure_analysis.md` 在有失败时自动生成（静态 smoke test + 直接调用均通过；完整 e2e 受环境缺 pytest-html 阻塞，已记录）
- [x] `--no-failure-analysis` 开关生效（通过 `parse_args` 单测验证）

## Deviations

**None** — 严格按 brief 实施：
- `sys` / `subprocess` 已在文件顶部导入（line 38-39），无需新增
- `build_marker_expression` 实际签名 `(tags, modules, priority, extra)` 与 brief 调用 `build_marker_expression(args.tags, args.modules, args.priority, args.marker_expr)` 完全匹配
- 所有变量名、guard 顺序、warning 格式与 brief 一致

## Concerns

1. **子脚本 stdout 全量透传到 stderr**：`generate_failure_analysis.py` 若打印大量诊断信息，可能与 pytest 自身 stderr 输出交织。当前脚本只打印 2 行（`[INFO]` + `[OK]`/`[WARN]`），影响可控；若后续 Task 12-14 扩展脚本输出量，需要回头加 quiet flag。
2. **30s 超时硬编码**：`subprocess.run(..., timeout=30)` 对极大规模测试套件（>1000 失败用例）可能不够。当前 shop-lab-ui-test 规模（~10 用例）远在安全范围。
3. **execution-summary 复算 marker**：在 `_maybe_generate_failure_analysis` 里再次调用 `build_marker_expression(...)`，与 `build_pytest_args` 里的计算重复一次。两次结果应一致（纯函数），但若未来 `build_marker_expression` 改为有状态，需重构为缓存。当前实现可接受。
4. **shop-lab-ui-test 环境缺 pytest-html**：预先存在问题（与 Task 11 无关），导致完整 e2e 无法跑通。建议在 Task 15 端到端验证阶段统一修复（`pip install pytest-html`）。
