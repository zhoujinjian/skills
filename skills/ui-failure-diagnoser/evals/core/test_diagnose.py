"""Smoke tests for diagnose.py — orchestration integration."""
import sys
import textwrap
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import diagnose


# ============ JUnit XML 解析 ============

def test_parse_junit_xml_extracts_failure_message_and_traceback(tmp_path):
    xml = tmp_path / "report.xml"
    xml.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<testsuites>\n'
        '  <testsuite name="pytest" errors="0" failures="1" tests="1">\n'
        '    <testcase classname="tests.auth.test_login.TestLogin" name="test_login_a[chromium]" time="3.0">\n'
        '      <failure message="TimeoutError: 10000ms">traceback line 1\ntraceback line 2</failure>\n'
        '    </testcase>\n'
        '  </testsuite>\n'
        '</testsuites>'
    )
    records = diagnose.parse_junit_xml(xml)
    assert len(records) == 1
    r = records[0]
    assert "test_login_a" in r.nodeid
    assert r.message == "TimeoutError: 10000ms"
    assert "traceback line 1" in r.traceback
    assert r.classname == "tests.auth.test_login.TestLogin"
    assert r.testname == "test_login_a[chromium]"


def test_parse_junit_xml_returns_empty_when_no_failures(tmp_path):
    xml = tmp_path / "ok.xml"
    xml.write_text('<testsuites><testsuite failures="0" tests="1">'
                   '<testcase classname="x" name="t"/></testsuite></testsuites>')
    assert diagnose.parse_junit_xml(xml) == []


def test_parse_junit_xml_handles_error_tag_as_failure(tmp_path):
    xml = tmp_path / "err.xml"
    xml.write_text('<testsuites><testsuite errors="1" failures="0" tests="1">'
                   '<testcase classname="x" name="t"><error message="setup err">tb</error>'
                   '</testcase></testsuite></testsuites>')
    records = diagnose.parse_junit_xml(xml)
    assert len(records) == 1
    assert records[0].message == "setup err"


# ============ nodeid → slug ============

def test_nodeid_to_slug_replaces_special_chars():
    slug = diagnose.nodeid_to_slug("tests/auth/test_login.py::TestLogin::test_a[chromium]")
    # :: / / / [ ] 应被替换为 -
    assert "::" not in slug
    assert "[" not in slug
    assert "]" not in slug
    assert "/" not in slug
    # . 和 _ 应保留（pytest-playwright slug 规则）
    assert "test_login.py" in slug
    assert "TestLogin" in slug
    assert "chromium" in slug


# ============ artifacts 索引 ============

def test_index_artifacts_finds_existing_files(tmp_path):
    artifacts = tmp_path / "artifacts"
    (artifacts / "console-logs").mkdir(parents=True)
    (artifacts / "page-source").mkdir(parents=True)

    nodeid = "tests/auth/test_login.py::TestLogin::test_a"
    slug = diagnose.nodeid_to_slug(nodeid)

    (artifacts / "console-logs" / f"{slug}.log").write_text("log")
    (artifacts / "page-source" / f"{slug}.html").write_text("<html/>")
    raw_subdir = artifacts / "pytest-raw" / slug
    raw_subdir.mkdir(parents=True)
    (raw_subdir / "trace.zip").write_text("zip")

    index = diagnose.index_artifacts(artifacts, [nodeid])
    entry = index[nodeid]
    assert entry["console_log"] is not None
    assert entry["page_source"] is not None
    assert entry["trace_zip"] is not None


def test_index_artifacts_returns_none_for_missing(tmp_path):
    artifacts = tmp_path / "artifacts"
    (artifacts / "console-logs").mkdir(parents=True)
    index = diagnose.index_artifacts(artifacts, ["unknown_nodeid"])
    assert index["unknown_nodeid"]["console_log"] is None
    assert index["unknown_nodeid"]["page_source"] is None


# ============ pages 扫描 ============

