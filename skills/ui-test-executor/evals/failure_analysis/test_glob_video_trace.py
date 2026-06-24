"""测试 _resolve_video_trace：slug 不匹配时的 glob fallback + 多候选警告。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    spec = importlib.util.spec_from_file_location(
        "_gen_failure_analysis",
        Path(__file__).parent.parent.parent / "scripts" / "generate_failure_analysis.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_gen_failure_analysis"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_exact_slug_match(tmp_path):
    mod = _load()
    pytest_raw = tmp_path / "pytest-raw"
    slug = "tests-test-x-py-testx-test-a-chromium"
    (pytest_raw / slug).mkdir(parents=True)
    (pytest_raw / slug / "video.webm").write_bytes(b"fake")
    (pytest_raw / slug / "trace.zip").write_bytes(b"fake")
    sidecar = {"slug_hint": slug, "pytest_raw_dir": str(pytest_raw)}
    result = mod._resolve_video_trace(sidecar)
    assert result["video"].endswith("video.webm")
    assert result["trace"].endswith("trace.zip")


def test_no_matching_slug_returns_empty(tmp_path):
    mod = _load()
    sidecar = {"slug_hint": "does-not-exist", "pytest_raw_dir": str(tmp_path / "pytest-raw")}
    result = mod._resolve_video_trace(sidecar)
    assert result == {} or "video" not in result


def test_glob_fallback_when_slug_mismatch(tmp_path):
    """slug 完全不匹配，但 pytest-raw 下只有一个目录 → glob fallback 命中"""
    mod = _load()
    pytest_raw = tmp_path / "pytest-raw"
    slug_actual = "different-slug-actual"
    (pytest_raw / slug_actual).mkdir(parents=True)
    (pytest_raw / slug_actual / "video.webm").write_bytes(b"fake")
    sidecar = {"slug_hint": "different-slug-expected", "pytest_raw_dir": str(pytest_raw)}
    result = mod._resolve_video_trace(sidecar)
    # glob fallback：pytest-raw 下唯一目录被选中
    assert "video" in result


def test_multiple_candidates_warning(tmp_path):
    """pytest-raw 下多个目录都无法精确匹配 → 不静默选一个，返回空 + 警告字段"""
    mod = _load()
    pytest_raw = tmp_path / "pytest-raw"
    for s in ["slug-a", "slug-b"]:
        (pytest_raw / s).mkdir(parents=True)
        (pytest_raw / s / "video.webm").write_bytes(b"fake")
    sidecar = {"slug_hint": "slug-c", "pytest_raw_dir": str(pytest_raw)}
    result = mod._resolve_video_trace(sidecar)
    # 多候选时不应贸然选
    assert "video" not in result
    assert result.get("warning") or result.get("_multi_candidate")  # 警告标志
