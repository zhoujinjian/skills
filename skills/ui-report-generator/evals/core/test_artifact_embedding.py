"""test_artifact_embedding.py — 失败用例素材嵌入渲染测试

覆盖：
    - _nodeid_slug_variants 生成多 slug 变体
    - attach_artifacts 同时扫描 flat 布局 + pytest-raw 布局
    - _failure_dict 输出含 video_url / page_source_url / console_logs_url
    - render_html 输出含 lightbox modal + <video> 渲染 JS
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest

from parsers import UITestCase, attach_artifacts, _nodeid_slug_variants
from renderer import render_html


# ============ slug 变体 ============


def test_slug_variants_basic():
    """方法名 + 全 nodeid slug 都应生成。"""
    variants = _nodeid_slug_variants("tests/x.py::TestY::test_z")
    assert "test-z" in variants
    assert any("tests-x" in v for v in variants)


def test_slug_variants_extract_browser():
    """带 [chromium-xxx] 参数化的 nodeid 应解出浏览器变体。"""
    variants = _nodeid_slug_variants("tests/x.py::TestY::test_z[chromium-手机]")
    assert "test-z" in variants
    assert "test-z-chromium" in variants


def test_slug_variants_empty_nodeid():
    assert _nodeid_slug_variants("") == []


# ============ attach_artifacts 双布局扫描 ============


def _make_case(nodeid: str, status: str = "failed") -> UITestCase:
    return UITestCase(
        nodeid=nodeid,
        classname=nodeid.split("::")[1] if "::" in nodeid else "",
        testname=nodeid.split("::")[-1],
        file="",
        line=None,
        status=status,
        duration=1.0,
    )


def test_attach_artifacts_flat_layout(tmp_path):
    """conftest 直写的 flat 布局：artifacts/screenshots/, videos/, traces/。"""
    artifacts = tmp_path / "artifacts"
    (artifacts / "screenshots").mkdir(parents=True)
    (artifacts / "videos").mkdir(parents=True)
    (artifacts / "traces").mkdir(parents=True)
    (artifacts / "page-source").mkdir(parents=True)
    (artifacts / "console-logs").mkdir(parents=True)

    # 文件名匹配方法名 slug
    (artifacts / "screenshots" / "test-foo-viewport.png").write_bytes(b"x")
    (artifacts / "screenshots" / "test-foo-fullpage.png").write_bytes(b"x")
    (artifacts / "videos" / "test-foo.webm").write_bytes(b"x")
    (artifacts / "traces" / "test-foo-trace.zip").write_bytes(b"x")
    (artifacts / "page-source" / "test-foo.html").write_text("<html/>")
    (artifacts / "console-logs" / "test-foo.log").write_text("logs")

    case = _make_case("tests/x.py::TestY::test_foo")
    attach_artifacts([case], artifacts)

    assert len(case.artifacts["screenshots"]) == 2
    assert len(case.artifacts["videos"]) == 1
    assert len(case.artifacts["traces"]) == 1
    assert len(case.artifacts["page_source"]) == 1
    assert len(case.artifacts["console_logs"]) == 1


def test_attach_artifacts_parametrized_cases_not_crossmatched(tmp_path):
    """仅参数化 ID 不同的两个用例（小米/手表）不应互相误匹配对方的 video/trace。

    Regression：_nodeid_slug_variants 之前去掉参数化 ID，导致两个用例生成
    完全相同的 slug 集合，attach_artifacts 子串匹配时第一个用例错挂到
    第二个用例的 video。
    """
    artifacts = tmp_path / "artifacts"
    raw = artifacts / "pytest-raw"
    raw.mkdir(parents=True)

    # 模拟 pytest-playwright 实际生成的目录名（含 unicode escape）
    xiaomi_dir = raw / "tests-product-test-search-py-testsearch-test-search-valid-chromium-u5c0f-u7c73"
    watch_dir = raw / "tests-product-test-search-py-testsearch-test-search-valid-chromium-u624b-u8868"
    xiaomi_dir.mkdir(parents=True)
    watch_dir.mkdir(parents=True)
    (xiaomi_dir / "video.webm").write_bytes(b"XIAOMI")
    (xiaomi_dir / "trace.zip").write_bytes(b"XIAOMI_TRACE")
    (watch_dir / "video.webm").write_bytes(b"WATCH")
    (watch_dir / "trace.zip").write_bytes(b"WATCH_TRACE")

    # conftest flat 布局也含参数化 ID（小米/手表分别）
    shots = artifacts / "screenshots"
    shots.mkdir(parents=True)
    (shots / "test-search-valid-chromium-u5c0f-u7c73-viewport.png").write_bytes(b"xiaomi")
    (shots / "test-search-valid-chromium-u624b-u8868-viewport.png").write_bytes(b"watch")

    xiaomi = _make_case("tests/product/test_search.py::TestSearch::test_search_valid[chromium-小米]")
    watch = _make_case("tests/product/test_search.py::TestSearch::test_search_valid[chromium-手表]")
    attach_artifacts([xiaomi, watch], artifacts)

    # 小米用例必须只匹配到自己的 video/trace/screenshot，不含手表
    assert len(xiaomi.artifacts["videos"]) == 1
    assert "u5c0f-u7c73" in xiaomi.artifacts["videos"][0], f"误匹配: {xiaomi.artifacts['videos']}"
    assert "u624b-u8868" not in xiaomi.artifacts["videos"][0]

    assert len(xiaomi.artifacts["traces"]) == 1
    assert "u5c0f-u7c73" in xiaomi.artifacts["traces"][0]

    assert len(xiaomi.artifacts["screenshots"]) == 1
    assert "u5c0f-u7c73" in xiaomi.artifacts["screenshots"][0]

    # 手表用例同理
    assert len(watch.artifacts["videos"]) == 1
    assert "u624b-u8868" in watch.artifacts["videos"][0]
    assert "u5c0f-u7c73" not in watch.artifacts["videos"][0]


def test_attach_artifacts_pytest_raw_layout(tmp_path):
    """pytest-playwright 原生布局：artifacts/pytest-raw/<slug>/{trace.zip,video.webm}。"""
    artifacts = tmp_path / "artifacts"
    slug_dir = artifacts / "pytest-raw" / "tests-x-test-foo-chromium"
    slug_dir.mkdir(parents=True)
    (slug_dir / "trace.zip").write_bytes(b"x")
    (slug_dir / "video.webm").write_bytes(b"x")
    (slug_dir / "test-failed-1.png").write_bytes(b"x")

    case = _make_case("tests/x.py::TestY::test_foo[chromium]")
    attach_artifacts([case], artifacts)

    assert len(case.artifacts["videos"]) == 1
    assert len(case.artifacts["traces"]) == 1


def test_attach_artifacts_failure_context_sidecar(tmp_path):
    """failure-context/<slug>.json sidecar 被扫描到。"""
    artifacts = tmp_path / "artifacts"
    (artifacts / "failure-context").mkdir(parents=True)
    sidecar = artifacts / "failure-context" / "test-foo.json"
    sidecar.write_text('{"rule": "missing_wait"}')

    case = _make_case("tests/x.py::TestY::test_foo")
    attach_artifacts([case], artifacts)

    assert len(case.artifacts["failure_context"]) == 1
    assert "test-foo.json" in case.artifacts["failure_context"][0]


def test_attach_artifacts_no_dir_is_noop(tmp_path):
    """artifacts 目录不存在时不报错。"""
    case = _make_case("tests/x.py::TestY::test_foo")
    attach_artifacts([case], tmp_path / "nonexistent")
    # artifacts 字段保持默认空 dict
    assert case.artifacts.get("screenshots", []) == []


# ============ _failure_dict 含 video_url 等字段 ============


def _make_failed_doc(tmp_path, with_artifacts: bool = True):
    """构造一个含失败用例的 ReportDocument。"""
    from parsers import ReportDocument, UISuiteSummary
    from analyzer import aggregate_by_module, aggregate_by_priority, aggregate_by_browser

    case = UITestCase(
        nodeid="tests/x.py::TestY::test_foo",
        classname="tests.x.TestY",
        testname="test_foo",
        file="",
        line=None,
        status="failed",
        duration=1.5,
        message="AssertionError",
    )
    if with_artifacts:
        artifacts = tmp_path / "artifacts"
        (artifacts / "screenshots").mkdir(parents=True)
        (artifacts / "videos").mkdir(parents=True)
        (artifacts / "page-source").mkdir(parents=True)
        (artifacts / "console-logs").mkdir(parents=True)
        (artifacts / "screenshots" / "test-foo-viewport.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 50)
        (artifacts / "videos" / "test-foo.webm").write_bytes(b"x")
        (artifacts / "page-source" / "test-foo.html").write_text("<html/>")
        (artifacts / "console-logs" / "test-foo.log").write_text("logs")
        attach_artifacts([case], artifacts)

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


def test_failure_payload_includes_video_and_screenshot_urls(tmp_path):
    """渲染后 PAYLOAD.failures[0] 应含 screenshots / video_url / page_source_url / console_logs_url。"""
    import json, re
    doc = _make_failed_doc(tmp_path, with_artifacts=True)
    html = render_html(doc)
    m = re.search(r"const PAYLOAD = (.+);", html)
    data = json.loads(m.group(1))
    f = data["failures"][0]

    assert len(f["screenshots"]) == 1, f"screenshots empty: {f}"
    assert f["screenshots"][0].startswith("data:image/png;base64,"), "should be base64 inlined"
    assert f["video_url"], "video_url missing"
    assert "test-foo.webm" in f["video_url"]
    assert f["page_source_url"], "page_source_url missing"
    assert f["console_logs_url"], "console_logs_url missing"


# ============ render_html 含 lightbox + video tag ============


def test_html_contains_lightbox_modal():
    """HTML 模板必须含 lightbox 容器 + 关闭按钮 + 背景遮罩。"""
    doc = _make_failed_doc(Path("/tmp/nonexistent_for_test"), with_artifacts=False)
    html = render_html(doc)
    assert 'id="lightbox"' in html
    assert 'class="lightbox"' in html
    assert 'lightbox-close' in html
    assert 'openLightbox' in html
    assert 'closeLightbox' in html


def test_html_contains_inline_video_tag_js():
    """JS 应包含 <video controls> 内联播放器渲染逻辑（不再是 <a> 外链）。"""
    doc = _make_failed_doc(Path("/tmp/nonexistent_for_test"), with_artifacts=False)
    html = render_html(doc)
    assert "<video controls" in html or "video controls" in html  # JS 模板字符串里的 video tag
    assert "video-player" in html  # CSS class


def test_html_contains_screenshot_grid():
    """CSS 含 screenshot-grid 样式，JS 用 grid 渲染。"""
    doc = _make_failed_doc(Path("/tmp/nonexistent_for_test"), with_artifacts=False)
    html = render_html(doc)
    assert "screenshot-grid" in html
    assert "screenshot-thumb" in html
    assert "zoom-hint" in html


def test_screenshots_capped_at_five(tmp_path):
    """截图超过 5 张时只取前 5。"""
    import json, re
    artifacts = tmp_path / "artifacts"
    (artifacts / "screenshots").mkdir(parents=True)
    for i in range(8):
        (artifacts / "screenshots" / f"test-foo-{i}.png").write_bytes(b"\x89PNG" + b"x" * 10)

    from parsers import ReportDocument, UISuiteSummary
    case = UITestCase(
        nodeid="tests/x.py::TestY::test_foo",
        classname="tests.x.TestY", testname="test_foo",
        file="", line=None, status="failed", duration=1.5, message="err",
    )
    attach_artifacts([case], artifacts)
    suite = UISuiteSummary(
        total=1, passed=0, failed=1, errors=0, skipped=0,
        pass_rate=0.0, total_duration=1.5,
        slowest_test=case.nodeid, slowest_duration=1.5,
    )
    doc = ReportDocument(
        generated_at="2026-06-23 12:00:00", suite=suite,
        tests=[case], failures=[case],
        by_module={}, by_priority={}, by_browser={},
    )
    html = render_html(doc)
    m = re.search(r"const PAYLOAD = (.+);", html)
    f = json.loads(m.group(1))["failures"][0]
    assert len(f["screenshots"]) == 5, f"expected cap at 5, got {len(f['screenshots'])}"


# ============ 通过用例不含 artifact 字段（差异化展示） ============


def test_passed_case_payload_excludes_artifacts():
    """通过用例的 test dict 不含 screenshots/video_url（差异化展示）。"""
    import json, re
    from parsers import ReportDocument, UISuiteSummary
    case = UITestCase(
        nodeid="tests/x.py::TestY::test_ok",
        classname="tests.x.TestY", testname="test_ok",
        file="", line=None, status="passed", duration=0.5,
    )
    suite = UISuiteSummary(
        total=1, passed=1, failed=0, errors=0, skipped=0,
        pass_rate=100.0, total_duration=0.5,
        slowest_test=case.nodeid, slowest_duration=0.5,
    )
    doc = ReportDocument(
        generated_at="2026-06-23 12:00:00", suite=suite,
        tests=[case], failures=[],
        by_module={}, by_priority={}, by_browser={},
    )
    html = render_html(doc)
    m = re.search(r"const PAYLOAD = (.+);", html)
    tests = json.loads(m.group(1))["tests"]
    assert len(tests) == 1
    t = tests[0]
    # 通过用例字段不含 screenshots/video_url
    assert "screenshots" not in t
    assert "video_url" not in t
    assert t["status"] == "passed"
