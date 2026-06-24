# Task 11 Brief: 自动调起 generate_failure_analysis.py + `--no-failure-analysis` 开关

**Phase**: 3 (集成层)
**Files to modify**: `scripts/execute_tests.py`（仅此一个文件）
**Prerequisite**: Task 10 已完成（`run_pytest` 已接受 `phase` 参数，已注入 `PYTEST_RUN_PHASE` 环境变量）

## 环境约束（重要）

- skill 目录 `/Users/zhoujinjian/.claude/skills/ui-test-executor/` **非 git repo** → 所有 commit 步骤改为「保存文件即完成」，**不要执行 `git add` / `git commit`**
- 用系统 `python3`（非 workbuddy 解释器，那个没 pytest）

## 实施步骤

### Step 1: 在 `parse_args` 末尾追加 `--no-failure-analysis` 开关

找到 `parse_args` 函数末尾（`--dry-run` 之后），追加：

```python
    # ============ 失败报告 ============
    parser.add_argument(
        "--no-failure-analysis",
        dest="no_failure_analysis",
        action="store_true",
        help="关闭自动生成 failure_analysis.md（默认开启：有失败时自动生成）",
    )
```

### Step 2: 修改 `main` 函数末尾，追加自动调用

把 Task 10 修改后的 main 函数末尾段（应该长这样）：

```python
    main_exit = run_pytest(main_pytest_args, cwd=cwd, label="MAIN", phase="main")
    return main_exit
```

改为：

```python
    main_exit = run_pytest(main_pytest_args, cwd=cwd, label="MAIN", phase="main")

    # 自动生成 failure_analysis.md（仅当有失败且未显式关闭）
    if not args.no_failure_analysis and not args.dry_run and not args.list_only:
        _maybe_generate_failure_analysis(output_dir, args, main_exit)

    return main_exit
```

### Step 3: 在文件末尾（`if __name__ == "__main__":` 之前）追加新函数

```python
def _maybe_generate_failure_analysis(output_dir: Path, args: argparse.Namespace, main_exit: int) -> None:
    """执行后自动生成 failure_analysis.md（若 report.xml 显示有失败）

    - 找不到 generate_failure_analysis.py → 跳过（脚本缺失不应阻塞主流程）
    - 脚本本身崩溃 → 仅打印 [WARN]，不改 execute_tests.py 退出码
    """
    report_xml = output_dir / "report.xml"
    if not report_xml.exists():
        return

    # 先扫 JUnit XML 看有没有失败
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(report_xml)
        root = tree.getroot()
        failures = sum(int(ts.attrib.get("failures", "0")) for ts in root.iter("testsuite"))
        errors = sum(int(ts.attrib.get("errors", "0")) for ts in root.iter("testsuite"))
        if failures == 0 and errors == 0:
            return
    except Exception:
        # XML 解析失败 → 仍然尝试调脚本，让脚本自己报错
        pass

    script = Path(__file__).parent / "generate_failure_analysis.py"
    if not script.exists():
        return

    # 构造执行概述（写到报告头部）
    summary_parts = []
    if args.priority or args.tags or args.marker_expr:
        m_expr = build_marker_expression(args.tags, args.modules, args.priority, args.marker_expr)
        if m_expr:
            summary_parts.append(m_expr)
    if args.browser:
        summary_parts.append("+".join(args.browser))
    summary_parts.append("headless" if args.headless else "headed")
    exec_summary = " · ".join(summary_parts) if summary_parts else "(未指定)"

    cmd = [
        sys.executable,
        str(script),
        "--junit-xml", str(report_xml),
        "--artifacts-dir", str(output_dir / "artifacts"),
        "--output-dir", str(output_dir),
        "--execution-summary", exec_summary,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode not in (0,):
            print(f"[WARN] generate_failure_analysis.py 退出码 {result.returncode}", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] failure_analysis 生成失败: {e}", file=sys.stderr)
```

### Step 4: 端到端验证（在 shop-lab-ui-test 里跑一次）

⚠️ **前置条件检查**：先确认 shop-lab-ui-test 有可用的 dev server / base-url。如果没有（或环境不可用），可降级为**静态 smoke test**：用一个已有的 `test-results/report.xml` 直接调 `generate_failure_analysis.py` 验证子脚本工作正常。

如 shop-lab-ui-test 可跑：

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
rm -rf test-results
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
    -m "P0 and run_smoke" \
    --browser chromium \
    --base-url=http://localhost:3000 \
    --output-dir ./test-results
ls test-results/
head -40 test-results/failure_analysis.md 2>/dev/null || echo "failure_analysis.md 未生成（全过）"
```

Expected: 执行完测试后自动生成 failure_analysis.md（若有失败）；日志里能看到生成脚本的输出

### Step 5: 验证 `--no-failure-analysis` 开关

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
rm -rf test-results
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
    -m "P0 and run_smoke" \
    --browser chromium \
    --base-url=http://localhost:3000 \
    --output-dir ./test-results \
    --no-failure-analysis
ls test-results/failure_analysis.md 2>&1 || echo "OK: --no-failure-analysis 生效，未生成 failure_analysis.md"
```

Expected: 不生成 failure_analysis.md

### Step 6: 静态 smoke test（不依赖 shop-lab-ui-test 环境）

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
# 用已有 report.xml 直接验证子脚本
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py \
    --junit-xml test-results/report.xml \
    --artifacts-dir test-results/artifacts \
    --output-dir test-results \
    --execution-summary "smoke test"
ls test-results/failure_analysis.md && echo "OK"
```

### Step 7: 「保存文件即完成」（非 git repo）

不执行 `git add` / `git commit`。完成编辑后直接进入自检。

## Self-Review Checklist

完成后，请在 report 里确认以下各项：

- [ ] `parse_args` 末尾追加了 `--no-failure-analysis`（`dest="no_failure_analysis"`, `action="store_true"`）
- [ ] `main` 函数末尾追加了对 `_maybe_generate_failure_analysis` 的条件调用
- [ ] 条件调用包含三个守卫：`not args.no_failure_analysis` / `not args.dry_run` / `not args.list_only`
- [ ] `_maybe_generate_failure_analysis` 函数定义放在 `if __name__ == "__main__":` 之前
- [ ] 函数先扫 JUnit XML 的 `failures` 和 `errors` 总和，都为 0 时直接 return
- [ ] 脚本缺失时不抛异常，静默 return
- [ ] 子脚本崩溃时只打印 `[WARN]`，不改 `execute_tests.py` 的退出码
- [ ] 子脚本的 stdout/stderr 都透传到 stderr（不污染 pytest stdout 报告）
- [ ] 端到端验证：`failure_analysis.md` 在有失败时自动生成（或静态 smoke test 通过）
- [ ] `--no-failure-analysis` 开关生效

## Deviations 处理原则

若 plan 代码无法直接套用（如变量名不一致 / `build_marker_expression` 签名不同 / `sys` 或 `subprocess` 未导入），以**让功能跑通**为最高优先级：

1. 优先按 plan 代码改，必要时修正周围的导入 / 变量名
2. 任何偏差在 report 的 Deviations 节说明原因 + 论证为何不破坏测试合约

## Report 模板

写一份 `.sdd/task-11-report.md`，包含：
- Status: DONE / DONE_WITH_CONCERNS / BLOCKED
- What I Implemented（改了哪些函数，加了什么参数）
- TDD/Validation Evidence（终端命令 + 输出片段）
- Files Changed
- Self-Review Findings（逐项 ✅/❌）
- Deviations（若无写 "None"）
- Concerns（生产环境的潜在风险）