def test_find_files_with_pattern(tmp_path):
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "a.py").write_text("timeout=10000")
    (pages / "b.py").write_text("# nothing")
    (pages / "sub").mkdir()
    (pages / "sub" / "c.py").write_text("self._x = page.locator\ntimeout=10000")

    hits = diagnose.find_files_with_pattern(pages, "timeout=10000")
    assert len(hits) == 2
    rel_paths = {p.relative_to(pages) for p in hits}
    assert Path("a.py") in rel_paths
    assert Path("sub/c.py") in rel_paths


def test_find_pages_dir_returns_existing(tmp_path):
    (tmp_path / "pages").mkdir()
    assert diagnose.find_pages_dir(tmp_path) is not None
    assert diagnose.find_pages_dir(tmp_path, "po") is None


# ============ 编排：mock 单元函数 ============

def _make_failure_record(**kwargs):
    return diagnose.FailureRecord(
        nodeid=kwargs.get("nodeid", "tests/x.py::TestX::test_a"),
        classname=kwargs.get("classname", "tests.x.TestX"),
        testname=kwargs.get("testname", "test_a"),
        message=kwargs.get("message", "TimeoutError"),
        traceback=kwargs.get("traceback", ""),
        failure_stage=kwargs.get("failure_stage", "call"),
    )


def test_diagnose_end_to_end_no_fix(tmp_path):
    """no-fix 模式：只 classify + locate，不调 apply_fix。"""
    junit = tmp_path / "r.xml"
    junit.write_text('<testsuites><testsuite failures="1" tests="1">'
                     '<testcase classname="t" name="t"><failure message="m">tb</failure>'
                     '</testcase></testsuite></testsuites>')
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    project = tmp_path / "proj"
    (project / "pages").mkdir(parents=True)

    with mock.patch("diagnose.classify") as mc, mock.patch("diagnose.locate") as ml:
        mc.return_value = mock.Mock(category="TIMEOUT_ERROR", confidence=0.9, signals=["timeout"])
        ml.return_value = mock.Mock(
            root_cause="insufficient_wait",
            fix_strategy="ast_rewrite",
            evidence={"original_timeout_ms": 10000, "suggested_timeout_ms": 30000},
        )
        records = diagnose.diagnose(
            junit_xml=junit,
            artifacts_dir=artifacts,
            project_dir=project,
            apply_fixes=False,
        )

    assert len(records) == 1
    assert records[0].classified is not None
    assert records[0].root_cause is not None
    assert records[0].fix_applied is None  # no-fix 模式


def test_diagnose_applies_insufficient_wait_fix(tmp_path):
    """对 ast_rewrite 的 insufficient_wait 根因，调起 apply_insufficient_wait_fix。"""
    junit = tmp_path / "r.xml"
    junit.write_text('<testsuites><testsuite failures="1" tests="1">'
                     '<testcase classname="t" name="t"><failure message="m">tb</failure>'
                     '</testcase></testsuite></testsuites>')
    project = tmp_path / "proj"
    pages = project / "pages"
    pages.mkdir(parents=True)
    base_page = pages / "base_page.py"
    base_page.write_text("class BasePage:\n    def f(self, timeout=10000): pass\n")

    with mock.patch("diagnose.classify") as mc, mock.patch("diagnose.locate") as ml:
        mc.return_value = mock.Mock(category="TIMEOUT_ERROR", confidence=0.9, signals=[])
        ml.return_value = mock.Mock(
            root_cause="insufficient_wait",
            fix_strategy="ast_rewrite",
            evidence={"original_timeout_ms": 10000, "suggested_timeout_ms": 30000},
        )
        records = diagnose.diagnose(
            junit_xml=junit,
            artifacts_dir=tmp_path / "artifacts_empty",
            project_dir=project,
            apply_fixes=True,
            dry_run=False,
        )

    assert len(records) == 1
    rec = records[0]
    assert rec.fix_applied is not None
    assert rec.fix_applied.modified is True
    # 验证文件被修改
    assert "timeout=30000" in base_page.read_text()
    assert rec.fix_target_file == base_page


