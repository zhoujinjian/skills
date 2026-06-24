"""Tests for --dry-run mode and spawn behavior."""
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "open_trace.py"

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import open_trace


def _run(argv):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True, text=True,
    )
    return result.returncode, result.stderr, result.stdout


def test_dry_run_latest_does_not_spawn(tmp_path):
    raw = tmp_path / "pytest-raw" / "tests-foo-test-bar"
    raw.mkdir(parents=True)
    (raw / "trace.zip").write_bytes(b"")
    rc, err, out = _run(["--dry-run", "--artifacts-dir", str(tmp_path)])
    assert rc == 0
    assert "[DRY-RUN]" in out
    assert "show-trace" in out
    assert "trace.zip" in out


def test_dry_run_keyword(tmp_path):
    raw = tmp_path / "pytest-raw" / "tests-login-test-foo"
    raw.mkdir(parents=True)
    (raw / "trace.zip").write_bytes(b"")
    rc, err, out = _run(["login", "--dry-run", "--artifacts-dir", str(tmp_path)])
    assert rc == 0
    assert "show-trace" in out


def test_dry_run_path_query(tmp_path):
    trace = tmp_path / "mytrace.zip"
    trace.write_bytes(b"")
    rc, err, out = _run([str(trace), "--dry-run", "--artifacts-dir", str(tmp_path)])
    assert rc == 0
    assert str(trace) in out or str(trace.resolve()) in out
    assert "show-trace" in out


def test_spawn_calls_popen_with_start_new_session(tmp_path):
    raw = tmp_path / "pytest-raw" / "tests-foo"
    raw.mkdir(parents=True)
    trace = raw / "trace.zip"
    trace.write_bytes(b"")

    with mock.patch.object(open_trace.subprocess, "Popen") as mock_popen, \
         mock.patch.object(open_trace, "_check_playwright_available", return_value=True):
        rc = open_trace.main(["--artifacts-dir", str(tmp_path)])

    assert rc == 0
    assert mock_popen.called
    _, kwargs = mock_popen.call_args
    assert kwargs.get("start_new_session") is True
    cmd = mock_popen.call_args[0][0]
    assert "show-trace" in cmd
    assert str(trace.resolve()) in cmd or str(trace) in cmd


def test_spawn_redirects_to_log_file(tmp_path):
    raw = tmp_path / "pytest-raw" / "tests-foo"
    raw.mkdir(parents=True)
    (raw / "trace.zip").write_bytes(b"")

    with mock.patch.object(open_trace.subprocess, "Popen") as mock_popen, \
         mock.patch.object(open_trace, "_check_playwright_available", return_value=True):
        open_trace.main(["--artifacts-dir", str(tmp_path)])

    _, kwargs = mock_popen.call_args
    log_file = kwargs["stdout"]
    assert hasattr(log_file, "write")
    log_file.close()


def test_spawn_returns_2_when_playwright_missing(tmp_path):
    raw = tmp_path / "pytest-raw" / "tests-foo"
    raw.mkdir(parents=True)
    (raw / "trace.zip").write_bytes(b"")

    with mock.patch.object(open_trace, "_check_playwright_available", return_value=False):
        rc = open_trace.main(["--artifacts-dir", str(tmp_path)])

    assert rc == 2
