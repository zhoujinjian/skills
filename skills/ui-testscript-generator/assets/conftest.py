# tests/conftest.py
import pytest
from playwright.sync_api import BrowserContext


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """全局浏览器上下文配置"""
    return {
        **browser_context_args,
        "viewport": {"width": 1920, "height": 1080},
        "locale": "zh-CN",
    }


# 导入各模块 fixtures
# from tests.fixtures.auth_fixture import *  # noqa: F401,F403
# from tests.fixtures.data_fixture import *  # noqa: F401,F403
