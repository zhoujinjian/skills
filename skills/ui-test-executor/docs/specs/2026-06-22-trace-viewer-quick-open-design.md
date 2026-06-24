# Trace Viewer 快捷打开 — 设计文档

**日期**: 2026-06-22
**Skill**: ui-test-executor
**状态**: 用户已批准，直接进 TDD 实现（跳过独立 plan 文档）

## 1. 目标

让用户在 Claude Code 里用自然语言（「打开最新 trace」「看看小米那条 trace」）直接调起 Playwright Trace Viewer，无需手敲 `playwright show-trace <path>` 长命令。

## 2. 非目标 (YAGNI)

- 不支持打开 video.webm（仅 trace.zip）。未来若要扩，重命名为 `open_artifact.py` 加 `--kind` 选项。
- 不支持 `--foreground`（前台阻塞）。CI 场景未来再考虑。
- 不支持批处理（一次开多个 trace）。
- 不做缓存/状态化。

## 3. 用户决策记录（brainstorming 阶段）

| 决策点 | 选择 |
|--------|------|
| 默认行为（无 query） | 打开最新一条失败的 trace（mtime 最新） |
| 触发方式 | 纯自然语言（扩展 SKILL.md 触发词），不新增 slash 命令 |
| trace 缺失时 | 报错 + 提示可能原因，不自动重跑 |
| 查询语法 | 三种：最新 / 关键词（nodeid 子串）/ 全路径 |
| 启动方式 | 后台（subprocess.Popen + start_new_session=True） |
| 项目发现 | `--artifacts-dir` 参数显式传，由 Claude 决定（与 `generate_failure_analysis.py` 一致） |

## 4. 架构

```
用户: "打开小米那条 trace"
   │
   ▼
Claude (Claude Code)
   ├─ SKILL.md 触发词命中
   ├─ 从上下文确定 --artifacts-dir
   └─ Bash: python3 scripts/open_trace.py 小米 --artifacts-dir <path>
   │
   ▼
scripts/open_trace.py
   ├─ 扫描 <artifacts-dir>/pytest-raw/*/trace.zip
   ├─ 按 query 分支匹配（latest / keyword / path）
   ├─ 校验唯一性
   └─ subprocess.Popen([playwright, show-trace, <path>], start_new_session=True)
   │
   ▼
Playwright Trace Viewer 窗口打开（独立后台进程）
Claude 立即拿到控制权
```

**单一职责：** 新增 `scripts/open_trace.py`；SKILL.md 加触发词 + Step 7.5 说明；新增 `references/trace_viewer_guide.md`。

**复用既有代码：** `_sanitize_nodeid_to_slug`（在 `assets/conftest_template.py`），import 进来用于中文转义容错。

## 5. CLI 接口

