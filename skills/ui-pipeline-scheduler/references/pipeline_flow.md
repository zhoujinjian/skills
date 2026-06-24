# ui-pipeline-scheduler 详细流程图

> SKILL.md 的 Step 0-5 简化版流程，本文件提供详细分支与产物变化。

## 完整流程图（含重试循环 + 失败兜底）

```
START
  │
  ▼
Step 0: 定位 Python + 检查项目结构
  │     产物：PYTHON=<解释器路径>
  │     校验：tests/、pages/、pages.yaml、tests/conftest.py
  │
  ▼
Step 1: ui-test-executor 首轮执行（round=0）
  │     命令：execute_tests.py tests/ --priority --tags ... --output-dir ./test-results --allure
  │     产物：report.xml, report.json, browser_env.json, artifacts/, failure_analysis.md
  │     备份：cp report.xml report-round-0.xml
  │     解析：first_round_failures = failures + errors
  │
  ├── first_round_failures == 0 ──────────────────────────────┐
  │                                                           │
  │   跳过 Step 2-4                                            │
  │                                                           │
  ▼                                                           │
Step 2: ui-failure-diagnoser 诊断（仅 failures > 0 时）        │
  │     命令：diagnose.py --junit-xml --artifacts-dir          │
  │              --project-dir --pages-yaml --verify           │
  │     产物：ui_repair_report.md, pages/**/*.py（修复）       │
  │     解析：fixed_this_round                                 │
  │                                                           │
  ├── fixed_this_round == 0 ── 修复无效熔断 ──────────────────┤
  │                                                           │
  ▼                                                           │
Step 3: ui-test-executor 重试执行（只跑失败用例）              │
  │     1. Python one-liner 提取失败 nodeid                    │
  │     2. execute_tests.py tests/ -k "name1 or name2 ..."     │
  │     3. 备份：cp report.xml report-round-N.xml              │
  │     解析：current_failures = failures + errors             │
  │                                                           │
  ├── current_failures == 0 ── 全过跳出 ──────────────────────┤
  │                                                           │
  ▼                                                           │
Step 4: 熔断判断                                               │
  │     条件：round >= max_retries                             │
  │     或   current_failures == 0                             │
  │     或   fixed_this_round == 0                             │
  │                                                           │
  ├── 未熔断 ── round += 1, 回 Step 2                          │
  │                                                           │
  ▼                                                           │
Step 4.5: 合并多轮 JUnit XML（仅发生过重试时触发）            │
  │     命令：merge_reports.py                                 │
  │              --base report-round-0.xml                    │
  │              --overlay report-round-1.xml [...]           │
  │              --output report.xml                          │
  │     规则：首轮完整 XML 为基底，重试轮按 (classname,name)   │
  │           覆盖同名用例，恢复完整 N 条用例最新状态          │
  │     产物：report.xml（被覆盖为完整版）                     │
  │                                                           │
  ▼                                                           │
Step 5: ui-report-generator 最终报告  ◀───────────────────────┘
  │     命令：generate_report.py --junit-xml（合并后）--exec-json
  │              --diagnose-md --artifacts-dir --browser-env-json
  │              --output ./test-results/ui_test_report.html --auto-allure
  │     产物：ui_test_report.html（含完整 N 条用例）
  │
  ▼
END: open ./test-results/ui_test_report.html
```

## 每轮产物变化

| 轮次 | report.xml 来源 | ui_repair_report.md | report-round-N.xml |
|------|----------------|---------------------|---------------------|
| round=0 | executor 首轮 | 不存在 | report-round-0.xml 备份 |
| round=1 | executor 重试1 | diagnoser 第1次产出 | report-round-1.xml 备份 |
| round=2 | executor 重试2 | diagnoser 第2次产出（覆盖） | report-round-2.xml 备份 |
| 最终 | 最后一轮的 xml | 最后一次 diagnoser 产出 | 全部留档 |

**report-generator 用的 xml**：始终是 `./test-results/report.xml`（已被最后一轮覆盖）。

## 失败兜底分支

### 分支 A：首轮全过

```
Step 1 → 跳过 Step 2-4.5 → Step 5
```

精简版 Step 5 命令（无 --diagnose-md，无需 merge_reports，首轮 report.xml 本身就完整）。

### 分支 B：达 max_retries 仍有失败

```
Step 1 → Step 2 → Step 3 → Step 4 (熔断) → Step 4.5 (合并) → Step 5
```

Step 5 用合并后的 report.xml；用户摘要标记 ⚠️ 修复失败用例；报告里这些用例显示「修复尝试 K 次，仍未通过」。

### 分支 C：diagnoser 修复无效（fixed_this_round == 0）

```
Step 1 → Step 2 → Step 3 → Step 4 (熔断) → Step 4.5 (合并) → Step 5
```

Step 3 仍会跑一次重试给 flaky 一次机会；Step 4 命中熔断条件 2（fixed==0）后跳出；Step 4.5 合并首轮 + 重试 XML 保证报告完整。

### 分支 D：diagnoser 异常（pages.yaml 缺失等）

```
Step 1 → Step 2 (异常) → Step 3 (用未修复脚本重试) → Step 4 → Step 4.5 → ...
```

记日志「诊断跳过：xxx」；进 Step 3 用原脚本重试（可能因 flaky 通过）。

## 关键时序约束

1. **Step 2 必须在 Step 1 之后**：依赖首轮 report.xml + artifacts
2. **Step 3 必须在 Step 2 之后**：依赖 diagnoser 修复的脚本（即使修复无效也走流程）
3. **Step 5 必须在所有循环结束后**：避免多轮报告互相覆盖
4. **Allure 服务在 Step 1 启动**（通过 executor 的 `--allure`），Step 5 直接 `--auto-allure` 复用

## 边界 case

### Case 1：用户 `--max-retries 0`

等价于「不重试，只执行 + 诊断 + 报告」：
```
Step 1 → Step 2 → Step 5（跳过 Step 3-4）
```

### Case 2：首轮执行异常（非测试失败）

executor 退出码非 0 且 report.xml 不存在或为空 → 立即终止，不进 Step 2。提示用户：
- 检查 Python 解释器
- 检查 tests/ 目录
- 检查 playwright 安装

### Case 3：重试时 `-k` 表达式过长

nodeid 含 `::`、`[]` 会让 `-k` 表达式超长。**对策**：提取时只取方法名（去参数化方括号），用方法名做 `-k` 子串匹配。

### Case 4：多浏览器矩阵的重试

首轮 `--browser chromium firefox` 跑出失败时，重试**保留多浏览器**（`-k` 筛选不指定浏览器，pytest-playwright 自动展开矩阵）。
