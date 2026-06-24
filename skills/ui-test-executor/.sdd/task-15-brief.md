### Task 15: 端到端验证（故意失败的测试 + 完整流程跑通）

**Files:**
- 临时修改（验证完恢复）：`/Users/zhoujinjian/ai_project/shop-lab-ui-test/tests/product/test_search.py`

- [ ] **Step 1: 备份并故意改坏一个断言**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
cp tests/product/test_search.py tests/product/test_search.py.bak
# 把「手机」关键字断言改成必然失败的（手机本来是过的，改成要求返回 999 个）
sed -i.bak2 's/assert count > 0, f"搜索/assert count > 999, f"搜索/' tests/product/test_search.py
# 复原 sed 没成功的话手动改；确认改了
grep -n "assert count" tests/product/test_search.py
```
Expected: 看到 `assert count > 999, f"搜索..."`

- [ ] **Step 2: 完整流程跑通**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
rm -rf test-results
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/execute_tests.py tests/ \
    -m "P0 and run_smoke" \
    --browser chromium \
    --base-url=http://localhost:3000 \
    --output-dir ./test-results
```
Expected: 测试跑完，stderr 显示 `[INFO] 检测到 1 个失败用例` 和 `[OK] 已生成 .../failure_analysis.md`

- [ ] **Step 3: 检查 failure_analysis.md 内容**

```bash
cat test-results/failure_analysis.md | head -100
```
Expected 检查项：
- 顶部总览含执行概述
- 每条失败用例有 `## ❌` 标题
- 判定规则段含 docstring 提取
- 断言原文含 `assert count > 999`
- 预期 vs 实际含 `assert 0 > 999` 或类似 introspection
- 截图路径指向实际存在的文件
- Trace 路径含 `playwright show-trace` 命令

- [ ] **Step 4: 验证 artifact 路径真实存在**

```bash
ls test-results/artifacts/failure-context/
ls test-results/artifacts/screenshots/ | head -5
find test-results/artifacts/pytest-raw -name "trace.zip" | head -5
```
Expected: sidecar JSON / screenshots / trace.zip 文件都真实存在，且路径与 MD 报告里写的一致

- [ ] **Step 5: 恢复测试文件**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
mv tests/product/test_search.py.bak tests/product/test_search.py
rm -f tests/product/test_search.py.bak2
grep -n "assert count" tests/product/test_search.py
```
Expected: 断言恢复为 `assert count > 0`

- [ ] **Step 6: Commit（这次 commit 是 skill 自身的最终汇总，端到端通过）**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git log --oneline | head -15  # 看本计划的所有 commit 是否齐全
```
Expected: 看到 Task 1-14 的 commit 序列

无需新 commit（本 Task 只做端到端验证）。

