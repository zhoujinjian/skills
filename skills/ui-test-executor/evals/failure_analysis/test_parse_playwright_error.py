"""测试 _parse_playwright_error。

输入：playwright 失败消息原文（从 report.longreprtext 提取的段落）。
输出：结构化字段 locator / expected / received / action / hint / raw。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    spec = importlib.util.spec_from_file_location(
        "_conftest_under_test",
        Path(__file__).parent.parent.parent / "assets" / "conftest_template.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_conftest_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_locator_timeout_visible():
    mod = _load()
    msg = Path(__file__).parent / "fixtures" / "playwright_expect_visible.txt"
    text = msg.read_text(encoding="utf-8")
    result = mod._parse_playwright_error(text)
    assert result["locator"] == ".product-card"
    assert result["action"] == "to_be_visible"
    assert "Timeout" in result["received"] or "30000ms" in result["received"]
    assert "元素未在超时内出现/可见" in result["hint"]


def test_text_mismatch():
    mod = _load()
    msg = Path(__file__).parent / "fixtures" / "playwright_text_mismatch.txt"
    text = msg.read_text(encoding="utf-8")
    result = mod._parse_playwright_error(text)
    assert result["expected"] == "小米手机"
    assert result["received"] == '""' or result["received"] == ""
    assert "文案变更" in result["hint"]


def test_no_playwright_structure_falls_back_to_raw():
    """非 playwright 错误消息 → 所有字段空，raw 保留原文"""
    mod = _load()
    text = "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0\nassert 0 > 0"
    result = mod._parse_playwright_error(text)
    assert result["locator"] == ""
    assert result["expected"] == ""
    assert result["received"] == ""
    assert result["action"] == ""
    assert result["raw"] == text
    # hint 仍可基于关键词匹配得出（断言含 count = 0）
    assert result["hint"]  # 非空


def test_hint_for_count_zero_locator_inferred():
    """原生 assert count = 0 + introspection 中能看出 locator → 推断「定位器不匹配」"""
    mod = _load()
    text = (
        "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0\n"
        "assert 0 > 0\n"
        "count = 0"
    )
    result = mod._parse_playwright_error(text)
    assert "定位器" in result["hint"] or "DOM" in result["hint"]


def test_protocol_error_navigation_hint():
    """Protocol error + navigate → URL/base_url 配置问题"""
    mod = _load()
    text = 'playwright._impl._errors.Error: Page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL\n  navigating to "/register"'
    result = mod._parse_playwright_error(text)
    assert "URL" in result["hint"] or "base_url" in result["hint"] or "配置" in result["hint"]


def test_empty_input():
    mod = _load()
    result = mod._parse_playwright_error("")
    assert result["raw"] == ""
    assert result["hint"] == ""
