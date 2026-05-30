# tests/conftest.py — 增强版（含完整失败追溯）
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
    }


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """失败时自动截图 + 保存 rep 属性"""
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)

    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page and not page.is_closed():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("screenshots", exist_ok=True)
            try:
                page.screenshot(
                    path=f"screenshots/{item.name}_{ts}.png",
                    full_page=True,
                )
            except Exception:
                pass


@pytest.fixture(autouse=True)
def log_on_failure(page, request):
    """失败时记录网络请求和控制台日志"""
    network_logs = []
    console_errors = []

    page.on("response", lambda r: network_logs.append(
        f"[{r.status}] {r.request.method} {r.url}"
    ))
    page.on("console", lambda msg: (
        console_errors.append(msg.text) if msg.type == "error" else None
    ))

    yield

    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        if network_logs:
            os.makedirs("reports/network", exist_ok=True)
            with open(f"reports/network/{request.node.name}.log", "w") as f:
                f.write(f"# {request.node.name}\n")
                f.write("\n".join(network_logs))

        if console_errors:
            print(f"\n  Console Errors ({len(console_errors)}):")
            for err in console_errors[:10]:
                print(f"    ✗ {err[:200]}")


# 导入各模块 fixtures
# from tests.fixtures.auth_fixture import *  # noqa: F401,F403
