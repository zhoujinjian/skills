"""Tests for match_keyword() — substring + Chinese slug fallback matching."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from open_trace import match_keyword


def _c(name: str, hint: str) -> dict:
    return {"path": Path(f"/{name}/trace.zip"), "mtime": 1.0, "nodeid_hint": hint}


def test_returns_empty_list_when_no_match():
    candidates = [_c("a", "login"), _c("b", "search")]
    matches, err = match_keyword("cart", candidates)
    assert matches == []
    assert err is not None
    assert "cart" in err


def test_literal_substring_match():
    candidates = [
        _c("a", "tests-login-test-login-valid"),
        _c("b", "tests-search-test-search"),
    ]
    matches, err = match_keyword("login", candidates)
    assert err is None
    assert len(matches) == 1
    assert matches[0]["nodeid_hint"] == "tests-login-test-login-valid"


def test_chinese_slug_fallback_match():
    candidates = [
        _c("a", "tests-product-test-search-chromium-u5c0f-u7c73"),
    ]
    matches, err = match_keyword("小米", candidates)
    assert err is None
    assert len(matches) == 1
    assert "u5c0f" in matches[0]["nodeid_hint"]


def test_multiple_matches_returns_error_with_list():
    candidates = [
        _c("a", "tests-login-test-login-valid"),
        _c("b", "tests-login-test-login-invalid"),
        _c("c", "tests-search-test-search"),
    ]
    matches, err = match_keyword("login", candidates)
    assert len(matches) == 2
    assert err is not None
    assert "login" in err
    for hint in ("tests-login-test-login-valid", "tests-login-test-login-invalid"):
        assert hint in err


def test_keyword_latest_treated_as_keyword_not_special():
    candidates = [_c("a", "test-latest-foo"), _c("b", "test-bar")]
    matches, err = match_keyword("latest", candidates)
    assert err is None
    assert len(matches) == 1
    assert matches[0]["nodeid_hint"] == "test-latest-foo"


def test_case_insensitive_match():
    candidates = [_c("a", "tests-Login-Test-Login-Valid")]
    matches, err = match_keyword("LOGIN", candidates)
    assert err is None
    assert len(matches) == 1
