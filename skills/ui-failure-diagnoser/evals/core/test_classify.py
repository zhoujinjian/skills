"""Tests for classify_failure.classify() — 6 类失败分类器 (MVP: ENV/LOCATOR/TIMEOUT)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from classify_failure import classify, ClassifiedFailure


# ============ ENV_ERROR ============

def test_env_error_browser_closed():
    msg = "playwright._impl._errors.Error: Browser has been closed"
    r = classify("tests/x.py::test_a", msg)
    assert r.category == "ENV_ERROR"
    assert "Browser has been closed" in r.signals[0]


def test_env_error_target_page_closed():
    msg = "Error: Target page, context or browser has been closed"
    r = classify("tests/x.py::test_a", msg)
    assert r.category == "ENV_ERROR"


def test_env_error_protocol_error():
    msg = "playwright._impl._errors.Error: Protocol error (Page.navigate): Connection closed"
    r = classify("tests/x.py::test_a", msg)
    assert r.category == "ENV_ERROR"


# ============ LOCATOR_ERROR (TimeoutError + locator 不在 page-source) ============

def test_locator_error_when_locator_absent_from_page_source():
    msg = (
        "playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 10000ms exceeded.\n"
        'Call log:\n  - waiting for get_by_placeholder("请输入 用户名") to be visible'
    )
    page_source = '<html><body><input placeholder="登录账号"></body></html>'
    r = classify("tests/x.py::test_a", msg, page_source=page_source)
    assert r.category == "LOCATOR_ERROR"
    assert r.locator_hint == 'get_by_placeholder("请输入 用户名")'


def test_locator_error_with_get_by_role_locator():
    msg = (
        "TimeoutError: Locator.click: Timeout 10000ms exceeded.\n"
        'waiting for get_by_role("button", name="登录")'
    )
    page_source = '<html><body><button>Sign In</button></body></html>'
    r = classify("tests/x.py::test_a", msg, page_source=page_source)
    assert r.category == "LOCATOR_ERROR"


def test_locator_error_with_css_locator():
    msg = 'TimeoutError: waiting for locator("div.login-form")'
    page_source = '<html><body><div class="auth-form">x</div></body></html>'
    r = classify("tests/x.py::test_a", msg, page_source=page_source)
    assert r.category == "LOCATOR_ERROR"


# ============ TIMEOUT_ERROR (TimeoutError + locator 在 page-source) ============

def test_timeout_error_when_locator_present_in_page_source():
    msg = (
        "TimeoutError: Locator.wait_for: Timeout 10000ms exceeded.\n"
        'waiting for get_by_placeholder("请输入 用户名") to be visible'
    )
    page_source = '<html><body><input placeholder="请输入 用户名"></body></html>'
    r = classify("tests/x.py::test_a", msg, page_source=page_source)
    assert r.category == "TIMEOUT_ERROR"


def test_timeout_error_when_css_locator_present():
    msg = 'TimeoutError: waiting for locator("div.login-form")'
    page_source = '<html><body><div class="login-form">x</div></body></html>'
    r = classify("tests/x.py::test_a", msg, page_source=page_source)
    assert r.category == "TIMEOUT_ERROR"


# ============ SCRIPT_ERROR (原生 AssertionError) ============

def test_script_error_plain_assertion():
    msg = "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0\nassert 0 > 0"
    r = classify("tests/x.py::test_a", msg)
    assert r.category == "SCRIPT_ERROR"


def test_script_error_assert_with_business_message():
    msg = 'AssertionError: expected locator(".cart-count") to contain "3"'
    r = classify("tests/x.py::test_a", msg)
    assert r.category == "SCRIPT_ERROR"


# ============ DATA_ERROR (setup 阶段 + fixture 数据问题) ============

def test_data_error_setup_stage_with_fixture_failure():
    msg = "failed on setup with \"RuntimeError: test user 'demo' not found in database\""
    r = classify("tests/x.py::test_a", msg, failure_stage="setup")
    assert r.category == "DATA_ERROR"


# ============ BUG (console Page Error / Uncaught) ============

def test_bug_when_console_log_has_page_error():
    msg = "AssertionError: something failed"
    console_log = "## Page Errors\n  Error: Uncaught TypeError: Cannot read property 'length' of undefined"
    r = classify("tests/x.py::test_a", msg, console_log=console_log)
    assert r.category == "BUG"


def test_bug_when_network_500_in_console_log():
    msg = "TimeoutError: network timeout"
    console_log = "## Network\n  POST /api/cart  500  Internal Server Error"
    r = classify("tests/x.py::test_a", msg, console_log=console_log)
    assert r.category == "BUG"


# ============ 优先级 / 边界 ============

def test_env_error_beats_locator_error_when_both_signals():
    """ENV_ERROR 优先级最高（浏览器挂了什么都无意义）。"""
    msg = (
        "Browser has been closed\n"
        "During waiting for get_by_placeholder('x')"
    )
    r = classify("tests/x.py::test_a", msg)
    assert r.category == "ENV_ERROR"


def test_bug_beats_script_error_when_console_has_page_error():
    """BUG 优先级高于 SCRIPT_ERROR（原生断言可能是 bug 导致的）。"""
    msg = "AssertionError: count == 0"
    console_log = "## Page Errors\n  Error: Uncaught ReferenceError: xxx is not defined"
    r = classify("tests/x.py::test_a", msg, console_log=console_log)
    assert r.category == "BUG"


def test_page_source_none_falls_back_to_timeout_error():
    """page-source 缺失时，TimeoutError 优先归为 TIMEOUT_ERROR（直接证据，可走 ast_rewrite）。"""
    msg = 'TimeoutError: waiting for get_by_placeholder("xxx")'
    r = classify("tests/x.py::test_a", msg, page_source=None)
    assert r.category == "TIMEOUT_ERROR"
    assert r.confidence < 0.75  # 低置信度（无 page-source 佐证）


def test_returns_classified_failure_with_required_fields():
    msg = "Browser has been closed"
    r = classify("tests/x.py::test_a", msg)
    assert isinstance(r, ClassifiedFailure)
    assert r.nodeid == "tests/x.py::test_a"
    assert r.category == "ENV_ERROR"
    assert isinstance(r.signals, list)
    assert len(r.signals) >= 1
    assert 0.0 <= r.confidence <= 1.0
