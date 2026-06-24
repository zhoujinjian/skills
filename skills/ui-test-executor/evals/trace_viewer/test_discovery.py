"""Tests for build_candidates() — scans pytest-raw/*/trace.zip and returns sorted list."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from open_trace import build_candidates


def test_returns_empty_when_pytest_raw_missing(tmp_path):
    result = build_candidates(tmp_path / "nonexistent")
    assert result == []


def test_returns_empty_when_no_trace_zip(tmp_path):
    (tmp_path / "pytest-raw" / "some-test").mkdir(parents=True)
    (tmp_path / "pytest-raw" / "some-test" / "video.webm").write_text("")
    result = build_candidates(tmp_path)
    assert result == []


def test_finds_single_trace(tmp_path):
    slug_dir = tmp_path / "pytest-raw" / "tests-foo-test-bar"
    slug_dir.mkdir(parents=True)
    (slug_dir / "trace.zip").write_bytes(b"")
    result = build_candidates(tmp_path)
    assert len(result) == 1
    assert result[0]["path"].name == "trace.zip"
    assert result[0]["nodeid_hint"] == "tests-foo-test-bar"


def test_finds_multiple_traces(tmp_path):
    for slug in ["test-a", "test-b", "test-c"]:
        d = tmp_path / "pytest-raw" / slug
        d.mkdir(parents=True)
        (d / "trace.zip").write_bytes(b"")
    result = build_candidates(tmp_path)
    assert len(result) == 3
    slugs = [r["nodeid_hint"] for r in result]
    assert set(slugs) == {"test-a", "test-b", "test-c"}


def test_ignores_non_zip_files(tmp_path):
    d = tmp_path / "pytest-raw" / "x"
    d.mkdir(parents=True)
    (d / "trace.zip").write_bytes(b"")
    (d / "video.webm").write_bytes(b"")
    (d / "test-failed-1.png").write_bytes(b"")
    result = build_candidates(tmp_path)
    assert len(result) == 1


def test_ignores_trace_zip_not_in_slug_subdir(tmp_path):
    raw = tmp_path / "pytest-raw"
    raw.mkdir(parents=True)
    (raw / "trace.zip").write_bytes(b"")
    result = build_candidates(tmp_path)
    assert result == []


def test_each_candidate_has_required_fields(tmp_path):
    d = tmp_path / "pytest-raw" / "abc"
    d.mkdir(parents=True)
    (d / "trace.zip").write_bytes(b"")
    result = build_candidates(tmp_path)
    assert len(result) == 1
    c = result[0]
    assert isinstance(c["path"], Path)
    assert isinstance(c["mtime"], float)
    assert isinstance(c["nodeid_hint"], str)
    assert c["mtime"] > 0