def test_diagnose_dry_run_does_not_write(tmp_path):
    """dry-run 模式：fix_applied.modified=True 但文件未变。"""
    junit = tmp_path / "r.xml"
    junit.write_text('<testsuites><testsuite failures="1" tests="1">'
                     '<testcase classname="t" name="t"><failure message="m">tb</failure>'
                     '</testcase></testsuite></testsuites>')
    project = tmp_path / "proj"
    pages = project / "pages"
    pages.mkdir(parents=True)
    base_page = pages / "base_page.py"
    original = "class BasePage:\n    def f(self, timeout=10000): pass\n"
    base_page.write_text(original)

    with mock.patch("diagnose.classify") as mc, mock.patch("diagnose.locate") as ml:
        mc.return_value = mock.Mock(category="TIMEOUT_ERROR", confidence=0.9, signals=[])
        ml.return_value = mock.Mock(
            root_cause="insufficient_wait",
            fix_strategy="ast_rewrite",
            evidence={"original_timeout_ms": 10000, "suggested_timeout_ms": 30000},
        )
        diagnose.diagnose(
            junit_xml=junit,
            artifacts_dir=tmp_path / "artifacts_empty",
            project_dir=project,
            apply_fixes=True,
            dry_run=True,
        )

    assert base_page.read_text() == original


# ============ 报告生成 ============

def test_generate_report_creates_markdown_with_summary(tmp_path):
    output = tmp_path / "report.md"
    rec = diagnose.DiagnosisRecord(
        failure=_make_failure_record(),
        classified=mock.Mock(category="TIMEOUT_ERROR", confidence=0.9, signals=["timeout"]),
        root_cause=mock.Mock(
            root_cause="insufficient_wait",
            fix_strategy="ast_rewrite",
            evidence={"original_timeout_ms": 10000, "suggested_timeout_ms": 30000},
        ),
        fix_applied=mock.Mock(modified=True, backup_path=Path("/tmp/x.py.bak")),
        fix_target_file=Path("/tmp/x.py"),
    )
    diagnose.generate_report([rec], output)
    content = output.read_text()
    assert "UI 失败诊断报告" in content
    assert "TIMEOUT_ERROR" in content
    assert "insufficient_wait" in content
    assert "已应用 AST 修复" in content


def test_generate_report_handles_no_records(tmp_path):
    output = tmp_path / "empty.md"
    diagnose.generate_report([], output)
    content = output.read_text()
    assert "总失败数：** 0" in content or "总失败数： 0" in content


# ============ CLI ============

def test_main_returns_2_when_junit_missing(tmp_path):
    rc = diagnose.main([
        "--junit-xml", str(tmp_path / "no.xml"),
        "--artifacts-dir", str(tmp_path),
        "--project-dir", str(tmp_path),
    ])
    assert rc == 2


def test_main_end_to_end_writes_report(tmp_path, capsys):
    """完整 CLI 端到端：生成报告文件、退出 0。"""
    junit = tmp_path / "r.xml"
    junit.write_text('<testsuites><testsuite failures="1" tests="1">'
                     '<testcase classname="t" name="t"><failure message="TimeoutError">tb</failure>'
                     '</testcase></testsuite></testsuites>')
    project = tmp_path / "proj"
    (project / "pages").mkdir(parents=True)

    output = tmp_path / "out.md"
    rc = diagnose.main([
        "--junit-xml", str(junit),
        "--artifacts-dir", str(tmp_path),
        "--project-dir", str(project),
        "--output", str(output),
        "--no-fix",
    ])
    assert rc == 0
    assert output.exists()
    captured = capsys.readouterr()
    assert "共诊断 1 条失败" in captured.out


# ============ 类别相关修复（ENV/DATA/BUG/SCRIPT）============

