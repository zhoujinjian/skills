# 失败追溯增强配置指南

## 目录

1. [自动截图](#自动截图)
2. [Trace 录制](#trace-录制)
3. [视频录制](#视频录制)
4. [网络请求日志](#网络请求日志)
5. [控制台日志捕获](#控制台日志捕获)
6. [完整 conftest.py 模板](#完整-conftestpy-模板)

---

## 自动截图

### 方案 1：pytest hook（推荐）

```python
# tests/conftest.py
import pytest
import os
from datetime import datetime


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    # 仅在测试调用阶段失败时截图
    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page and not page.is_closed():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_dir = "screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            path = os.path.join(screenshot_dir, f"{item.name}_{timestamp}.png")
            try:
                page.screenshot(path=path, full_page=True)
                print(f"\n  失败截图: {path}")
            except Exception as e:
                print(f"\n  截图失败: {e}")
```

### 方案 2：Playwright 内置配置

```python
# pytest.ini 或 conftest.py
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "screenshot": "only-on-failure",  # 失败时自动截图
    }
```

---

## Trace 录制

### 方案 1：Playwright 配置

```python
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "trace": "retain-on-failure",  # 失败时保留 trace
    }
```

### 方案 2：手动控制 Trace

```python
@pytest.fixture
def traced_page(page):
    """每个测试自动录制 Trace"""
    context = page.context
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    yield page
    # 测试结束后停止并保存
    import os
    trace_dir = "traces"
    os.makedirs(trace_dir, exist_ok=True)

    # 获取测试结果
    trace_path = os.path.join(trace_dir, f"{os.getenv('PYTEST_CURRENT_TEST', 'unknown')}.zip")
    context.tracing.stop(path=trace_path)
```

### 查看 Trace

```bash
playwright show-trace traces/test_login.zip
```

---

## 视频录制

```python
@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "record_video": True,  # 或 "retain-on-failure"
        "record_video_dir": "reports/videos/",
    }
```

---

## 网络请求日志

### 方案 1：自动记录失败测试的请求

```python
@pytest.fixture(autouse=True)
def log_network_on_failure(page, request):
    """失败时自动记录网络请求"""
    network_logs = []

    def on_response(response):
        entry = f"[{response.status}] {response.request.method} {response.url}"
        if response.status >= 400:
            entry += f" ← ERROR"
        network_logs.append(entry)

    page.on("response", on_response)
    yield

    # 如果测试失败，写入日志文件
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        log_dir = "reports/network"
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"{request.node.name}.log")
        with open(log_path, "w") as f:
            f.write(f"# 网络请求日志 - {request.node.name}\n")
            f.write(f"# 时间: {datetime.now()}\n\n")
            f.write("\n".join(network_logs))
```

### 方案 2：全量请求监控

```python
class NetworkMonitor:
    """网络请求监控器"""

    def __init__(self, page: Page):
        self.page = page
        self.requests = []
        self.failed_requests = []

    def start(self):
        self.page.on("request", self._on_request)
        self.page.on("response", self._on_response)
        self.page.on("requestfailed", self._on_failed)

    def _on_request(self, request):
        self.requests.append({
            "method": request.method,
            "url": request.url,
            "time": datetime.now().isoformat(),
        })

    def _on_response(self, response):
        if response.status >= 400:
            self.failed_requests.append({
                "url": response.url,
                "status": response.status,
                "body": response.text()[:500],
            })

    def _on_failed(self, request):
        self.failed_requests.append({
            "url": request.url,
            "error": request.failure,
        })

    def get_summary(self) -> str:
        lines = [
            f"总请求数: {len(self.requests)}",
            f"失败请求: {len(self.failed_requests)}",
        ]
        for req in self.failed_requests:
            lines.append(f"  ✗ {req.get('status', 'FAIL')} {req['url']}")
        return "\n".join(lines)
```

---

## 控制台日志捕获

```python
@pytest.fixture(autouse=True)
def capture_console(page, request):
    """捕获浏览器控制台日志"""
    console_logs = []
    console_errors = []

    page.on("console", lambda msg: (
        console_errors.append(msg.text) if msg.type == "error"
        else console_logs.append(f"[{msg.type}] {msg.text}")
    ))

    yield

    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        if console_errors:
            print(f"\n  浏览器控制台错误 ({len(console_errors)}):")
            for err in console_errors[:10]:
                print(f"    ✗ {err[:200]}")
```

---

## 完整 conftest.py 模板

将所有追溯增强整合到一个 conftest.py：

```python
# tests/conftest.py — 增强版（含失败追溯）
import pytest
import os
from datetime import datetime
from playwright.sync_api import BrowserContext


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """全局浏览器配置：失败追溯全部开启"""
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "locale": "zh-CN",
        "screenshot": "only-on-failure",
        "trace": "retain-on-failure",
        "video": "retain-on-failure",
        "record_video_dir": "reports/videos/",
    }


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """失败时自动截图 + 记录信息"""
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)

    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page and not page.is_closed():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("screenshots", exist_ok=True)
            page.screenshot(
                path=f"screenshots/{item.name}_{ts}.png",
                full_page=True,
            )


@pytest.fixture(autouse=True)
def log_network_on_failure(page, request):
    """失败时记录网络和控制台日志"""
    network_logs = []
    console_errors = []

    page.on("response", lambda r: network_logs.append(
        f"[{r.status}] {r.request.method} {r.url}"
    ))
    page.on("console", lambda msg: (
        console_errors.append(msg.text)
        if msg.type == "error" else None
    ))

    yield

    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        # 写网络日志
        if network_logs:
            os.makedirs("reports/network", exist_ok=True)
            with open(f"reports/network/{request.node.name}.log", "w") as f:
                f.write("\n".join(network_logs))

        # 打印控制台错误
        if console_errors:
            print(f"\n  Console Errors ({len(console_errors)}):")
            for err in console_errors[:10]:
                print(f"    ✗ {err[:200]}")


# 导入各模块 fixtures
from tests.fixtures.auth_fixture import *  # noqa: F401,F403
```
