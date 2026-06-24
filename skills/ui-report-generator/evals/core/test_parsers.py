"""test_parsers.py — parsers.py 单元测试

覆盖：
    - JUnit XML 解析（含参数化浏览器后缀、状态分类、traceback）
    - ui_repair_report.md 解析（概览表 + 失败明细字段映射）
    - nodeid slug 化（artifacts 关联）
    - 历史 JSON 加载
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest

from parsers import (
    DiagnoseRecord,
    _nodeid_slug,
    load_history,
    parse_diagnose_md,
    parse_junit_xml,
)


# ============ JUnit XML 解析 ============


JUNIT_XML_WITH_FAILURES = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="4" failures="1" errors="1" skipped="1" time="10.5">
    <testcase classname="tests.product.test_search.TestSearchPositive"
              name="test_search_valid_keyword_shows_results[chromium-手机]"
              file="tests/product/test_search.py" line="55" time="1.5">
      <failure message="AssertionError: 搜索 '手机' 应返回商品，但结果数为 0"
               type="AssertionError">traceback line 1
traceback line 2</failure>
      <system-out>[BROWSER=chromium]</system-out>
    </testcase>
    <testcase classname="tests.auth.test_login.TestLogin"
              name="test_login_valid" file="tests/auth/test_login.py" line="20" time="0.5">
    </testcase>
    <testcase classname="tests.auth.test_login.TestLogin"
              name="test_login_invalid" file="tests/auth/test_login.py" line="30" time="0.3">
      <error message="failed on setup" type="fixture">setup err</error>
    </testcase>
    <testcase classname="tests.auth.test_login.TestLogin"
              name="test_login_skip" file="tests/auth/test_login.py" line="40" time="0.0">
      <skipped message="reason" />
    </testcase>
  </testsuite>
</testsuites>
"""


def test_parse_junit_xml_counts():
    suite, cases = _parse(JUNIT_XML_WITH_FAILURES)
    assert suite.total == 4
    assert suite.passed == 1
    assert suite.failed == 1  # failure
    assert suite.errors == 1  # error
    assert suite.skipped == 1
    assert suite.total_duration == 10.5
    assert len(cases) == 4


def test_parse_junit_xml_failure_status():
    suite, cases = _parse(JUNIT_XML_WITH_FAILURES)
    failed = [c for c in cases if c.status == "failed"]
    assert len(failed) == 1
    assert "搜索 '手机'" in (failed[0].message or "")
    assert failed[0].failure_stage == "call"


def test_parse_junit_xml_error_status():
    suite, cases = _parse(JUNIT_XML_WITH_FAILURES)
    errors = [c for c in cases if c.status == "error"]
    assert len(errors) == 1
    # error message 含 "setup" → 失败阶段判定为 setup
    assert errors[0].failure_stage == "setup"


def test_parse_junit_xml_skipped_status():
    suite, cases = _parse(JUNIT_XML_WITH_FAILURES)
    skipped = [c for c in cases if c.status == "skipped"]
    assert len(skipped) == 1


def test_parse_junit_xml_browser_from_system_out():
    suite, cases = _parse(JUNIT_XML_WITH_FAILURES)
    search_case = next(c for c in cases if "search" in c.nodeid)
    assert search_case.browser == "chromium"


def test_parse_junit_xml_browser_from_param_suffix():
    """无 <system-out>[BROWSER=] 时，从 [chromium-xxx] 后缀提取。"""
    xml = """<?xml version="1.0"?>
    <testsuites><testsuite tests="1" failures="0" errors="0" skipped="0" time="1">
      <testcase classname="tests.x.TestY" name="test_z[firefox-小米]" file="tests/x.py" line="1" time="1"/>
    </testsuite></testsuites>"""
    suite, cases = _parse(xml)
    assert cases[0].browser == "firefox"


def test_parse_junit_xml_nodeid_format():
    suite, cases = _parse(JUNIT_XML_WITH_FAILURES)
    search_case = next(c for c in cases if "search" in c.nodeid)
    assert search_case.nodeid == "tests/product/test_search.py::TestSearchPositive::test_search_valid_keyword_shows_results[chromium-手机]"


# ============ ui_repair_report.md 解析 ============


