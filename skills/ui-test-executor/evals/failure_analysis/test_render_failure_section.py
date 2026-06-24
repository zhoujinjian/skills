"""测试 render_failure_section：单条失败用例 → MD 章节。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    """加载 generate_failure_analysis.py 作为模块"""
    spec = importlib.util.spec_from_file_location(
        "_gen_failure_analysis",
        Path(__file__).parent.parent.parent / "scripts" / "generate_failure_analysis.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_gen_failure_analysis"] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_sidecar_native_assert():
    return {
        "nodeid": "tests/test_search.py::TestS::test_search[chromium-小米]",
        "slug_hint": "tests-test-search-py-tests-test-search-chromium-u5c0f-u7c73",
        "phase": "main",
        "duration": 1.56,
        "browser": "chromium",
        "url": "http://localhost:3000/search?q=小米",
        "title": "搜索结果",
        "failure_type": "AssertionError",
        "rule": "搜索「小米」应返回至少 1 件商品",
        "rule_source": "docstring",
        "assertion": {
            "statement": 'assert count > 0, f"搜索 \'{keyword}\' 应返回商品"',
            "file": "tests/test_search.py:55",
            "introspection": "assert 0 > 0\ncount = 0\nkeyword = '小米'",
            "message": "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0",
        },
        "expect_failure": {
            "locator": "",
            "expected": "",
            "received": "",
            "action": "",
            "hint": "定位器与实际 DOM class 不匹配（推断，仅作参考）",
            "raw": "AssertionError: ...\nassert 0 > 0\ncount = 0",
        },
        "artifacts": {
            "screenshots": [
                "/tmp/screenshots/x-viewport.png",
                "/tmp/screenshots/x-fullpage.png",
            ],
            "page_source": "/tmp/x.html",
            "console_log": "/tmp/x.log",
        },
        "pytest_raw_dir": "/tmp/pytest-raw",
    }


def test_section_contains_required_sections():
    mod = _load()
    case = mod.FailureCase(
        nodeid="tests/test_search.py::TestS::test_search[chromium-小米]",
        classname="tests.test_search.TestS",
        name="test_search[chromium-小米]",
        file="tests/test_search.py",
        line="55",
        duration=1.56,
        message="AssertionError: ...",
    )
    md = mod.render_failure_section(case, sidecar=_build_sidecar_native_assert(), video_trace={})
    assert "判定规则" in md
    assert "断言原文" in md
    assert "预期 vs 实际" in md
    assert "页面元素校验" in md
    assert "失败截图" in md
    assert "失败录屏与 Trace" in md
    assert "搜索「小米」应返回至少 1 件商品" in md  # rule 出现
    assert "tests/test_search.py:55" in md  # 文件:行号


def test_section_native_assert_renders_empty_locator_row():
    """原生 assert 失败 → locator/expected/received 行显示「未提取」"""
    mod = _load()
    case = mod.FailureCase(
        nodeid="...", classname="...", name="...", duration=1, message="..."
    )
    md = mod.render_failure_section(case, sidecar=_build_sidecar_native_assert(), video_trace={})
    assert "原生 assert" in md or "未提取" in md


def test_section_playwright_expect_renders_locator():
    """playwright expect 失败 → locator/expected/received 行有值"""
    mod = _load()
    sidecar = _build_sidecar_native_assert()
    sidecar["expect_failure"] = {
        "locator": ".product-card",
        "expected": "visible",
        "received": "Timeout 30000ms",
        "action": "to_be_visible",
        "hint": "元素未在超时内出现/可见（推断，仅作参考）",
        "raw": "",
    }
    case = mod.FailureCase(nodeid="...", classname="...", name="...", duration=1, message="...")
    md = mod.render_failure_section(case, sidecar=sidecar, video_trace={})
    assert ".product-card" in md
    assert "visible" in md
    assert "Timeout" in md


def test_section_video_trace_paths_rendered():
    mod = _load()
    case = mod.FailureCase(nodeid="...", classname="...", name="...", duration=1, message="...")
    video_trace = {
        "video": "/tmp/pytest-raw/slug/video.webm",
        "trace": "/tmp/pytest-raw/slug/trace.zip",
    }
    md = mod.render_failure_section(case, sidecar=_build_sidecar_native_assert(), video_trace=video_trace)
    assert "video.webm" in md
    assert "trace.zip" in md
    assert "playwright show-trace" in md


def test_section_video_trace_missing_renders_warning():
    mod = _load()
    case = mod.FailureCase(nodeid="...", classname="...", name="...", duration=1, message="...")
    md = mod.render_failure_section(case, sidecar=_build_sidecar_native_assert(), video_trace={})
    assert "未生成" in md
