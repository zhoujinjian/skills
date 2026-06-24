### Task 10: 注入 PYTEST_RUN_PHASE 环境变量

**Files:**
- Modify: `scripts/execute_tests.py`（`run_pytest` 传 env，`main` 注入 phase）

- [ ] **Step 1: 修改 `run_pytest` 让它接收 phase 并注入环境变量**

打开 `scripts/execute_tests.py`，找到 `def run_pytest(pytest_args, cwd, dry_run=False, label="MAIN")` 函数签名（约 397 行），改为：

```python
def run_pytest(pytest_args: list[str], cwd: str, dry_run: bool = False, label: str = "MAIN", phase: str = "main") -> int:
    """执行 pytest 命令，实时流式输出

    label 用于在日志中区分"前置阶段"和"主测试"（如 --pre-run vs 主筛选集）
    phase 注入到子进程环境变量 PYTEST_RUN_PHASE，供 conftest 写 sidecar 时区分阶段
    """
```

在 `subprocess.Popen` 调用（约 422 行）前加：

```python
    env = os.environ.copy()
    env["PYTEST_RUN_PHASE"] = phase
```

然后修改 `subprocess.Popen(cmd, cwd=cwd, stdout=..., stderr=..., text=True, bufsize=1, universal_newlines=True)` 调用，追加 `env=env`：

```python
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env,
        )
```

- [ ] **Step 2: 修改 `main` 调用处**

找到 main 函数末尾（约 711-718 行）：

```python
    if pre_pytest_args:
        pre_exit = run_pytest(pre_pytest_args, cwd=cwd, label="PRE-RUN")
        if pre_exit not in (0, 1):
            # 0=全过 / 1=有失败（仍允许继续主测试）/ 其他=异常
            print(f"[PRE-RUN] 前置阶段异常退出（exit={pre_exit}），终止后续执行", file=sys.stderr)
            return pre_exit

    main_exit = run_pytest(main_pytest_args, cwd=cwd, label="MAIN")
    return main_exit
```

改为：

```python
    if pre_pytest_args:
        pre_exit = run_pytest(pre_pytest_args, cwd=cwd, label="PRE-RUN", phase="pre-run")
        if pre_exit not in (0, 1):
            print(f"[PRE-RUN] 前置阶段异常退出（exit={pre_exit}），终止后续执行", file=sys.stderr)
            return pre_exit

    main_exit = run_pytest(main_pytest_args, cwd=cwd, label="MAIN", phase="main")
    return main_exit
```

- [ ] **Step 3: 手动验证 phase 注入生效**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
python3 -c "
import subprocess, os
env = os.environ.copy()
env['PYTEST_RUN_PHASE'] = 'test'
result = subprocess.run(
    ['python3', '-c', 'import os; print(\"PHASE=\", os.environ.get(\"PYTEST_RUN_PHASE\"))'],
    env=env, capture_output=True, text=True
)
print(result.stdout)
"
```
Expected: 输出 `PHASE= test`（确认 env 传递机制）

- [ ] **Step 4: 跑 execute_tests 的现有 evals 看无回归**

```bash
# 用 --dry-run 不实际跑测试，只看命令构建
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
    --priority P0 --tags run_smoke --browser chromium --base-url=http://localhost:3000 \
    --dry-run
```
Expected: 正常输出构建的命令，无 traceback

- [ ] **Step 5: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git add scripts/execute_tests.py
git commit -m "feat(failure-analysis): inject PYTEST_RUN_PHASE env to subprocess for conftest sidecar"
```

---

