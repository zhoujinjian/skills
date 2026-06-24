# Trace Viewer 快捷打开使用指南

**用途：** 在 Claude Code 里用自然语言或快捷命令调起 Playwright Trace Viewer，免去手敲 `playwright show-trace <长路径>`。

**对应脚本：** `scripts/open_trace.py`（SKILL.md Step 7.5）

---

## 1. 何时用

失败用例排障时，Trace Viewer 比看 screenshot 更细粒度：
- 逐动作回放（每次 click / fill / navigate 前后状态）
- DOM 快照 + 网络 + console 同步时间轴
- 鼠标悬停看每步 locator 高亮

通过用例没有 trace（pytest-playwright `--tracing=retain-on-failure` 只保留失败用例的 trace）。

---

## 2. 如何触发

**方式一：自然语言**（推荐）

在 Claude Code 里直接说：
- "打开最新 trace"
- "看看小米那条 trace"
- "show trace" / "open trace"
- "trace viewer"

Claude 会命中 SKILL.md 触发词，自动从上下文确定 `--artifacts-dir`，调用脚本。

**方式二：直接调脚本**

```bash
python3 scripts/open_trace.py [query] --artifacts-dir <path>
```

---

## 3. 三种查询形式

| query 形式 | 示例 | 行为 |
|------------|------|------|
| 省略 / `"latest"` / `"最新"` | `open_trace.py` | 打开 mtime 最新的一条 |
| 关键词 | `open_trace.py 小米` / `open_trace.py login` | 按 nodeid_hint 子串匹配（大小写不敏感），中文自动转 slug 容错 |
| 文件路径 | `open_trace.py /abs/path/to/trace.zip` | 直接用，必须 `.zip` 后缀 |

### 3.1 关键词中文匹配原理

pytest-playwright 把 nodeid 里的非 ASCII 字符转成 `uXXXX-uXXXX` 形式做目录名：
- `小米` → `u5c0f-u7c73`
- 目录名如 `tests-product-test_search-chromium-u5c0f-u7c73`

所以脚本里对每个候选同时检查：
- `query.lower() in nodeid_hint.lower()`（字面子串）
- `_sanitize_nodeid_to_slug(query) in nodeid_hint`（slug 子串，覆盖中文）

用户可以照常输入中文，脚本自动转。

---

## 4. 期望输出

### 成功（后台启动）

```
[OK] Trace Viewer 已后台启动: /path/to/trace.zip
     日志: /path/to/trace-viewer.log
```

Claude 立即拿到控制权，Trace Viewer 在独立窗口运行。关闭窗口即退出进程。

### Dry-run

```
[DRY-RUN] 会启动:
  /usr/local/opt/python@3.13/bin/python3.13 -m playwright show-trace /path/to/trace.zip
  stdout/stderr → /path/to/trace-viewer.log
```

---

## 5. 后台启动说明

- `subprocess.Popen(..., start_new_session=True)` 让子进程脱离父进程的 process group
- Claude 的 Bash 调用立即返回（不 wait）
- stdout/stderr append 到 `<artifacts-dir>/trace-viewer.log`（多次启动的历史保留）
- spawn 成功后即使 viewer 后续崩溃，脚本退出码仍为 0（不在职责内）

---

## 6. 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 spawn（或 dry-run） |
| 1 | discovery/matching 错误（找不到 trace、多候选等） |
| 2 | 环境错误（playwright 未装） |
| 3 | spawn 异常 |

---

## 7. 故障排查

### 7.1 "未找到任何 trace.zip"

```
[ERROR] 未找到任何 trace.zip in <artifacts-dir>/pytest-raw/

可能原因:
  - 用例通过了（pytest-playwright --tracing=retain-on-failure 不会保留通过用例的 trace）
  - 项目 conftest 未集成 --tracing 选项
  - 用例在 setup 阶段失败（page 未初始化，pytest-playwright 不会生成 trace）

建议:
  确认目录存在: ls <artifacts-dir>/pytest-raw/
  重跑并强制 trace: execute_tests.py ... --trace on
```

**处理：**
1. `ls <artifacts-dir>/pytest-raw/` 确认目录是否空
2. 如果空，重跑测试并加 `--trace on`（而不是 `retain-on-failure`），强制保留所有 trace

### 7.2 "多条 trace 匹配 '<query>'"

```
[ERROR] 多条 trace 匹配 'login'，请精确指定。命中:
  - tests-login-test-login-valid
  - tests-login-test-login-invalid
```

**处理：** 换更精确的关键词（如 `login-valid`），或直接用文件路径。

### 7.3 "playwright 未安装"

```
[ERROR] playwright 未安装
  安装: pip install playwright && python -m playwright install chromium
```

**处理：** 按提示装。注意检查 Claude 当前用的 Python 解释器（`sys.executable`），可能不是项目 venv。

### 7.4 中文匹配失败

如果用户输入中文关键词匹配不到：
1. `ls <artifacts-dir>/pytest-raw/` 看实际目录名里的 `uXXXX` 序列
2. 让用户换个唯一的关键词（如完整 test 名）
3. 或直接传 trace.zip 全路径

### 7.5 候选 mtime 相同时的选择

`match_latest` 在 mtime 相同时按 `path.name` 字典序取最小，保证确定性（同样输入永远同样输出）。如果 CI 环境里多个 trace.zip mtime 完全一致，结果可能不是「直觉上最新」的——这是已知限制，建议加毫秒级时间戳区分。

---

## 8. 设计参考

详见 `docs/specs/2026-06-22-trace-viewer-quick-open-design.md`：
- discovery/matching 算法
- 错误处理矩阵
- 测试策略
- 实施顺序
