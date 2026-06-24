"""Tests for verify_fix.verify_single_test() — subprocess 重跑单用例."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from verify_fix import verify_single_test, VerifyResult


def _mock_completed(returncode, stdout="", stderr=""):
    m = mock.Mock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def test_verify_returns_passed_when_pytest_exits_0():
    with mock.patch("verify_fix.subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed(0, stdout="1 passed")
        result = verify_single_test(
            project_dir=Path("/tmp/proj"),
            nodeid="tests/test_x.py::test_a",
        )
    assert result.status == "passed"
    assert result.pytest_exit_code == 0


def test_verify_returns_failed_when_pytest_exits_1():
    with mock.patch("verify_fix.subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed(1, stdout="1 failed")
        result = verify_single_test(
            project_dir=Path("/tmp/proj"),
            nodeid="tests/test_x.py::test_a",
        )
    assert result.status == "failed"


def test_verify_returns_error_when_pytest_exits_non_zero_non_one():
    with mock.patch("verify_fix.subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed(2, stderr="error")
        result = verify_single_test(
            project_dir=Path("/tmp/proj"),
            nodeid="tests/test_x.py::test_a",
        )
    assert result.status == "error"


def test_verify_returns_timeout_on_timeout_expired():
    import subprocess as sp
    with mock.patch("verify_fix.subprocess.run", side_effect=sp.TimeoutExpired(cmd="pytest", timeout=10)):
        result = verify_single_test(
            project_dir=Path("/tmp/proj"),
            nodeid="tests/test_x.py::test_a",
            timeout_sec=10,
        )
    assert result.status == "timeout"


def test_verify_passes_correct_args_to_pytest():
    with mock.patch("verify_fix.subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed(0)
        verify_single_test(
            project_dir=Path("/tmp/proj"),
            nodeid="tests/test_x.py::TestA::test_a",
            base_url="http://localhost:3000",
        )
    cmd = mock_run.call_args[0][0]
    # 命令应以 sys.executable -m pytest 开头
    assert cmd[0] == sys.executable
    assert cmd[1] == "-m"
    assert cmd[2] == "pytest"
    # nodeid 应该原样传入
    assert "tests/test_x.py::TestA::test_a" in cmd
    # base_url 应该以参数形式传
    assert "--base-url" in cmd
    assert "http://localhost:3000" in cmd


def test_verify_includes_browser_when_specified():
    with mock.patch("verify_fix.subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed(0)
        verify_single_test(
            project_dir=Path("/tmp/proj"),
            nodeid="tests/x.py::t",
            browser="chromium",
        )
    cmd = mock_run.call_args[0][0]
    assert "--browser" in cmd
    assert "chromium" in cmd


def test_verify_result_dataclass_has_required_fields():
    r = VerifyResult(status="passed", pytest_exit_code=0, duration_sec=1.5, stdout="x", stderr="")
    assert r.status == "passed"
    assert r.pytest_exit_code == 0
    assert r.duration_sec == 1.5


def test_verify_default_timeout_is_300_sec():
    """单用例默认 5 分钟超时（足够 UI 测试跑完）。"""
    with mock.patch("verify_fix.subprocess.run") as mock_run:
        mock_run.return_value = _mock_completed(0)
        verify_single_test(
            project_dir=Path("/tmp/proj"),
            nodeid="tests/x.py::t",
        )
    # 第二个位置参数应该是 timeout
    timeout = mock_run.call_args.kwargs.get("timeout", None) or mock_run.call_args[1].get("timeout")
    assert timeout == 300
