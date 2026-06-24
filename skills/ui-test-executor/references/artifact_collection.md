# Artifact 采集机制

## 概览

ui-test-executor 的 artifact 采集分两层：

| 层 | 提供者 | 时机 | 内容 |
|----|--------|------|------|
| L1 | pytest-playwright 原生 | 用例执行期 | 截图、录屏、Trace（基于 `--screenshot` / `--video` / `--trace` 标志） |
| L2 | conftest hook（自定义）| 失败时 | 全页截图、DOM 快照、console 日志、网络请求摘要 |

L1 是默认开启的；L2 需要把 `assets/conftest_template.py` 合并到项目 conftest。

## pytest-playwright 原生采集

### 命令行标志

```bash
--screenshot=off|on|only-on-failure   # 默认 off
--video=off|on|retain-on-failure      # 默认 off
--trace=off|on|retain-on-failure      # 默认 off
```

### 三种模式语义

| 模式 | 行为 |
|------|------|
| `off` | 不采集 |
| `on` | 每个用例都采集（无论通过失败） |
| `retain-on-failure` | 全部采集，但通过用例的 artifact 在结束时删除 |

### 推荐配置

| 场景 | 推荐 |
|------|------|
| 本地开发 | `--screenshot only-on-failure --video off --trace off` |
| CI 标准 | `--screenshot only-on-failure --video retain-on-failure --trace retain-on-failure` |
| 调试单个用例 | `--screenshot on --video on --trace on --no-headless` |
| 性能基线 | `--screenshot off --video off --trace off` |

### 输出目录

```
test-results/pytest-output/
└── <test-method-token>/
    ├── test-failed-1.png         # 失败截图（按失败顺序编号）
    ├── video.webm                 # 录屏
    └── trace.zip                  # Trace 归档
```

**test-method-token 命名规则：**

```
tests/auth/test_login.py::TestLogin::test_invalid_password
→ test-login-test-invalid-password-mod-N-chromium
```

- 文件路径中的 `/` → `-`
- `::` → `-`
- `[param]` → `-mod-N`（参数化）
- 末尾追加 `-<worker>-<browser>`

## conftest 自定义 hook 采集

### 触发时机

`pytest_runtest_makereport` 在 `report.when == "call"` 且 `report.failed == True` 时触发。

### 采集内容

| Artifact | 路径 | 用途 |
|---------|------|------|
| 视口截图 | `artifacts/screenshots/{nodeid}-viewport.png` | 当前可见区域 |
| 全页截图 | `artifacts/screenshots/{nodeid}-fullpage.png` | 整个页面（含滚动区域） |
| HTML 源码 | `artifacts/page-source/{nodeid}.html` | 失败时 DOM 结构 |
| Console 日志 | `artifacts/console-logs/{nodeid}.log` | 页面 URL、title、JS 异常 |
| Trace | pytest-playwright 原生保留 | 完整操作时间线 |

### 命名归一化

`_sanitize_filename(nodeid)` 把：

```
tests/auth/test_login.py::TestLogin::test_invalid_password[密码错误]
→ tests-auth-test-login-TestLogin-test-invalid-password-密码错误
```

实际进一步去除非 ASCII 字符，得到：

```
tests-auth-test-login-testlogin-test-invalid-password-mod-0
```

## Artifact 关联（report 生成阶段）

`generate_report.py::associate_artifacts()` 在生成报告时：

1. 扫描 `artifacts/` 目录所有文件
2. 对每个测试用例，根据 `normalize_method_token()` 生成方法 token
3. 在文件名中匹配 token，归类到 `screenshots/videos/traces/har/page_source/console_logs`

匹配规则：**双向包含** — token 在文件名中，或文件名中的某段在 token 中。

## Trace 查看

```bash
# 本地查看
npx playwright show-trace test-results/artifacts/traces/xxx.zip

# 在线查看（上传到 trace.playwright.dev）
npx playwright show-trace --host=0.0.0.0 test-results/.../trace.zip
```

Trace 提供：

- 完整操作时间线（每个 Playwright API 调用）
- 每个 action 前后的 DOM 快照
- 网络请求瀑布图
- Console 输出
- 录屏（与操作同步）

## 录屏格式

pytest-playwright 默认输出 `.webm`（VP9 编码）。CI 系统如需 MP4：

```python
# tests/conftest.py
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "record_video_dir": "test-results/artifacts/videos",
        "record_video_size": {"width": 1280, "height": 720},
    }
```

后续可用 ffmpeg 转码：

```bash
for f in test-results/artifacts/videos/*.webm; do
  ffmpeg -i "$f" "${f%.webm}.mp4"
done
```

## HAR 网络抓包

```bash
$PYTHON execute_tests.py tests/ --browser chromium
# 在 conftest 中开启:
@pytest.fixture
def context(context):
    context.route_from_har("test-results/artifacts/har/request.har")
    yield context
```

HAR 文件包含所有网络请求/响应，可拖入 Chrome DevTools 的 Network 面板查看。

## Artifact 保留策略

### 通过的用例

- pytest-playwright `retain-on-failure` 模式：自动删除
- conftest 自定义 hook：只对失败用例采集，通过的用例不产生额外文件

### 失败的用例

- 全部保留
- 报告生成器扫描时归类到对应用例
- 在 `report.json` 的 `failures[i].artifacts` 字段引用路径

### 长期保留

建议 CI 系统配置 artifact 保留期：

| 用例结果 | 保留期 |
|---------|--------|
| 全部通过 | 7 天 |
| 有失败 | 90 天（供回归分析） |
| Release build | 永久（标记版本号） |

## 排查采集失败

### 症状

测试失败但 `artifacts/screenshots/` 中无对应文件。

### 排查

1. **conftest 集成完整？** 检查 `pytest_runtest_makereport` hook 是否注册成功
   ```bash
   pytest --co tests/ -q | head
   # 应看到 ui-test-executor 增强选项注册日志
   ```

2. **artifact_root 路径权限？**
   ```bash
   ls -ld ./test-results/artifacts/screenshots/
   # 应可写
   ```

3. **page fixture 是否注入？** 自定义 hook 通过 `item.funcargs.get("page")` 取，如果测试没用 `page` fixture（用了别的名字如 `browser`），不会触发。

4. **是否在 setup/teardown 失败？** `report.when == "call"` 才采集，setup 失败（`when == "setup"`）不触发。

## 性能影响

### 录屏开销

录制视频会让单用例耗时增加 **30-50%**。CI 推荐用 `retain-on-failure`，本地调试用 `on`。

### Trace 开销

Trace 录制开销约 **10-20%**，但解析非常快（局部 IO）。

### 截图开销

每次截图约 100-300ms（视页面复杂度）。失败截图 1-2 次可接受，避免在用例内部循环截图。

### 综合推荐

| 场景 | screenshot | video | trace |
|------|-----------|-------|-------|
| 本地快速验证 | off | off | off |
| 本地调试 | only-on-failure | on | on |
| CI 回归 | only-on-failure | retain-on-failure | retain-on-failure |
| CI 冒烟 | only-on-failure | off | off |
| Release build | on | on | on |
