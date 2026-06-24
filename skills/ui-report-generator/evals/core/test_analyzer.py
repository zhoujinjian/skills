"""test_analyzer.py — analyzer.py 单元测试

覆盖：
    - aggregate_by_module / by_priority / by_browser
    - aggregate_diagnose（含升级标记）
    - analyze_risk（高/中/低分级）
    - cluster_failures（按根因聚类）
    - generate_suggestions（高频根因 + ENV + LOCATOR + 升级）
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest

from analyzer import (
    aggregate_by_browser,
    aggregate_by_module,
    aggregate_by_priority,
    aggregate_diagnose,
    analyze_risk,
    cluster_failures,
    generate_suggestions,
)
from parsers import DiagnoseRecord, UITestCase


# ============ fixtures ============


def _case(nodeid, file, status, duration=1.0, browser=None, markers=None, message=None, classname=None):
    return UITestCase(
        nodeid=nodeid,
        classname=classname or (nodeid.split("::")[1] if "::" in nodeid else ""),
        testname=nodeid.split("::")[-1],
        file=file,
        line=None,
        status=status,
        duration=duration,
        browser=browser,
        markers=markers or [],
        message=message,
    )


@pytest.fixture
def sample_cases():
    return [
        _case("tests/auth/test_login.py::TestLogin::test_a", "tests/auth/test_login.py", "passed", browser="chromium", markers=["P0"]),
        _case("tests/auth/test_login.py::TestLogin::test_b", "tests/auth/test_login.py", "failed", browser="chromium", markers=["P0"]),
        _case("tests/product/test_search.py::TestSearch::test_c", "tests/product/test_search.py", "passed", browser="chromium", markers=["P1"]),
        _case("tests/product/test_search.py::TestSearch::test_d", "tests/product/test_search.py", "failed", browser="firefox", markers=["P1"]),
        _case("tests/product/test_search.py::TestSearch::test_e", "tests/product/test_search.py", "skipped", browser="firefox"),
    ]


# ============ by_module ============


def test_aggregate_by_module_groups(sample_cases):
    m = aggregate_by_module(sample_cases)
    assert "auth" in m
    assert "product" in m
    assert m["auth"]["total"] == 2
    assert m["auth"]["passed"] == 1
    assert m["auth"]["failed"] == 1


def test_aggregate_by_module_pass_rate(sample_cases):
    m = aggregate_by_module(sample_cases)
    # product: 1 passed, 1 failed, 1 skipped out of 3 → 33.3%
    assert m["product"]["pass_rate"] == pytest.approx(33.3, abs=0.1)
    assert m["product"]["risk"] == "high"


def test_aggregate_by_module_no_markers():
    """没有 tests/ 子目录时退化到文件名。"""
    cases = [_case("test_x.py::T::test_a", "test_x.py", "passed")]
    m = aggregate_by_module(cases)
    assert "x" in m


def test_aggregate_by_module_classname_fallback():
    """关键回归：JUnit XML 常不包含 file= 属性，必须从 classname 解析模块。

    classname 形如 'tests.product.test_search.TestSearchPositive' → 'product'
    """
    cases = [_case(
        "tests/product/test_search.py::TestSearch::test_a",
        "",  # file 为空，模拟 JUnit XML 没写 file= 的情况
        "passed",
        classname="tests.product.test_search.TestSearch",
    )]
    m = aggregate_by_module(cases)
    assert "product" in m, f"expected 'product' module, got {list(m.keys())}"
    assert m["product"]["total"] == 1


def test_aggregate_by_module_classname_test_prefix():
    """classname 中 tests/ 后直接是 test_xxx.py → 模块名 strip test_ 前缀。"""
    cases = [_case(
        "tests/test_smoke.py::TestSmoke::test_a",
        "",
        "passed",
        classname="tests.test_smoke.TestSmoke",
    )]
    m = aggregate_by_module(cases)
    assert "smoke" in m


# ============ by_priority ============


def test_aggregate_by_priority(sample_cases):
    p = aggregate_by_priority(sample_cases)
    assert p["P0"]["total"] == 2
    assert p["P0"]["passed"] == 1
    assert p["P0"]["failed"] == 1
    assert p["P1"]["total"] == 2
    assert "未标记" in p


# ============ by_browser ============


def test_aggregate_by_browser(sample_cases):
    b = aggregate_by_browser(sample_cases)
    # sample_cases: 3 chromium (2 passed + 1 failed) + 2 firefox (1 failed + 1 skipped)
    assert b["chromium"]["total"] == 3
    assert b["chromium"]["passed"] == 2
    assert b["firefox"]["total"] == 2
    assert b["firefox"]["failed"] == 1


# ============ aggregate_diagnose ============


def test_aggregate_diagnose_basic():
    recs = [
        DiagnoseRecord(nodeid="a", category="SCRIPT_ERROR", root_cause="missing_async_list_wait"),
        DiagnoseRecord(nodeid="b", category="SCRIPT_ERROR", root_cause="missing_async_list_wait"),
        DiagnoseRecord(nodeid="c", category="LOCATOR_ERROR", root_cause="locator_drift"),
    ]
    by_cat, by_rc = aggregate_diagnose(recs)
    assert by_cat == {"SCRIPT_ERROR": 2, "LOCATOR_ERROR": 1}
    assert by_rc == {"missing_async_list_wait": 2, "locator_drift": 1}


def test_aggregate_diagnose_upgrade_label():
    """升级后的根因加（升级）后缀。"""
    recs = [
        DiagnoseRecord(nodeid="a", category="SCRIPT_ERROR", root_cause="missing_async_list_wait",
                       upgraded_root_cause="assertion_mismatch"),
    ]
    by_cat, by_rc = aggregate_diagnose(recs)
    assert by_rc == {"assertion_mismatch（升级）": 1}


# ============ analyze_risk ============


def test_analyze_risk_high():
    by_module = {"auth": {"total": 10, "passed": 5, "failed": 5, "skipped": 0, "pass_rate": 50.0, "avg_duration": 1.0, "risk": "high"}}
    risks = analyze_risk(by_module)
    assert len(risks) == 1
    assert risks[0]["level"] == "高"
    assert risks[0]["module"] == "auth"


def test_analyze_risk_mid():
    by_module = {"auth": {"total": 10, "passed": 8, "failed": 2, "skipped": 0, "pass_rate": 80.0, "avg_duration": 1.0, "risk": "mid"}}
    risks = analyze_risk(by_module)
    assert risks[0]["level"] == "中"


def test_analyze_risk_low_filtered():
    by_module = {"auth": {"total": 10, "passed": 10, "failed": 0, "skipped": 0, "pass_rate": 100.0, "avg_duration": 1.0, "risk": "low"}}
    risks = analyze_risk(by_module)
    assert risks == []


# ============ cluster_failures ============


def test_cluster_failures_by_root_cause():
    failures = [
        _case("a", "tests/x.py", "failed"),
        _case("b", "tests/x.py", "failed"),
    ]
    records = [
        DiagnoseRecord(nodeid="a", root_cause="missing_async_list_wait"),
        DiagnoseRecord(nodeid="b", root_cause="missing_async_list_wait"),
    ]
    clusters = cluster_failures(failures, records)
    assert len(clusters) == 1
    assert clusters[0]["root_cause"] == "missing_async_list_wait"
    assert clusters[0]["count"] == 2


def test_cluster_failures_fallback_no_record():
    failures = [_case("a", "tests/x.py", "failed", message="TimeoutError")]
    clusters = cluster_failures(failures, [])
    assert clusters[0]["root_cause"] == "TimeoutError（未诊断）"


# ============ generate_suggestions ============


def test_suggestions_high_freq_root_cause():
    by_module = {"x": {"pass_rate": 100.0, "risk": "low"}}
    by_category = {"SCRIPT_ERROR": 2}
    by_root_cause = {"missing_async_list_wait": 2}
    recs = []
    suggestions = generate_suggestions(by_module, by_category, by_root_cause, recs)
    assert any("重点修复根因" in s["suggestion"] for s in suggestions)


def test_suggestions_env_error():
    by_module = {}
    by_category = {"ENV_ERROR": 1}
    by_root_cause = {"missing_browser_binary": 1}
    suggestions = generate_suggestions(by_module, by_category, by_root_cause, [])
    assert any("ENV_ERROR" in s["suggestion"] for s in suggestions)


def test_suggestions_upgraded_assertion_mismatch():
    by_module = {}
    by_category = {"SCRIPT_ERROR": 1}
    by_root_cause = {"assertion_mismatch（升级）": 1}
    recs = [DiagnoseRecord(nodeid="a", upgraded_root_cause="assertion_mismatch")]
    suggestions = generate_suggestions(by_module, by_category, by_root_cause, recs)
    assert any("assertion_mismatch" in s["suggestion"] for s in suggestions)


def test_suggestions_empty_when_all_pass():
    suggestions = generate_suggestions({}, {}, {}, [])
    assert suggestions == []