DIAGNOSE_MD = """# UI 失败诊断报告

**总失败数：** 2

## 概览

| 维度 | 值 |
|------|-----|
| 分类：SCRIPT_ERROR | 2 |
| 根因：missing_async_list_wait | 2 |
| 已应用 AST 修复 | 1 |
| 验证通过 | 1 |
| 验证失败 → 升级为 assertion_mismatch | 0 |

## 失败明细

### 1. `tests/x.py::TestY::test_a[chromium-手机]`

- **失败阶段：** call
- **分类：** SCRIPT_ERROR（置信度 0.65）
- **信号：** native AssertionError (business assertion)
- **根因：** missing_async_list_wait（策略：ast_rewrite）
- **证据：** reason=...
- **修复：** 已修改 `/path/to/search_result_page.py`
- **备份：** `/path/to/search_result_page.py.bak`
- **验证：** passed（15.4s）
- **原始错误：** `AssertionError: 搜索 '手机' 应返回商品`

### 2. `tests/x.py::TestY::test_b[chromium-手表]`

- **失败阶段：** call
- **分类：** SCRIPT_ERROR（置信度 0.65）
- **根因：** missing_async_list_wait（策略：ast_rewrite）
- **修复：** 未匹配到修改点
- **原始错误：** `AssertionError: 搜索 '手表' 应返回商品`
"""


def test_parse_diagnose_overview_counts():
    recs, overview = _parse_md(DIAGNOSE_MD)
    assert overview["分类：SCRIPT_ERROR"] == 2
    assert overview["根因：missing_async_list_wait"] == 2
    assert overview["已应用 AST 修复"] == 1
    assert overview["验证通过"] == 1


def test_parse_diagnose_records_count():
    recs, _ = _parse_md(DIAGNOSE_MD)
    assert len(recs) == 2


def test_parse_diagnose_record_fields():
    recs, _ = _parse_md(DIAGNOSE_MD)
    first = recs[0]
    assert first.nodeid == "tests/x.py::TestY::test_a[chromium-手机]"
    assert first.failure_stage == "call"
    assert first.category == "SCRIPT_ERROR"
    assert first.confidence == 0.65
    assert first.root_cause == "missing_async_list_wait"
    assert first.fix_strategy == "ast_rewrite"
    assert first.fix_applied is True
    assert first.fix_target_file == "/path/to/search_result_page.py"
    assert first.verify_status == "passed"
    assert first.verify_duration == 15.4
    assert first.raw_error == "AssertionError: 搜索 '手机' 应返回商品"


def test_parse_diagnose_record_no_fix():
    recs, _ = _parse_md(DIAGNOSE_MD)
    second = recs[1]
    assert second.fix_applied is False
    assert second.verify_status is None


def test_parse_diagnose_upgrade_marker():
    """测试升级标记解析。"""
    md = """# UI 失败诊断报告

**总失败数：** 1

## 概览

| 维度 | 值 |
|------|-----|
| 验证失败 → 升级为 assertion_mismatch | 1 |

## 失败明细

### 1. `tests/x.py::TestY::test_a`

- **分类：** SCRIPT_ERROR（置信度 0.65）
- **根因：** assertion_mismatch（策略：none）
- **根因升级：** assertion_mismatch
- **升级原因：** 已应用智能等待，verify 重跑仍失败
- **原始错误：** `AssertionError: ...`
"""
    recs, overview = _parse_md(md)
    assert overview["验证失败 → 升级为 assertion_mismatch"] == 1
    assert recs[0].upgraded_root_cause == "assertion_mismatch"
    assert "verify 重跑仍失败" in (recs[0].upgrade_reason or "")


# ============ nodeid slug ============


def test_nodeid_slug_chinese_param():
    """中文参数化后缀被清掉，只保留方法名 slug。"""
    slug = _nodeid_slug("tests/x.py::TestY::test_z[chromium-手机]")
    assert slug == "test-z"


def test_nodeid_slug_no_param():
    slug = _nodeid_slug("tests/x.py::TestY::test_login_valid")
    assert slug == "test-login-valid"


def test_nodeid_slug_special_chars():
    slug = _nodeid_slug("tests/x.py::TestY::test_login_with_special_chars")
    assert slug == "test-login-with-special-chars"


# ============ 历史 JSON ============


def test_load_history_valid(tmp_path):
    p = tmp_path / "h.json"
    p.write_text('[{"timestamp": "2026-06-20", "pass_rate": 90.0}]', encoding="utf-8")
    h = load_history(p)
    assert len(h) == 1
    assert h[0]["pass_rate"] == 90.0


def test_load_history_missing(tmp_path):
    h = load_history(tmp_path / "no.json")
    assert h == []


def test_load_history_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not json", encoding="utf-8")
    assert load_history(p) == []


# ============ fixtures / helpers ============


def _parse(xml_text: str):
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml_text)
        path = Path(f.name)
    try:
        return parse_junit_xml(path)
    finally:
        path.unlink()


def _parse_md(text: str):
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(text)
        path = Path(f.name)
    try:
        return parse_diagnose_md(path)
    finally:
        path.unlink()