def test_diagnose_dispatches_env_error_repair(tmp_path):
    """ENV_ERROR 失败 → 调用 env_repair。"""
    junit = tmp_path / "r.xml"
    junit.write_text('<testsuites><testsuite failures="1" tests="1">'
                     '<testcase classname="t" name="t">'
                     '<failure message="Executable doesn\'t exist at chromium-1234">tb</failure>'
                     '</testcase></testsuite></testsuites>')
    project = tmp_path / "proj"
    (project / "pages").mkdir(parents=True)

    records = diagnose.diagnose(
        junit_xml=junit,
        artifacts_dir=tmp_path / "artifacts",
        project_dir=project,
        apply_fixes=True,
        dry_run=True,  # 不真跑 playwright install
    )
    assert len(records) == 1
    rec = records[0]
    assert rec.classified.category == "ENV_ERROR"
    assert rec.category_repair is not None
    assert rec.category_repair["kind"] == "env"


def test_diagnose_dispatches_data_error_repair(tmp_path):
    """DATA_ERROR（fixture 失败）→ 调用 data_repair。"""
    junit = tmp_path / "r.xml"
    junit.write_text('<testsuites><testsuite failures="1" tests="1">'
                     '<testcase classname="t" name="t">'
                     '<failure message="fixture \'registered_user\' not found">tb</failure>'
                     '</testcase></testsuite></testsuites>')
    project = tmp_path / "proj"
    (project / "pages").mkdir(parents=True)

    records = diagnose.diagnose(
        junit_xml=junit,
        artifacts_dir=tmp_path / "artifacts",
        project_dir=project,
        apply_fixes=True,
        dry_run=True,
    )
    assert len(records) == 1
    rec = records[0]
    # fixture 失败归类为 DATA_ERROR（由 classify_failure 判定）
    assert rec.classified.category == "DATA_ERROR"
    assert rec.category_repair is not None
    assert rec.category_repair["kind"] == "data"


def test_diagnose_dispatches_script_error_typo(tmp_path):
    """SCRIPT_ERROR（AttributeError clcik）→ apply_method_typo_fix。"""
    junit = tmp_path / "r.xml"
    junit.write_text('<testsuites><testsuite failures="1" tests="1">'
                     '<testcase classname="t" name="t">'
                     '<failure message="AttributeError: \'Locator\' object has no attribute \'clcik\'">tb</failure>'
                     '</testcase></testsuite></testsuites>')
    project = tmp_path / "proj"
    pages = project / "pages"
    pages.mkdir(parents=True)
    (pages / "login_page.py").write_text(
        "class LoginPage:\n"
        "    def submit(self):\n"
        "        self._btn.clcik()\n"
    )

    records = diagnose.diagnose(
        junit_xml=junit,
        artifacts_dir=tmp_path / "artifacts",
        project_dir=project,
        apply_fixes=True,
        dry_run=True,
    )
    assert len(records) == 1
    rec = records[0]
    assert rec.classified.category == "SCRIPT_ERROR"
    assert rec.category_repair is not None
    assert rec.category_repair["kind"] == "script"
    assert rec.category_repair["subkind"] == "method_typo"
    assert rec.category_repair["typo"] == "clcik"
    assert rec.category_repair["correct"] == "click"


def test_diagnose_no_category_repair_when_apply_fixes_false(tmp_path):
    """apply_fixes=False 时不触发类别修复。"""
    junit = tmp_path / "r.xml"
    junit.write_text('<testsuites><testsuite failures="1" tests="1">'
                     '<testcase classname="t" name="t">'
                     '<failure message="Browser has been closed">tb</failure>'
                     '</testcase></testsuite></testsuites>')
    project = tmp_path / "proj"
    (project / "pages").mkdir(parents=True)

    records = diagnose.diagnose(
        junit_xml=junit,
        artifacts_dir=tmp_path / "artifacts",
        project_dir=project,
        apply_fixes=False,
    )
    assert len(records) == 1
    assert records[0].category_repair is None


def test_diagnose_category_repair_recorded_in_report(tmp_path):
    """报告里能看到类别修复记录。"""
    output = tmp_path / "report.md"
    rec = diagnose.DiagnosisRecord(
        failure=_make_failure_record(),
        classified=mock.Mock(category="SCRIPT_ERROR", confidence=0.9, signals=["AttributeError"]),
        category_repair={
            "kind": "script",
            "subkind": "method_typo",
            "typo": "clcik",
            "correct": "click",
            "target_file": Path("/tmp/login_page.py"),
            "result": mock.Mock(modified=True),
        },
    )
    diagnose.generate_report([rec], output)
    content = output.read_text()
    assert "脚本修复" in content
    assert "clcik" in content
    assert "click" in content
    assert "已应用类别修复" in content


