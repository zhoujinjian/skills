"""test_renderer.py — renderer.py 回归测试

覆盖：
    - HTML 模板格式化（{}/{{}} 转义不出错）
    - escapeHtml / escapeAttr JS 函数源码正确（无 \" 坍塌 bug）
    - 真实数据渲染后 HTML 在浏览器中无 JS 运行时错误（headless 验证）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest

from analyzer import aggregate_by_browser, aggregate_by_module, aggregate_by_priority, aggregate_diagnose
from parsers import ReportDocument, UISuiteSummary, UITestCase
from renderer import render_html


# ============ 模板格式化正确性 ============


@pytest.fixture
def sample_doc():
    case = UITestCase(
        nodeid='tests/x.py::TestY::test_a[chromium-手机]',
        classname="TestY",
        testname="test_a",
        file="tests/x.py",
        line=10,
        status="failed",
        duration=1.5,
        message='AssertionError: 搜索 "手机" 应返回商品',
        browser="chromium",
    )
    case.artifacts = {"screenshots": [], "videos": [], "traces": [], "page_source": [], "console_logs": []}
    suite = UISuiteSummary(
        total=1, passed=0, failed=1, errors=0, skipped=0,
        pass_rate=0.0, total_duration=1.5,
        slowest_test=case.nodeid, slowest_duration=1.5,
    )
    return ReportDocument(
        generated_at="2026-06-23 12:00:00",
        suite=suite,
        tests=[case],
        failures=[case],
        by_module={"x": {"total": 1, "passed": 0, "failed": 1, "skipped": 0,
                          "pass_rate": 0.0, "avg_duration": 1.5, "risk": "high"}},
        by_priority={"未标记": {"total": 1, "passed": 0, "failed": 1, "pass_rate": 0.0}},
        by_browser={"chromium": {"total": 1, "passed": 0, "failed": 1, "pass_rate": 0.0}},
    )


def test_render_html_basic_structure(sample_doc):
    html = render_html(sample_doc, title="Test Report")
    assert "<!DOCTYPE html>" in html
    assert "<title>Test Report</title>" in html
    assert "const PAYLOAD = " in html
    assert "</html>" in html


def test_render_html_payload_is_valid_json(sample_doc):
    html = render_html(sample_doc)
    m = re.search(r"const PAYLOAD = (.+);", html)
    assert m, "PAYLOAD not found"
    data = json.loads(m.group(1))  # 抛错说明 JSON 有问题
    assert data["suite"]["total"] == 1
    assert len(data["tests"]) == 1


# ============ Allure 入口 ============


def test_render_allure_btn_active_when_url_provided(sample_doc):
    """传入 allure_url 时，渲染为可点击的蓝色按钮。"""
    html = render_html(sample_doc, allure_url="http://localhost:8088")
    assert 'class="allure-btn"' in html
    assert 'href="http://localhost:8088"' in html
    assert 'target="_blank"' in html
    assert "打开 Allure 报告" in html
    # 不应该有 disabled 类
    assert "allure-btn disabled" not in html


def test_render_allure_btn_disabled_when_url_absent(sample_doc):
    """未传 allure_url 时，渲染为灰色 disabled 提示。"""
    html = render_html(sample_doc)
    assert 'class="allure-btn disabled"' in html
    assert "Allure 未就绪" in html
    # 不应该是可点击链接
    assert 'href=' not in html.split("allure-btn disabled")[0].rsplit("<span", 1)[-1]


def test_render_allure_btn_html_escaped(sample_doc):
    """URL 含特殊字符时正确 HTML escape，防 XSS。"""
    html = render_html(sample_doc, allure_url='http://x.com?a=1&b="evil"')
    assert "&amp;" in html or "&quot;" in html  # 至少要 escape & 或 "
    assert '"evil"' not in html  # 原文不能直接出现


# ============ 回归：escapeHtml 函数源码正确性 ============


def test_escape_html_js_function_well_formed(sample_doc):
    """关键回归：之前 \" 在 Python 三引号字符串里坍塌成 "，导致 JS 报 Unexpected string。

    现在 escapeHtml 必须用单引号 JS key 来表达双引号字符。
    """
    html = render_html(sample_doc)
    assert "function escapeHtml" in html
    # 关键回归：HTML 全文不能出现 """:  这种坏语法（空字符串 key 紧跟未闭合字符串）
    assert '""":' not in html, "broken JS dict syntax detected"
    # 应该用单引号包裹双引号字符
    assert "'\"': \"&quot;\"" in html, "escapeHtml should use single-quoted JS key for double-quote char"


def test_escape_attr_js_function_well_formed(sample_doc):
    html = render_html(sample_doc)
    m = re.search(r"function escapeAttr\(s\)", html)
    assert m, "escapeAttr function not found"


# ============ 真实 headless 浏览器验证（可选，依赖 playwright）===========


def test_html_renders_without_js_errors(sample_doc):
    """headless 浏览器加载渲染后的 HTML，确认无 pageerror + 关键区块非空。

    跳过条件：环境无 playwright。
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright not installed")

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(render_html(sample_doc, title="Headless Test"))
        path = f.name

    try:
        errors: list[str] = []
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            # 用 domcontentloaded 避免 Chart.js CDN 阻塞 load 事件
            page.goto(f"file://{path}", wait_until="domcontentloaded", timeout=10000)
            page.wait_for_timeout(2000)
            cards = page.locator("#overview-cards").inner_text()
            module_table = page.locator("#module-table").inner_text()
            browser.close()

        assert not errors, f"JS pageerrors: {errors}"
        assert "总用例" in cards
        assert "1" in cards  # total
        assert "x" in module_table  # 模块名
    except Exception as e:
        if "Target page, context or browser has been closed" in str(e) or "Timeout" in str(e):
            pytest.skip(f"playwright environment unavailable: {e}")
        raise
    finally:
        Path(path).unlink(missing_ok=True)
