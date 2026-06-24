"""Tests for pages_yaml_resolver.py — pages.yaml 对比修复."""
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from pages_yaml_resolver import (
    resolve_locator_from_yaml,
    YamlResolvedLocator,
    _extract_hint_identity,
    _to_playwright_locator,
    _build_canonical_locator,
)


def _write_yaml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "pages.yaml"
    p.write_text(textwrap.dedent(content))
    return p


# ============ hint identity 提取 ============

def test_extract_placeholder():
    ident = _extract_hint_identity('get_by_placeholder("请输入 用户名")')
    assert ident["kind"] == "placeholder"
    assert ident["value"] == "请输入 用户名"


def test_extract_label():
    ident = _extract_hint_identity('get_by_label("密码")')
    assert ident["kind"] == "label"
    assert ident["value"] == "密码"


def test_extract_testid():
    ident = _extract_hint_identity('get_by_test_id("login-btn")')
    assert ident["kind"] == "testid"
    assert ident["value"] == "login-btn"


def test_extract_role_with_name():
    ident = _extract_hint_identity('get_by_role("button", name="登录")')
    assert ident["kind"] == "role"
    assert ident["value"] == "登录"
    assert ident["role"] == "button"


def test_extract_role_without_name():
    ident = _extract_hint_identity('get_by_role("checkbox")')
    assert ident["kind"] == "role"
    assert ident["value"] == "checkbox"


def test_extract_css_class():
    ident = _extract_hint_identity('locator(".login-btn")')
    assert ident["kind"] == "css_class"
    assert ident["value"] == "login-btn"


def test_extract_css_id():
    ident = _extract_hint_identity('locator("#username")')
    assert ident["kind"] == "css_id"
    assert ident["value"] == "username"


def test_extract_testid_from_css_attr():
    ident = _extract_hint_identity("locator(\"[data-testid='login-username']\")")
    assert ident["kind"] == "testid"
    assert ident["value"] == "login-username"


def test_extract_returns_empty_for_unknown():
    ident = _extract_hint_identity("some random text")
    assert ident == {}


# ============ 单条 locator → Playwright ============

def test_to_playwright_testid():
    r = _to_playwright_locator("data-testid", "[data-testid='login-btn']")
    assert r == 'page.get_by_test_id("login-btn")'


def test_to_playwright_testid_plain_value():
    r = _to_playwright_locator("data-testid", "login-btn")
    assert r == 'page.get_by_test_id("login-btn")'


def test_to_playwright_role_with_name():
    r = _to_playwright_locator("role", "button[name='登录']")
    assert r == 'page.get_by_role("button", name="登录")'


def test_to_playwright_placeholder():
    r = _to_playwright_locator("placeholder", "请输入 用户名")
    assert r == 'page.get_by_placeholder("请输入 用户名")'


def test_to_playwright_css_class():
    r = _to_playwright_locator("class", "login-btn")
    assert r == 'page.locator(".login-btn")'


def test_to_playwright_id():
    r = _to_playwright_locator("id", "username")
    assert r == 'page.locator("#username")'


def test_to_playwright_xpath():
    r = _to_playwright_locator("xpath", "//button[@type='submit']")
    assert r == "page.locator(\"xpath=//button[@type='submit']\")"


# ============ canonical locator 构建（含 fallback 优先级）============

def test_build_canonical_prefers_testid_over_placeholder():
    element = {
        "element_name": "用户名输入框",
        "locator": {
            "strategy": "placeholder",
            "value": "请输入 用户名",
            "fallback": [
                {"strategy": "data-testid", "value": "[data-testid='login-username']"},
            ],
        },
    }
    r = _build_canonical_locator(element)
    # 应该优先 testid
    assert "get_by_test_id" in r
    assert "login-username" in r


def test_build_canonical_uses_main_locator_when_no_fallback():
    element = {
        "element_name": "登录按钮",
        "locator": {
            "strategy": "role",
            "value": "button[name='登录']",
        },
    }
    r = _build_canonical_locator(element)
    assert "get_by_role" in r


# ============ resolve_locator_from_yaml 端到端 ============

@pytest.fixture
def sample_yaml(tmp_path):
    return _write_yaml(tmp_path, """
        meta:
          generator: "ui-page-parser"
        pages:
          - page_name: "登录页"
            url: "/login"
            elements:
              - element_name: "用户名输入框"
                element_type: "input"
                locator:
                  strategy: "data-testid"
                  value: "[data-testid='login-username']"
                  fallback:
                    - strategy: "placeholder"
                      value: "请输入 用户名"
              - element_name: "登录按钮"
                element_type: "button"
                locator:
                  strategy: "role"
                  value: "button[name='登录']"
    """)


def test_resolve_matches_by_placeholder_fallback(sample_yaml):
    r = resolve_locator_from_yaml(
        pages_yaml_path=sample_yaml,
        failing_locator_hint='get_by_placeholder("请输入 用户名")',
    )
    assert r is not None
    assert r.found is True
    assert r.page_name == "登录页"
    assert r.element_name == "用户名输入框"
    # canonical 应当优先 data-testid（主 locator）
    assert "get_by_test_id" in r.canonical_locator
    assert "login-username" in r.canonical_locator


def test_resolve_matches_by_role(sample_yaml):
    r = resolve_locator_from_yaml(
        pages_yaml_path=sample_yaml,
        failing_locator_hint='get_by_role("button", name="登录")',
    )
    assert r is not None
    assert r.found is True
    assert r.element_name == "登录按钮"


def test_resolve_returns_none_when_no_match(sample_yaml):
    r = resolve_locator_from_yaml(
        pages_yaml_path=sample_yaml,
        failing_locator_hint='get_by_placeholder("不存在的字段")',
    )
    assert r is None or r.found is False


def test_resolve_returns_none_when_yaml_missing(tmp_path):
    r = resolve_locator_from_yaml(
        pages_yaml_path=tmp_path / "nonexistent.yaml",
        failing_locator_hint='get_by_placeholder("X")',
    )
    assert r is None


def test_resolve_filters_by_page_url(sample_yaml):
    """指定 page_url 时限定在该页面找。"""
    r = resolve_locator_from_yaml(
        pages_yaml_path=sample_yaml,
        failing_locator_hint='get_by_role("button", name="登录")',
        page_url="/login",
    )
    assert r is not None
    assert r.found is True


def test_resolve_fallbacks_extracted(sample_yaml):
    r = resolve_locator_from_yaml(
        pages_yaml_path=sample_yaml,
        failing_locator_hint='get_by_placeholder("请输入 用户名")',
    )
    assert r is not None
    assert len(r.fallbacks) == 1
    assert r.fallbacks[0]["strategy"] == "placeholder"


def test_resolve_match_reason_documented(sample_yaml):
    r = resolve_locator_from_yaml(
        pages_yaml_path=sample_yaml,
        failing_locator_hint='get_by_role("button", name="登录")',
    )
    assert r is not None
    assert r.match_reason  # 非空字符串
