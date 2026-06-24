"""Tests for match_path() — treats query as file path."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from open_trace import match_path


def test_absolute_existing_path(tmp_path):
    trace = tmp_path / "trace.zip"
    trace.write_bytes(b"")
    result, err = match_path(str(trace))
    assert err is None
    assert result == trace.resolve()


def test_relative_existing_path(tmp_path, monkeypatch):
    trace = tmp_path / "trace.zip"
    trace.write_bytes(b"")
    monkeypatch.chdir(tmp_path)
    result, err = match_path("trace.zip")
    assert err is None
    assert result == trace.resolve()


def test_nonexistent_path_returns_error(tmp_path):
    result, err = match_path(str(tmp_path / "nope.zip"))
    assert result is None
    assert err is not None
    assert "路径不存在" in err
    assert "nope.zip" in err


def test_non_zip_extension_returns_error(tmp_path):
    f = tmp_path / "trace.txt"
    f.write_text("")
    result, err = match_path(str(f))
    assert result is None
    assert err is not None
    assert ".zip" in err


def test_directory_returns_error(tmp_path):
    result, err = match_path(str(tmp_path))
    assert result is None
    assert err is not None
    assert "路径不存在" in err or "不是" in err
