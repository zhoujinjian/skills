"""Tests for bug_repair.py — BUG 容错策略."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from bug_repair import (
    diagnose_bug_failure,
    execute_bug_repair,
    BugRepairPlan,
    _match_known_bug,
    _detect_intermittent_from_history,
    _has_network_5xx,
    _has_page_error,
    _apply_conftest_marker,
)


# ============ 已知 bug 指纹匹配 ============

def test_match_known_bug_login_placeholder():
    text = 'Locator.wait_for: Timeout 10000ms waiting for get_by_placeholder("请输入 用户名")'
    sig = _match_known_bug(text)
    assert sig is not None
    assert sig["id"] == "BUG-AUTH-001"


def test_match_known_bug_captcha():
    text = "captcha iframe failed to load: Timeout"
    sig = _match_known_bug(text)
    assert sig is not None
    assert sig["id"] == "BUG-CAPTCHA-LOAD"


def test_match_known_bug_no_match():
    assert _match_known_bug("random error") is None


# ============ 历史偶发检测 ============

def test_detect_intermittent_mixed_history():
    history = [
        {"nodeid": "tests/x.py::t", "status": "passed"},
        {"nodeid": "tests/x.py::t", "status": "failed"},
        {"nodeid": "tests/x.py::t", "status": "passed"},
    ]
    info = _detect_intermittent_from_history("tests/x.py::t", history)
    assert info is not None
    assert info["fail_count"] == 1
    assert info["total"] == 3


def test_detect_intermittent_all_passed():
    history = [{"nodeid": "x", "status": "passed"}] * 5
    assert _detect_intermittent_from_history("x", history) is None


def test_detect_intermittent_all_failed():
    history = [{"nodeid": "x", "status": "failed"}] * 5
    assert _detect_intermittent_from_history("x", history) is None


def test_detect_intermittent_insufficient_history():
    history = [{"nodeid": "x", "status": "passed"}]
    assert _detect_intermittent_from_history("x", history) is None


# ============ 5xx / page error 检测 ============

def test_has_network_5xx_positive():
    assert _has_network_5xx("## Network\n  POST /api  500") is True


def test_has_network_5xx_negative():
    assert _has_network_5xx("## Network\n  POST /api  200") is False


def test_has_page_error_positive():
    log = "## Console\n---\n## Page Errors\nUncaught TypeError at line 5\n---"
    assert _has_page_error(log) is True


def test_has_page_error_empty_section():
    log = "## Page Errors\n\n---"
    assert _has_page_error(log) is False


def test_has_page_error_no_section():
    assert _has_page_error("just console log") is False


# ============ 主入口 ============

def test_diagnose_returns_known_bug_plan():
    msg = 'Locator.wait_for: Timeout 10000ms waiting for get_by_placeholder("请输入 用户名")'
    plan = diagnose_bug_failure(msg)
    assert plan is not None
    assert plan.subkind == "known_bug"


def test_diagnose_returns_intermittent_plan():
    history = [
        {"nodeid": "tests/x.py::t", "status": "passed"},
        {"nodeid": "tests/x.py::t", "status": "failed"},
    ]
    plan = diagnose_bug_failure(
        message="TimeoutError", nodeid="tests/x.py::t",
        historical_failures=history,
    )
    assert plan is not None
    assert plan.subkind == "intermittent_bug"


def test_diagnose_returns_network_5xx_plan():
    plan = diagnose_bug_failure(
        message="TimeoutError",
        console_log="## Network\n  POST /api/cart  500",
    )
    assert plan is not None
    assert plan.subkind == "network_5xx_retry"


def test_diagnose_returns_stable_bug_plan():
    plan = diagnose_bug_failure(
        message="TimeoutError",
        console_log="## Page Errors\nUncaught TypeError\n---",
    )
    assert plan is not None
    assert plan.subkind == "stable_bug_report"


def test_diagnose_returns_none_when_no_signal():
    plan = diagnose_bug_failure("TimeoutError")
    assert plan is None


# ============ conftest hook 修改 ============

def test_apply_conftest_marker_creates_hook(tmp_path):
    conftest = tmp_path / "conftest.py"
    conftest.write_text("import pytest\n")
    ok = _apply_conftest_marker(
        conftest_path=conftest,
        marker_name="xfail",
        nodeid_filter="tests/x.py::TestA",
        reason="BUG-X",
    )
    assert ok is True
    content = conftest.read_text()
    assert "xfail" in content
    assert "tests/x.py::TestA" in content
    assert "BUG-X" in content


def test_apply_conftest_marker_idempotent(tmp_path):
    """同 nodeid + marker 不重复加。"""
    conftest = tmp_path / "conftest.py"
    conftest.write_text("import pytest\n")
    _apply_conftest_marker(
        conftest_path=conftest,
        marker_name="xfail",
        nodeid_filter="tests/x.py::t",
        reason="R1",
    )
    content_after_first = conftest.read_text()
    _apply_conftest_marker(
        conftest_path=conftest,
        marker_name="xfail",
        nodeid_filter="tests/x.py::t",
        reason="R2",
    )
    content_after_second = conftest.read_text()
    assert content_after_first == content_after_second


def test_apply_conftest_marker_dry_run_does_not_write(tmp_path):
    conftest = tmp_path / "conftest.py"
    original = "import pytest\n"
    conftest.write_text(original)
    _apply_conftest_marker(
        conftest_path=conftest,
        marker_name="xfail",
        nodeid_filter="tests/x.py::t",
        reason="R",
        dry_run=True,
    )
    assert conftest.read_text() == original


def test_apply_conftest_marker_missing_file(tmp_path):
    ok = _apply_conftest_marker(
        conftest_path=tmp_path / "nonexistent.py",
        marker_name="xfail",
        nodeid_filter="x",
        reason="r",
    )
    assert ok is False


# ============ 执行 ============

def test_execute_bug_repair_known_bug(tmp_path):
    conftest = tmp_path / "conftest.py"
    conftest.write_text("import pytest\n")
    plan = BugRepairPlan(
        subkind="known_bug",
        diagnosis="...",
        actions=[{
            "kind": "patch_conftest",
            "marker_name": "xfail",
            "nodeid_filter": "tests/x.py::t",
            "reason": "BUG-1",
        }],
    )
    result = execute_bug_repair(
        plan=plan, project_dir=tmp_path, conftest_path=conftest,
    )
    assert result.success is True
    assert "xfail" in conftest.read_text()


def test_execute_bug_repair_warning_only(tmp_path):
    conftest = tmp_path / "conftest.py"
    conftest.write_text("")
    plan = BugRepairPlan(
        subkind="stable_bug_report",
        diagnosis="...",
        actions=[{"kind": "warning", "message": "stable bug"}],
    )
    result = execute_bug_repair(
        plan=plan, project_dir=tmp_path, conftest_path=conftest,
    )
    assert result.success is False  # warning 让 success=False