# ============ missing_async_list_wait: AST 修复派发 ============

def test_apply_deterministic_fix_dispatches_async_wait_for_missing_async_list_wait(tmp_path):
    """root_cause=missing_async_list_wait 时调起 apply_async_wait_fix 修改 get_product_count."""
    # 构造 pages/ 结构
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "product").mkdir()
    (pages_dir / "product" / "search_result_page.py").write_text(textwrap.dedent("""
        from pages.base_page import BasePage
        class SearchResultPage(BasePage):
            def get_product_count(self) -> int:
                return self._product_cards.count()
    """))
    (pages_dir / "base_page.py").write_text(textwrap.dedent("""
        class BasePage:
            def __init__(self, page):
                self.page = page
    """))

    # 构造 record，root_cause 已是 missing_async_list_wait
    from apply_fix import FixResult
    from dataclasses import dataclass
    from pathlib import Path as PathCls

    rc = type("RC", (), {
        "root_cause": "missing_async_list_wait",
        "fix_strategy": "ast_rewrite",
        "evidence": {},
    })()
    failure = diagnose.FailureRecord(
        nodeid="tests/x.py::t", classname="x", testname="t",
        message="AssertionError: 搜索 '手表' 应返回商品，但结果数为 0",
        traceback="",
    )
    record = diagnose.DiagnosisRecord(failure=failure)
    record.root_cause = rc

    diagnose._apply_deterministic_fix(
        record=record, pages_dir=pages_dir, dry_run=False,
    )

    assert record.fix_applied is not None
    assert record.fix_applied.modified is True
    assert "_wait_for_product_list_loaded" in record.fix_applied.new_source
    # base_page 也应该被注入 helper
    assert "_wait_for_product_list_loaded" in \
           (pages_dir / "base_page.py").read_text()


# ============ Stage 2: verify 失败升级为 assertion_mismatch ============

def test_verify_failure_with_missing_async_list_wait_upgrades_to_assertion_mismatch(tmp_path):
    """missing_async_list_wait 修复后 verify 失败 → 升级为 assertion_mismatch + rollback."""
    from unittest import mock
    from apply_fix import FixResult

    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    src_file = pages_dir / "search_result_page.py"
    src_file.write_text(textwrap.dedent("""
        class SearchResultPage:
            def get_product_count(self):
                return self._product_cards.count()
    """))
    base_file = pages_dir / "base_page.py"
    base_file.write_text("class BasePage: pass\n")

    # 预先应用修复（直接走 apply_async_wait_fix）
    fix_result = diagnose.apply_async_wait_fix(
        source_path=src_file, base_page_path=base_file, backup=True,
    )
    assert fix_result.modified

    rc = type("RC", (), {
        "root_cause": "missing_async_list_wait",
        "fix_strategy": "ast_rewrite",
        "evidence": {},
    })()
    failure = diagnose.FailureRecord(
        nodeid="tests/x.py::t", classname="x", testname="t",
        message="AssertionError: 搜索 '手表' 应返回商品，但结果数为 0",
        traceback="",
    )
    record = diagnose.DiagnosisRecord(failure=failure)
    record.root_cause = rc
    record.fix_applied = fix_result
    record.fix_target_file = src_file

    # mock verify_single_test 返回 failed
    fake_verify = mock.Mock()
    fake_verify.status = "failed"
    fake_verify.duration_sec = 1.5

    with mock.patch.object(diagnose, "verify_single_test", return_value=fake_verify):
        diagnose._verify_and_maybe_rollback(
            record=record,
            project_dir=tmp_path,
            base_url=None,
            browser=None,
        )

    # 升级字段已设置
    assert record.upgraded_root_cause == "assertion_mismatch"
    assert record.upgrade_reason is not None
    assert "排查后端" in record.upgrade_reason or "异步加载" in record.upgrade_reason
    # rollback 已执行
    assert record.rolled_back is True
    # source 文件已恢复
    assert "_wait_for_product_list_loaded()" not in src_file.read_text()


