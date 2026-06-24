"""Tests for CLI-level error rendering via main() — stderr文案 + 退出码."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from open_trace import format_no_candidates_error, format_playwright_missing_error

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "open_trace.py"


def _run(argv, **kwargs):
    """invoke open_trace.py as subprocess; capture rc + stderr."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True, text=True, **kwargs,
    )
    return result.returncode, result.stderr, result.stdout


def test_no_trace_zip_in_artifacts_dir(tmp_path):
    (tmp_path / "pytest-raw").mkdir(parents=True)
    rc, err, _ = _run(["--artifacts-dir", str(tmp_path)])
    assert rc == 1
    assert "未找到任何 trace.zip" in err
    assert "用例通过了" in err or "retain-on-failure" in err
    assert str(tmp_path) in err


def test_pytest_raw_dir_missing(tmp_path):
    rc, err, _ = _run(["--artifacts-dir", str(tmp_path)])
    assert rc == 1
    assert "未找到任何 trace.zip" in err


def test_keyword_zero_match_error(tmp_path):
    raw = tmp_path / "pytest-raw" / "tests-login-test-foo"
    raw.mkdir(parents=True)
    (raw / "trace.zip").write_bytes(b"")
    rc, err, _ = _run(["cart", "--artifacts-dir", str(tmp_path)])
    assert rc == 1
    assert "未找到含 'cart'" in err
    assert "tests-login-test-foo" in err


def test_keyword_multi_match_error(tmp_path):
    for slug in ("tests-login-valid", "tests-login-invalid"):
        d = tmp_path / "pytest-raw" / slug
        d.mkdir(parents=True)
        (d / "trace.zip").write_bytes(b"")
    rc, err, _ = _run(["login", "--artifacts-dir", str(tmp_path)])
    assert rc == 1
    assert "多条 trace 匹配 'login'" in err
    assert "tests-login-valid" in err
    assert "tests-login-invalid" in err


def test_path_not_exist_error(tmp_path):
    rc, err, _ = _run([str(tmp_path / "nope.zip"), "--artifacts-dir", str(tmp_path)])
    assert rc == 1
    assert "路径不存在" in err
    assert "nope.zip" in err


def test_path_not_zip_error(tmp_path):
    f = tmp_path / "trace.txt"
    f.write_text("")
    rc, err, _ = _run([str(f), "--artifacts-dir", str(tmp_path)])
    assert rc == 1
    assert ".zip" in err


def test_format_no_candidates_error_includes_diagnostic_hints(tmp_path):
    msg = format_no_candidates_error(tmp_path)
    assert "未找到任何 trace.zip" in msg
    assert "retain-on-failure" in msg
    assert "setup 阶段失败" in msg or "setup" in msg
    assert str(tmp_path) in msg


def test_format_playwright_missing_error_includes_install_command():
    msg = format_playwright_missing_error()
    assert "playwright 未安装" in msg
    assert "playwright install" in msg