```bash
python3 scripts/open_trace.py [query] [--artifacts-dir <path>] [--dry-run]
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `query` (位置) | `"latest"` | 三种形式：`latest` / 关键词 / 文件路径 |
| `--artifacts-dir` | `./test-results/artifacts` | artifact 根目录 |
| `--dry-run` | False | 只打印会启动的命令，不 spawn（用于测试/调试） |

退出码：
- `0`：成功 spawn（或 dry-run）
- `1`：discovery/matching 错误（找不到、多候选等）
- `2`：环境错误（playwright 未装）
- `3`：spawn 异常

## 6. Discovery + Matching 算法

```
build_candidates(artifacts_dir)
  → 扫描 <artifacts-dir>/pytest-raw/*/trace.zip
  → 返回 [{"path": Path, "mtime": float, "nodeid_hint": str}, ...]

match(query, candidates)
  ├─ query in ("", "latest", "最新")
  │     → sort by mtime desc, then by name asc; return candidates[0]
  ├─ query 是已存在的文件路径
  │     → 校验 .zip 后缀；return that path
  └─ query 其他字符串
        → 对每个候选的 nodeid_hint 做：query in nodeid_hint
          OR _sanitize_nodeid_to_slug(query) in nodeid_hint
        → 命中 0：error
        → 命中 1：return
        → 命中 ≥2：error + 列表
```

**nodeid_hint 来源：** 候选 trace.zip 的父目录名（如 `tests-product-...-chromium-u5c0f-u7c73`）。这是 pytest-playwright 的目录命名，足够用于子串匹配。

**mtime tiebreaker：** mtime 相同时按文件名字典序，保证确定性（测试可重现）。

## 7. 启动 Trace Viewer

```python
log_path = artifacts_dir / "trace-viewer.log"
log_file = log_path.open("a")  # append 模式，多次启动的历史保留

subprocess.Popen(
    [sys.executable, "-m", "playwright", "show-trace", str(trace_path)],
    stdout=log_file,
    stderr=log_file,
    start_new_session=True,  # 关键：detach，父进程退出后子进程继续
)
# 不 wait()，立即返回
```

- stdout/stderr 重定向到 `<artifacts-dir>/trace-viewer.log`，方便事后排查
- `start_new_session=True` 让子进程脱离父进程的 process group，Claude 的 Bash 调用立即返回
- spawn 成功后即使 viewer 后续崩溃，脚本退出码仍为 0（不在职责内）

## 8. 错误处理矩阵

| 场景 | stderr 输出 | 退出码 |
|------|------------|--------|
| 扫描 0 个 trace.zip | `[ERROR] 未找到任何 trace.zip` + 原因提示（3 条） + 目录确认 | 1 |
| 关键词命中 0 条 | `[ERROR] 未找到含 '<query>' 的 trace` + 所有候选列表 | 1 |
| 关键词命中 ≥2 条 | `[ERROR] 多条 trace 匹配 '<query>'` + 列表 + 精确指定提示 | 1 |
| 文件路径不存在 | `[ERROR] 路径不存在: <path>` | 1 |
| 文件路径非 .zip | `[ERROR] 不是 trace 文件（需 .zip 后缀）: <path>` | 1 |
| playwright 未装 | `[ERROR] playwright 未安装` + 安装命令 | 2 |
| spawn 异常 | `[ERROR] 启动失败: <e>` | 3 |

**缺失 trace 的提示文案（场景 1）：**
```
[ERROR] 未找到任何 trace.zip in <artifacts-dir>/pytest-raw/

可能原因：
  - 用例通过了（pytest-playwright --tracing=retain-on-failure 不会保留通过用例的 trace）
  - 项目 conftest 未集成 --tracing 选项
  - 用例在 setup 阶段失败（page 未初始化，pytest-playwright 不会生成 trace）

建议：
  确认目录存在: ls <artifacts-dir>/pytest-raw/
  重跑并强制 trace: execute_tests.py ... --trace on
```

## 9. 测试策略

**单元测试（`evals/trace_viewer/`，mock subprocess.Popen，不依赖真实 playwright）：**

| 文件 | 覆盖 |
|------|------|
| `test_discovery.py` | 扫描多目录 / 空目录 / 嵌套 / 非 .zip 文件被忽略 |
| `test_match_latest.py` | mtime 倒序 / 相同 mtime tiebreaker / 空候选列表 |
| `test_match_keyword.py` | 字面命中 / slug 容错命中（小米↔u5c0f-u7c73）/ 0 命中 / 多命中 |
| `test_match_path.py` | 绝对路径 / 相对路径 / 不存在 / 非 .zip |
| `test_error_messages.py` | 每个错误场景的 stderr 文案 |
| `test_dry_run.py` | `--dry-run` 不 spawn / print 正确命令 |
| `test_spawn.py` | Popen 调用参数正确 / start_new_session=True / stdout 重定向 |

**手动 smoke test（shop-lab-ui-test 已有 3 个 trace.zip）：**
- `python3 open_trace.py` → 最新
- `python3 open_trace.py 小米` → 中文转义命中
- `python3 open_trace.py foo` → 0 命中错误
- `python3 open_trace.py search` → 多命中错误
- `--dry-run` 验证不 spawn

## 10. SKILL.md 集成

**触发词新增（"触发场景" 段）：**
- "打开 trace" / "看 trace" / "show trace" / "open trace"
- "最新 trace" / "trace viewer"

**Step 7.5 新增（Step 7 之后）：**
```markdown
### Step 7.5：按需打开 Trace Viewer

当用户在执行后问「打开 trace」「看看最新失败的 trace」「打开小米那条 trace」时，调：

python3 scripts/open_trace.py [query] --artifacts-dir <test-results/artifacts>

`query` 三种形式：
- 省略 / "latest"：打开最新一条
- 关键词（如 "小米"、"test_search"）：按 nodeid 子串匹配
- 全路径：直接用

脚本后台启动 Trace Viewer 并立即返回。详见 references/trace_viewer_guide.md。
```

**参考文件索引表新增：**
- `scripts/open_trace.py` → Step 7.5

## 11. references/trace_viewer_guide.md 大纲

- 何时用（失败后排障，比看 screenshot 更细粒度）
- 如何触发（自然语言 / 直接调脚本）
- 三种查询示例 + 期望输出
- 后台启动说明（关闭窗口即退出进程，Claude 立即返回）
- 故障排查：trace 没生成 / playwright 未装 / 中文匹配 / 多候选消歧

## 12. 实施顺序（TDD）

1. 任务 1：写 `evals/trace_viewer/test_discovery.py` + 实现 `build_candidates` → RED → GREEN
2. 任务 2：写 `test_match_latest.py` + 实现 `match_latest`
3. 任务 3：写 `test_match_keyword.py` + 实现 `match_keyword`（含 slug 容错）
4. 任务 4：写 `test_match_path.py` + 实现 `match_path`
5. 任务 5：写 `test_error_messages.py` + 实现错误文案
6. 任务 6：写 `test_dry_run.py` + `test_spawn.py` + 实现 CLI main + spawn
7. 任务 7：shop-lab 手动 smoke test
8. 任务 8：SKILL.md 触发词 + Step 7.5
9. 任务 9：references/trace_viewer_guide.md

## 13. 相关文档

- 失败分析报告 spec：`2026-06-21-failure-analysis-report-design.md`
- 主流程：`SKILL.md` Step 7.5
- 复用代码：`assets/conftest_template.py::_sanitize_nodeid_to_slug`