def test_verify_failure_with_other_root_cause_does_not_upgrade(tmp_path):
    """非 missing_async_list_wait 的修复 verify 失败 → 只 rollback，不升级."""
    from unittest import mock
    from apply_fix import FixResult

    src_file = tmp_path / "f.py"
    src_file.write_text("x = 1\n")
    bak = tmp_path / "f.py.bak"
    bak.write_text("x = 1\n")

    rc = type("RC", (), {
        "root_cause": "insufficient_wait",
        "fix_strategy": "ast_rewrite",
        "evidence": {},
    })()
    failure = diagnose.FailureRecord(
        nodeid="tests/x.py::t", classname="x", testname="t",
        message="TimeoutError", traceback="",
    )
    record = diagnose.DiagnosisRecord(failure=failure)
    record.root_cause = rc
    record.fix_applied = FixResult(
        modified=True, new_source="x = 2\n", backup_path=bak,
    )
    record.fix_target_file = src_file

    fake_verify = mock.Mock()
    fake_verify.status = "failed"
    fake_verify.duration_sec = 1.0

    with mock.patch.object(diagnose, "verify_single_test", return_value=fake_verify):
        diagnose._verify_and_maybe_rollback(
            record=record,
            project_dir=tmp_path,
            base_url=None,
            browser=None,
        )

    # 不升级
    assert record.upgraded_root_cause is None
    # 仍 rollback
    assert record.rolled_back is True


# ============ 报告生成：assertion_mismatch 统计 + 渲染 ============

def test_generate_report_includes_assertion_mismatch_stats(tmp_path):
    """报告概览含「验证失败 → 升级为 assertion_mismatch」字段."""
    rc = type("RC", (), {
        "root_cause": "missing_async_list_wait",
        "fix_strategy": "ast_rewrite",
        "evidence": {},
    })()
    failure = diagnose.FailureRecord(
        nodeid="tests/x.py::t", classname="x", testname="t",
        message="AssertionError: 搜索 '手表' 应返回商品，但结果数为 0",
        traceback="",
    )
    record = diagnose.DiagnosisRecord(failure=failure)
    record.classified = type("C", (), {"category": "SCRIPT_ERROR", "confidence": 0.65, "signals": []})()
    record.root_cause = rc
    record.upgraded_root_cause = "assertion_mismatch"
    record.upgrade_reason = "已应用智能等待，verify 重跑仍失败。"
    record.rolled_back = True

    out = tmp_path / "report.md"
    diagnose.generate_report([record], out)

    text = out.read_text()
    assert "验证失败 → 升级为 assertion_mismatch" in text
    assert "assertion_mismatch" in text  # 根因分布中也要出现


def test_render_record_shows_upgrade_section(tmp_path):
    """明细中 assertion_mismatch 用例显示升级原因 + 建议."""
    rc = type("RC", (), {
        "root_cause": "missing_async_list_wait",
        "fix_strategy": "ast_rewrite",
        "evidence": {},
    })()
    failure = diagnose.FailureRecord(
        nodeid="tests/x.py::t", classname="x", testname="t",
        message="AssertionError: 搜索 '手表' 应返回商品，但结果数为 0",
        traceback="",
    )
    record = diagnose.DiagnosisRecord(failure=failure)
    record.classified = type("C", (), {"category": "SCRIPT_ERROR", "confidence": 0.65, "signals": []})()
    record.root_cause = rc
    record.upgraded_root_cause = "assertion_mismatch"
    record.upgrade_reason = "已应用智能等待，verify 重跑仍失败。建议排查后端搜索接口。"
    record.rolled_back = True

    lines = diagnose._render_record(1, record)
    text = "\n".join(lines)

    assert "assertion_mismatch" in text
    assert "已应用智能等待" in text
    assert "建议排查后端" in text
