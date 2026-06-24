"""Tests for locate_root_cause.locate() — 3 种 MVP 根因定位."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from locate_root_cause import locate, RootCause, locate_all


# ============ 定位失效：locator_drift ============

def test_locator_drift_when_locator_absent_everywhere():
    cf = type("CF", (), {
        "category": "LOCATOR_ERROR",
        "locator_hint": 'get_by_placeholder("请输入 用户名")',
        "nodeid": "tests/x.py::test_a",
        "raw_message": "TimeoutError",
    })()
    page_source = '<html><body><input placeholder="登录账号"></body></html>'
    r = locate(cf, page_source=page_source)
    assert r.root_cause == "locator_drift"
    assert "candidates" in r.evidence  # 应该给候选元素


def test_locator_drift_finds_alternative_placeholder():
    cf = type("CF", (), {
        "category": "LOCATOR_ERROR",
        "locator_hint": 'get_by_placeholder("请输入 用户名")',
        "nodeid": "tests/x.py::test_a",
        "raw_message": "TimeoutError",
    })()
    page_source = '<input placeholder="账号"><input placeholder="密码">'
    r = locate(cf, page_source=page_source)
    assert r.root_cause == "locator_drift"
    # 候选列表应该包含实际的 placeholder
    placeholders = [c["value"] for c in r.evidence["candidates"] if c["kind"] == "placeholder"]
    assert "账号" in placeholders
    assert "密码" in placeholders


# ============ 等待不足：insufficient_wait ============

def test_insufficient_wait_when_locator_present_but_timed_out():
    cf = type("CF", (), {
        "category": "TIMEOUT_ERROR",
        "locator_hint": 'get_by_placeholder("请输入 用户名")',
        "nodeid": "tests/x.py::test_a",
        "raw_message": "TimeoutError: Timeout 10000ms exceeded",
    })()
    page_source = '<input placeholder="请输入 用户名">'
    r = locate(cf, page_source=page_source)
    assert r.root_cause == "insufficient_wait"
    # 应该提取出原 timeout 值
    assert r.evidence["original_timeout_ms"] == 10000


def test_insufficient_wait_extracts_timeout_from_message():
    cf = type("CF", (), {
        "category": "TIMEOUT_ERROR",
        "locator_hint": 'locator("div.login-form")',
        "nodeid": "tests/x.py::test_a",
        "raw_message": "TimeoutError: Locator.wait_for: Timeout 30000ms exceeded",
    })()
    page_source = '<div class="login-form">'
    r = locate(cf, page_source=page_source)
    assert r.root_cause == "insufficient_wait"
    assert r.evidence["original_timeout_ms"] == 30000


# ============ iframe 未切换：missing_iframe_switch ============

def test_missing_iframe_switch_when_locator_in_iframe():
    cf = type("CF", (), {
        "category": "LOCATOR_ERROR",
        "locator_hint": 'get_by_placeholder("验证码")',
        "nodeid": "tests/x.py::test_a",
        "raw_message": "TimeoutError",
    })()
    # 主文档没有，但 iframe 里有
    page_source = """
    <html><body>
      <iframe src="/captcha" id="captcha-frame"></iframe>
    </body></html>
    """
    # iframe_contents: 主文档中 iframe 的 src 列表
    iframe_contents = {
        "/captcha": '<input placeholder="验证码">',
    }
    r = locate(cf, page_source=page_source, iframe_contents=iframe_contents)
    assert r.root_cause == "missing_iframe_switch"
    assert "/captcha" in r.evidence["iframe_url"]


def test_no_iframe_when_locator_absent_in_main_and_no_iframes():
    """主文档没 locator，也没有 iframe → 回退为 locator_drift."""
    cf = type("CF", (), {
        "category": "LOCATOR_ERROR",
        "locator_hint": 'get_by_placeholder("xxx")',
        "nodeid": "tests/x.py::test_a",
        "raw_message": "TimeoutError",
    })()
    page_source = '<html><body><input placeholder="其他"></body></html>'
    r = locate(cf, page_source=page_source, iframe_contents=None)
    assert r.root_cause == "locator_drift"


def test_no_iframe_when_locator_absent_but_iframes_dont_contain_it():
    """有 iframe 但 locator 也不在 iframe 内 → locator_drift."""
    cf = type("CF", (), {
        "category": "LOCATOR_ERROR",
        "locator_hint": 'get_by_placeholder("xxx")',
        "nodeid": "tests/x.py::test_a",
        "raw_message": "TimeoutError",
    })()
    page_source = '<iframe src="/ad"></iframe>'
    iframe_contents = {"/ad": '<input placeholder="广告位">'}  # 不含目标
    r = locate(cf, page_source=page_source, iframe_contents=iframe_contents)
    assert r.root_cause == "locator_drift"


# ============ 扩展：ENV_ERROR 根因定位（4 种）============

def test_env_missing_browser_binary():
    cf = type("CF", (), {
        "category": "ENV_ERROR",
        "locator_hint": None,
        "raw_message": "Executable doesn't exist at chromium-1234/chrome",
    })()
    r = locate(cf)
    assert r.root_cause == "missing_browser_binary"
    assert r.fix_strategy == "category_repair"
    assert r.evidence["browser"] in ("chromium", "chrome")


def test_env_missing_python_package():
    cf = type("CF", (), {
        "category": "ENV_ERROR",
        "locator_hint": None,
        "raw_message": "ModuleNotFoundError: No module named 'requests'",
    })()
    r = locate(cf)
    assert r.root_cause == "missing_python_package"
    assert r.evidence["module"] == "requests"


def test_env_port_conflict():
    cf = type("CF", (), {
        "category": "ENV_ERROR",
        "locator_hint": None,
        "raw_message": "Error: Address already in use port 3000",
    })()
    r = locate(cf)
    assert r.root_cause == "port_conflict"
    assert r.evidence["port"] == 3000


def test_env_service_unavailable():
    cf = type("CF", (), {
        "category": "ENV_ERROR",
        "locator_hint": None,
        "raw_message": "net::ERR_CONNECTION_REFUSED 127.0.0.1:3000",
    })()
    r = locate(cf)
    assert r.root_cause == "service_unavailable"
    assert r.evidence["host"] == "127.0.0.1"
    assert r.evidence["port"] == 3000


# ============ 扩展：DATA_ERROR 根因定位（2 种）============

def test_data_unique_constraint_conflict():
    cf = type("CF", (), {
        "category": "DATA_ERROR",
        "locator_hint": None,
        "raw_message": "IntegrityError: UNIQUE constraint failed: users.email",
    })()
    r = locate(cf)
    assert r.root_cause == "unique_constraint_conflict"
    assert "users.email" in r.evidence["constraint"]


def test_data_fixture_data_missing():
    cf = type("CF", (), {
        "category": "DATA_ERROR",
        "locator_hint": None,
        "raw_message": "fixture 'registered_user' not found",
    })()
    r = locate(cf)
    assert r.root_cause == "fixture_data_missing"
    assert r.evidence["fixture"] == "registered_user"


# ============ 扩展：BUG 根因 ============

def test_bug_known_pattern():
    cf = type("CF", (), {
        "category": "BUG",
        "locator_hint": None,
        "raw_message": "Page Error: Uncaught TypeError",
    })()
    r = locate(cf)
    assert r.root_cause == "known_bug_pattern"
    assert r.fix_strategy == "category_repair"


# ============ 扩展：TIMEOUT_ERROR → page_not_loaded ============

def test_timeout_page_not_loaded_when_goto_in_message():
    cf = type("CF", (), {
        "category": "TIMEOUT_ERROR",
        "locator_hint": 'get_by_placeholder("x")',
        "raw_message": "page.goto('http://x') Timeout 10000ms exceeded",
    })()
    r = locate(cf)
    assert r.root_cause == "page_not_loaded"
    assert r.evidence["suggested_wait_state"] == "networkidle"


# ============ 扩展：LOCATOR_ERROR → shadow_dom_not_pierced ============

def test_locator_shadow_dom_not_pierced():
    cf = type("CF", (), {
        "category": "LOCATOR_ERROR",
        "locator_hint": 'get_by_placeholder("x")',
        "raw_message": "TimeoutError",
    })()
    page_source = '<div id="app"></div><script>const sr = shadowRoot.attachShadow({mode:"open"});</script>'
    r = locate(cf, page_source=page_source)
    assert r.root_cause == "shadow_dom_not_pierced"
    assert r.fix_strategy == "claude_semantic"


# ============ 非目标 category 返回 RootCause（SCRIPT_ERROR 兜底）============

def test_returns_root_cause_for_script_error():
    cf = type("CF", (), {
        "category": "SCRIPT_ERROR",
        "locator_hint": None,
        "nodeid": "tests/x.py::test_a",
        "raw_message": "AssertionError",
    })()
    r = locate(cf, page_source="")
    assert r is not None
    assert r.root_cause == "script_error_unspecified"
    assert r.fix_strategy == "category_repair"


# ============ locate_all（批量） ============

def test_locate_all_processes_multiple_classified_failures():
    cf1 = type("CF", (), {
        "category": "TIMEOUT_ERROR",
        "locator_hint": 'get_by_placeholder("x")',
        "nodeid": "tests/x.py::t1",
        "raw_message": "Timeout 10000ms",
    })()
    cf2 = type("CF", (), {
        "category": "ENV_ERROR",
        "locator_hint": None,
        "nodeid": "tests/x.py::t2",
        "raw_message": "ModuleNotFoundError: No module named 'requests'",
    })()
    results = locate_all([cf1, cf2], page_source_map={"tests/x.py::t1": '<input placeholder="x">'})
    assert len(results) == 2
    assert results[0].root_cause == "insufficient_wait"
    assert results[1].root_cause == "missing_python_package"


def test_root_cause_dataclass_has_required_fields():
    cf = type("CF", (), {
        "category": "LOCATOR_ERROR",
        "locator_hint": 'get_by_placeholder("x")',
        "nodeid": "tests/x.py::t1",
        "raw_message": "TimeoutError",
    })()
    page_source = '<input placeholder="y">'
    r = locate(cf, page_source=page_source)
    assert isinstance(r, RootCause)
    assert hasattr(r, "root_cause")
    assert hasattr(r, "evidence")
    assert hasattr(r, "fix_strategy")
    assert r.fix_strategy in ("ast_rewrite", "claude_semantic", "category_repair", "none")


# ============ 扩展：SCRIPT_ERROR 子根因 ============

def test_script_error_search_zero_assertion_classified_as_missing_async_wait():
    """搜索正向断言 + 0 结果 → missing_async_list_wait."""
    cf = type("CF", (), {
        "category": "SCRIPT_ERROR",
        "locator_hint": None,
        "nodeid": "tests/x.py::t1",
        "raw_message": "AssertionError: 搜索 '手表' 应返回商品，但结果数为 0",
    })()
    r = locate(cf)
    assert r is not None
    assert r.root_cause == "missing_async_list_wait"
    assert r.fix_strategy == "ast_rewrite"


def test_script_error_search_negative_assertion_not_matched():
    """搜索负向断言（应 0 实际 N）→ 仍走 script_error_unspecified."""
    cf = type("CF", (), {
        "category": "SCRIPT_ERROR",
        "locator_hint": None,
        "nodeid": "tests/x.py::t1",
        "raw_message": "AssertionError: 搜索 '飞机' 应无结果，但返回 3 个商品",
    })()
    r = locate(cf)
    assert r is not None
    assert r.root_cause == "script_error_unspecified"


def test_script_error_non_search_assertion_not_matched():
    """非搜索场景的 AssertionError → 仍走 script_error_unspecified."""
    cf = type("CF", (), {
        "category": "SCRIPT_ERROR",
        "locator_hint": None,
        "nodeid": "tests/x.py::t1",
        "raw_message": "AssertionError: 购物车商品数应为 0",
    })()
    r = locate(cf)
    assert r.root_cause == "script_error_unspecified"


def test_script_error_english_search_zero_matched():
    """英文搜索 0 结果 → 也命中（跨项目支持）."""
    cf = type("CF", (), {
        "category": "SCRIPT_ERROR",
        "locator_hint": None,
        "nodeid": "tests/x.py::t1",
        "raw_message": "AssertionError: search 'watch' should return items, count is 0",
    })()
    r = locate(cf)
    assert r.root_cause == "missing_async_list_wait"
