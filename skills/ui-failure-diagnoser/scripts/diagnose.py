"""diagnose.py — ui-failure-diagnoser 主入口

编排流程：
    JUnit XML + artifacts/ + project pages/ → classify → locate → apply_fix → verify → report

CLI:
    python3 diagnose.py \\
        --junit-xml ./test-results/report.xml \\
        --artifacts-dir ./test-results/artifacts \\
        --project-dir ./shop-lab-ui-test \\
        [--output ./test-results/ui_repair_report.md] \\
        [--verify] \\
        [--dry-run] \\
        [--no-fix] \\
        [--base-url http://localhost:3000] \\
        [--browser chromium]
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# 同目录下的兄弟模块
sys.path.insert(0, str(Path(__file__).parent))
from apply_fix import (  # noqa: E402
    apply_async_wait_fix,
    apply_deprecated_api_fix,
    apply_iframe_switch_fix,
    apply_insufficient_wait_fix,
    apply_method_typo_fix,
    rollback,
    suggest_method_correction,
)
from audit_log import AuditLogger  # noqa: E402
from bug_repair import diagnose_bug_failure, execute_bug_repair  # noqa: E402
from classify_failure import classify  # noqa: E402
from data_repair import diagnose_data_failure, execute_data_repair  # noqa: E402
from env_repair import diagnose_env_failure, execute_env_repair  # noqa: E402
from locate_root_cause import locate  # noqa: E402
from verify_fix import verify_single_test  # noqa: E402


# ============ 数据结构 ============

@dataclass
class FailureRecord:
    """从 JUnit XML 解析出的单条失败记录。"""
    nodeid: str
    classname: str
    testname: str
    message: str
    traceback: str
    failure_stage: str = "call"  # pytest_runtest_makereport 默认 call


@dataclass
class DiagnosisRecord:
    """单条失败的完整诊断结果。"""
    failure: FailureRecord
    classified: object | None = None  # ClassifiedFailure
    root_cause: object | None = None  # RootCause
    fix_applied: object | None = None  # FixResult
    fix_target_file: Path | None = None
    verify_result: object | None = None  # VerifyResult
    rolled_back: bool = False
    # 扩展：4 类非 ast_rewrite 修复（env / data / bug / script）
    category_repair: dict | None = None  # {"kind": "env"|"data"|"bug"|"script", "plan": ..., "result": ...}
    # 扩展：verify 失败升级（missing_async_list_wait → assertion_mismatch）
    upgraded_root_cause: str | None = None
    upgrade_reason: str | None = None


# ============ JUnit XML 解析 ============

def parse_junit_xml(junit_path: Path) -> list[FailureRecord]:
    """从 JUnit XML 提取所有失败用例。

    支持两种 failure 标记：
        <testcase><failure message="...">traceback...</failure></testcase>
        <testcase><error message="...">traceback...</error></testcase>

    Returns:
        list[FailureRecord]，每个含 nodeid / message / traceback / failure_stage
    """
    tree = ET.parse(junit_path)
    root = tree.getroot()
    records: list[FailureRecord] = []

    for tc in root.iter("testcase"):
        classname = tc.get("classname", "")
        testname = tc.get("name", "")
        nodeid = _build_nodeid(classname, testname)

        # 检查 failure / error 子元素
        for child in tc:
            if child.tag in ("failure", "error"):
                message = child.get("message", "") or ""
                traceback = (child.text or "").strip()
                stage = "setup" if child.tag == "error" and "setup" in message.lower() else "call"
                records.append(FailureRecord(
                    nodeid=nodeid,
                    classname=classname,
                    testname=testname,
                    message=message,
                    traceback=traceback,
                    failure_stage=stage,
                ))
                break  # 一个 testcase 只取第一个 failure

    return records


def _build_nodeid(classname: str, testname: str) -> str:
    """根据 classname + testname 重建 pytest nodeid。

    pytest nodeid 格式：<file_path>::<ClassName>::<test_method>[<params>]
    classname 形如 "ui-test.tests.auth.test_login.TestLogin"
    → nodeid = "ui-test/tests/auth/test_login.py::TestLogin::test_xxx"
    """
    if not classname:
        return testname
    parts = classname.split(".")
    if len(parts) >= 2:
        # 最后一段是类名，前几段是模块路径
        class_name = parts[-1]
        module_path = ".".join(parts[:-1])
        file_path = module_path.replace(".", "/") + ".py"
        return f"{file_path}::{class_name}::{testname}" if testname else file_path
    # 兜底
    return f"{classname.replace('.', '/')}.py::{testname}" if testname else classname


# ============ artifacts 索引 ============

def nodeid_to_slug(nodeid: str) -> str:
    """pytest-playwright 目录 slug 规则：把非字母数字字符替换为 -。

    用于在 artifacts/<subdir>/ 下找到对应的文件。
    """
    # 移除参数化方括号内容会简化匹配，但实际 slug 是包含的，这里保留
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", nodeid)
    # 折叠连续 -
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def index_artifacts(artifacts_dir: Path, nodeids: list[str]) -> dict[str, dict]:
    """为每个 nodeid 找到 console-log / page-source 文件路径。

    匹配策略：
        1. 优先按 nodeid 直接生成的 slug 找（精确）
        2. 失败则 glob 子目录，按 testname 子串匹配（容忍 prefix 差异）

    Returns:
        {nodeid: {"console_log": Path|None, "page_source": Path|None, "trace_zip": Path|None}}
    """
    console_dir = artifacts_dir / "console-logs"
    page_source_dir = artifacts_dir / "page-source"
    pytest_raw_dir = artifacts_dir / "pytest-raw"

    # 预扫描每个子目录，构建按 normalized name 索引
    console_index = _index_artifact_subdir(console_dir, ".log")
    page_source_index = _index_artifact_subdir(page_source_dir, ".html")
    raw_index = _index_pytest_raw(pytest_raw_dir)

    index: dict[str, dict] = {}
    for nodeid in nodeids:
        slug = nodeid_to_slug(nodeid)
        norm = _normalize_for_match(nodeid)

        entry = {
            "console_log": _lookup_artifact(console_index, slug, norm),
            "page_source": _lookup_artifact(page_source_index, slug, norm),
            "trace_zip": _lookup_trace(raw_index, slug, norm),
        }
        index[nodeid] = entry
    return index


def _index_artifact_subdir(dir_path: Path, suffix: str) -> dict[str, list[Path]]:
    """扫描子目录，按 normalized 文件名建索引（容忍 slug 差异）。

    Returns:
        {normalized_name: [path1, path2, ...]}
    """
    if not dir_path.is_dir():
        return {}
    index: dict[str, list[Path]] = {}
    for p in dir_path.iterdir():
        if not p.is_file() or p.suffix != suffix:
            continue
        stem = p.stem  # 去掉后缀
        norm = _normalize_for_match(stem)
        index.setdefault(norm, []).append(p)
    return index


def _index_pytest_raw(dir_path: Path) -> dict[str, list[Path]]:
    """扫描 pytest-raw 子目录，每个子目录可能含 trace.zip / video.webm。

    Returns:
        {normalized_dir_name: [trace.zip path]}
    """
    if not dir_path.is_dir():
        return {}
    index: dict[str, list[Path]] = {}
    for sub in dir_path.iterdir():
        if not sub.is_dir():
            continue
        trace = sub / "trace.zip"
        if trace.exists():
            norm = _normalize_for_match(sub.name)
            index.setdefault(norm, []).append(trace)
    return index


def _normalize_for_match(s: str) -> str:
    """把字符串归一化为匹配键：去特殊字符、统一小写、折叠分隔符。

    "tests/auth/test_login.py::TestLogin::test_a[chromium]"
    "tests-auth-test_login.py-TestLogin-test_a-chromium"
    两者都归一化为 "testsauthtestloginpytestlogintestlogintestachromium"
    """
    return re.sub(r"[^A-Za-z0-9]", "", s).lower()


def _lookup_artifact(
    index: dict[str, list[Path]],
    slug: str,
    nodeid_norm: str,
) -> Path | None:
    """先精确 slug 匹配，失败则子串匹配（nodeid_norm 含 slug_norm 时命中）。"""
    if not index:
        return None
    # 精确匹配 slug 归一化
    slug_norm = _normalize_for_match(slug)
    if slug_norm in index:
        return index[slug_norm][0]
    # 子串匹配：nodeid 归一化后以某个 key 结尾（或包含）
    for key, paths in index.items():
        if key and (nodeid_norm.endswith(key) or key in nodeid_norm):
            return paths[0]
    return None


def _lookup_trace(
    index: dict[str, list[Path]],
    slug: str,
    nodeid_norm: str,
) -> Path | None:
    """trace.zip 的查找，同 _lookup_artifact 但针对 pytest-raw 子目录。"""
    return _lookup_artifact(index, slug, nodeid_norm)


# ============ pages 目录扫描 ============

def find_pages_dir(project_dir: Path, pages_subdir: str = "pages") -> Path | None:
    """定位 pages 目录，支持自定义子目录名。"""
    candidate = project_dir / pages_subdir
    return candidate if candidate.is_dir() else None


def find_files_with_pattern(pages_dir: Path, pattern: str) -> list[Path]:
    """扫描 pages/**/*.py，返回源码中包含 pattern 的文件列表。"""
    hits: list[Path] = []
    for py in pages_dir.rglob("*.py"):
        try:
            source = py.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if pattern in source:
            hits.append(py)
    return hits


# ============ 编排主流程 ============

def diagnose(
    junit_xml: Path,
    artifacts_dir: Path,
    project_dir: Path,
    pages_subdir: str = "pages",
    apply_fixes: bool = True,
    dry_run: bool = False,
    verify: bool = False,
    base_url: str | None = None,
    browser: str | None = None,
    audit_log_path: Path | None = None,
    conftest_path: Path | None = None,
    pages_yaml_path: Path | None = None,
) -> list[DiagnosisRecord]:
    """主编排函数。

    Args:
        junit_xml: JUnit XML 文件路径
        artifacts_dir: artifacts 根目录
        project_dir: 项目根（用于找 pages/）
        pages_subdir: pages 子目录名（默认 "pages"）
        apply_fixes: 是否应用 AST 修复（False 时只 classify + locate）
        dry_run: True 时不写文件（apply_fix 的 dry_run=True）
        verify: 是否在每个修复后 verify_single_test
        base_url: 传给 verify_single_test
        browser: 传给 verify_single_test
        audit_log_path: env/data/bug 副作用操作的审计日志路径（默认 <project>/.ui-failure-diagnoser/audit.log）
        conftest_path: 项目的 tests/conftest.py（bug_repair 注入 marker 需要）
        pages_yaml_path: 项目 pages.yaml（LOCATOR_ERROR 时供 pages_yaml_resolver 对比）

    Returns:
        list[DiagnosisRecord]，顺序与 JUnit XML 中的失败用例一致
    """
    failures = parse_junit_xml(junit_xml)
    if not failures:
        return []

    nodeids = [f.nodeid for f in failures]
    artifacts_index = index_artifacts(artifacts_dir, nodeids)
    pages_dir = find_pages_dir(project_dir, pages_subdir)

    # 初始化审计日志（env/data/bug 的副作用操作都会记录）
    effective_audit_path = audit_log_path or (project_dir / ".ui-failure-diagnoser" / "audit.log")
    logger = AuditLogger(log_path=effective_audit_path) if apply_fixes else None

    records: list[DiagnosisRecord] = []

    for failure in failures:
        record = DiagnosisRecord(failure=failure)

        # 加载 artifacts 内容（classify 需要 page_source/console_log 文本）
        artifact_paths = artifacts_index.get(failure.nodeid, {})
        page_source_text = _read_text(artifact_paths.get("page_source"))
        console_log_text = _read_text(artifact_paths.get("console_log"))

        # Step 1: classify
        classified = classify(
            nodeid=failure.nodeid,
            message=failure.message,
            traceback=failure.traceback,
            page_source=page_source_text,
            console_log=console_log_text,
            failure_stage=failure.failure_stage,
        )
        record.classified = classified

        # Step 2: locate root cause（TIMEOUT/LOCATOR 才有意义）
        # iframe_contents MVP 不解析（需要额外爬取），传 None
        root_cause = locate(classified, page_source=page_source_text, iframe_contents=None)
        record.root_cause = root_cause

        # Step 3a: apply_fix（仅对 ast_rewrite 策略，即 TIMEOUT/LOCATOR）
        if apply_fixes and root_cause and root_cause.fix_strategy == "ast_rewrite" and pages_dir:
            _apply_deterministic_fix(
                record=record,
                pages_dir=pages_dir,
                dry_run=dry_run,
            )

        # Step 3b: 类别相关修复（ENV/DATA/BUG/SCRIPT）
        # 与 ast_rewrite 互补：env/data/bug 没有 root_cause（走另外的判定路径）
        if apply_fixes and logger:
            _apply_category_repair(
                record=record,
                project_dir=project_dir,
                pages_dir=pages_dir,
                console_log_text=console_log_text,
                page_source_text=page_source_text,
                logger=logger,
                conftest_path=conftest_path,
                pages_yaml_path=pages_yaml_path,
                dry_run=dry_run,
            )

        # Step 4: verify（仅在 ast_rewrite 修复成功后）
        if verify and record.fix_applied and record.fix_applied.modified and not dry_run:
            _verify_and_maybe_rollback(
                record=record,
                project_dir=project_dir,
                base_url=base_url,
                browser=browser,
            )

        records.append(record)

    return records


def _read_text(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _apply_deterministic_fix(
    record: DiagnosisRecord,
    pages_dir: Path,
    dry_run: bool,
) -> None:
    """根据 root_cause 类型调起对应的 AST 修复。"""
    rc = record.root_cause
    assert rc is not None

    if rc.root_cause == "insufficient_wait":
        original = rc.evidence.get("original_timeout_ms", 10000)
        suggested = rc.evidence.get("suggested_timeout_ms", 30000)
        # 扫描所有含 timeout=<original> 的 pages 文件
        candidates = find_files_with_pattern(pages_dir, f"timeout={original}")
        if not candidates:
            return
        # MVP：修改第一个匹配（通常 base_page.py）
        target = candidates[0]
        record.fix_target_file = target
        record.fix_applied = apply_insufficient_wait_fix(
            source_path=target,
            original_timeout_ms=original,
            suggested_timeout_ms=suggested,
            dry_run=dry_run,
        )

    elif rc.root_cause == "missing_iframe_switch":
        target_var = _infer_target_var_from_locator_hint(rc.evidence.get("locator_hint", ""))
        iframe_css = rc.evidence.get("iframe_locator", "")
        if not target_var or not iframe_css:
            return
        # 找到含 self.<target_var> 的文件
        candidates = find_files_with_pattern(pages_dir, f"self.{target_var}")
        if not candidates:
            return
        target = candidates[0]
        record.fix_target_file = target
        record.fix_applied = apply_iframe_switch_fix(
            source_path=target,
            target_var=target_var,
            iframe_css=iframe_css,
            dry_run=dry_run,
        )

    elif rc.root_cause == "missing_async_list_wait":
        # 找含 def get_product_count 的 page 文件
        candidates = find_files_with_pattern(pages_dir, "def get_product_count")
        if not candidates:
            return
        target = candidates[0]
        # 找 base_page.py（class BasePage 所在文件）
        base_candidates = find_files_with_pattern(pages_dir, "class BasePage")
        if not base_candidates:
            return
        base_page = base_candidates[0]
        record.fix_target_file = target
        record.fix_applied = apply_async_wait_fix(
            source_path=target,
            base_page_path=base_page,
            dry_run=dry_run,
        )


def _infer_target_var_from_locator_hint(locator_hint: str) -> str:
    """从 locator_hint 推断 page 对象上的目标属性名。

    MVP 策略：
        get_by_placeholder("账号") → _account_input / _username_input（不精确）
        对于中文 placeholder，简单返回 "_input" 后缀；找不到则返回空。
    实际生产可由 locate_root_cause.evidence 直接携带 target_var。
    """
    if not locator_hint:
        return ""
    # 提取核心文本（中文/英文）
    m = re.search(r'get_by_(?:placeholder|label|text|test_id)\(["\'](.+?)["\']', locator_hint)
    if not m:
        return ""
    text = m.group(1)
    # 中文 → 拼音简化（MVP 直接用原文转 slug）
    slug = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return f"_{slug}_input" if slug else ""


# ============ 类别相关修复：ENV / DATA / BUG / SCRIPT ============

# AttributeError 的属性名提取（用于 SCRIPT_ERROR 的 method_typo 推断）
_ATTR_NOT_FOUND_PATTERN = re.compile(
    r"AttributeError: ['\"](?P<obj>[^'\"]+)['\"] object has no attribute ['\"](?P<attr>[\w]+)['\"]",
)

# Playwright DeprecationWarning 提取
_DEPRECATED_PATTERN = re.compile(
    r"DeprecationWarning:[^\n]*?(?P<old>[\w_]+)\(\)[^\n]*?deprecated",
    re.IGNORECASE,
)


def _apply_category_repair(
    record: DiagnosisRecord,
    project_dir: Path,
    pages_dir: Path | None,
    console_log_text: str | None,
    page_source_text: str | None,
    logger: AuditLogger,
    conftest_path: Path | None,
    pages_yaml_path: Path | None,
    dry_run: bool,
) -> None:
    """根据 classified.category 派发到对应的修复模块。

    - ENV_ERROR    → env_repair
    - DATA_ERROR   → data_repair
    - BUG          → bug_repair（注入 conftest marker）
    - SCRIPT_ERROR → apply_method_typo_fix / apply_deprecated_api_fix（基于 AttributeError / DeprecationWarning）
    """
    if record.classified is None:
        return
    category = getattr(record.classified, "category", "")
    message = record.failure.message or ""
    traceback = record.failure.traceback or ""

    if category == "ENV_ERROR":
        plan = diagnose_env_failure(
            message=message,
            traceback=traceback,
            console_log=console_log_text,
        )
        if plan is None:
            return
        result = execute_env_repair(
            plan=plan, logger=logger, project_dir=project_dir, dry_run=dry_run,
        )
        record.category_repair = {"kind": "env", "plan": plan, "result": result}

    elif category == "DATA_ERROR":
        plan = diagnose_data_failure(
            message=message,
            traceback=traceback,
            console_log=console_log_text,
        )
        if plan is None:
            return
        result = execute_data_repair(
            plan=plan, logger=logger, project_dir=project_dir,
            dry_run=dry_run, trigger_nodeid=record.failure.nodeid,
        )
        record.category_repair = {"kind": "data", "plan": plan, "result": result}

    elif category == "BUG":
        plan = diagnose_bug_failure(
            message=message,
            traceback=traceback,
            console_log=console_log_text,
            nodeid=record.failure.nodeid,
        )
        if plan is None:
            return
        result = execute_bug_repair(
            plan=plan, project_dir=project_dir,
            conftest_path=conftest_path or (project_dir / "tests" / "conftest.py"),
            dry_run=dry_run,
        )
        record.category_repair = {"kind": "bug", "plan": plan, "result": result}

    elif category == "SCRIPT_ERROR":
        # 仅处理 AttributeError / DeprecationWarning，原生 AssertionError 不动（业务断言）
        script_repair = _try_script_error_fix(
            message=message,
            traceback=traceback,
            pages_dir=pages_dir,
            dry_run=dry_run,
        )
        if script_repair:
            record.category_repair = script_repair


def _try_script_error_fix(
    message: str,
    traceback: str,
    pages_dir: Path | None,
    dry_run: bool,
) -> dict | None:
    """SCRIPT_ERROR：尝试 method_typo / deprecated_api 修复。

    Returns:
        {"kind": "script", "subkind": "method_typo"|"deprecated_api", "result": FixResult, "target_file": Path}
        或 None（未匹配到可修复信号）
    """
    if not pages_dir:
        return None
    combined = f"{message}\n{traceback}"

    # 1. AttributeError: ... has no attribute 'xxx'
    m = _ATTR_NOT_FOUND_PATTERN.search(combined)
    if m:
        attr = m.group("attr")
        correct = suggest_method_correction(attr)
        if not correct:
            return None
        # 在 pages/**/*.py 中搜索 .attr( 的调用
        candidates = find_files_with_pattern(pages_dir, f".{attr}(")
        if not candidates:
            return None
        target = candidates[0]
        result = apply_method_typo_fix(
            source_path=target, typo_name=attr, correct_name=correct, dry_run=dry_run,
        )
        return {
            "kind": "script",
            "subkind": "method_typo",
            "typo": attr,
            "correct": correct,
            "target_file": target,
            "result": result,
        }

    # 2. DeprecationWarning: ... deprecated
    m = _DEPRECATED_PATTERN.search(combined)
    if m:
        old_method = m.group("old")
        # 仅处理 1:1 可替换的（query_selector → locator）
        from apply_fix import DEPRECATED_API_MAPPING
        new_method = DEPRECATED_API_MAPPING.get(old_method)
        if not new_method:
            return None
        candidates = find_files_with_pattern(pages_dir, f".{old_method}(")
        if not candidates:
            return None
        target = candidates[0]
        result = apply_deprecated_api_fix(
            source_path=target, old_method=old_method, new_method=new_method, dry_run=dry_run,
        )
        return {
            "kind": "script",
            "subkind": "deprecated_api",
            "typo": old_method,
            "correct": new_method,
            "target_file": target,
            "result": result,
        }

    return None


def _verify_and_maybe_rollback(
    record: DiagnosisRecord,
    project_dir: Path,
    base_url: str | None,
    browser: str | None,
) -> None:
    """重跑单用例；失败则 rollback 到 .bak。

    升级规则：原根因是 missing_async_list_wait 且 verify 失败时，
    升级为 assertion_mismatch（仅报告，不再尝试自动修复）。
    """
    assert record.fix_applied is not None
    assert record.fix_target_file is not None
    failure = record.failure

    result = verify_single_test(
        project_dir=project_dir,
        nodeid=failure.nodeid,
        base_url=base_url,
        browser=browser,
    )
    record.verify_result = result

    if result.status != "passed" and record.fix_applied.backup_path:
        rollback(record.fix_applied.backup_path, record.fix_target_file)
        record.rolled_back = True

        # 升级：missing_async_list_wait → assertion_mismatch
        rc = record.root_cause
        if rc and getattr(rc, "root_cause", "") == "missing_async_list_wait":
            record.upgraded_root_cause = "assertion_mismatch"
            record.upgrade_reason = (
                "已应用智能等待，verify 重跑仍失败。"
                "非异步加载问题，建议排查后端搜索接口/测试数据。"
            )


# ============ 报告生成 ============

def generate_report(records: list[DiagnosisRecord], output_path: Path) -> None:
    """生成 ui_repair_report.md。"""
    lines: list[str] = []
    lines.append("# UI 失败诊断报告")
    lines.append("")
    lines.append(f"**总失败数：** {len(records)}")
    lines.append("")

    # 分类统计
    by_category: dict[str, int] = {}
    by_root_cause: dict[str, int] = {}
    fix_applied_count = 0
    verify_passed_count = 0
    rolled_back_count = 0
    category_repair_count = 0
    upgraded_count = 0

    for r in records:
        if r.classified:
            cat = getattr(r.classified, "category", "UNKNOWN")
            by_category[cat] = by_category.get(cat, 0) + 1
        if r.root_cause:
            rc_name = getattr(r.root_cause, "root_cause", "unknown")
            by_root_cause[rc_name] = by_root_cause.get(rc_name, 0) + 1
        if r.fix_applied and r.fix_applied.modified:
            fix_applied_count += 1
        if r.verify_result and getattr(r.verify_result, "status", "") == "passed":
            verify_passed_count += 1
        if r.rolled_back:
            rolled_back_count += 1
        if r.category_repair:
            category_repair_count += 1
        if r.upgraded_root_cause:
            upgraded_count += 1
            # 升级后的根因也计入分布
            by_root_cause[r.upgraded_root_cause] = \
                by_root_cause.get(r.upgraded_root_cause, 0) + 1

    lines.append("## 概览")
    lines.append("")
    lines.append("| 维度 | 值 |")
    lines.append("|------|-----|")
    for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
        lines.append(f"| 分类：{cat} | {count} |")
    for rc_name, count in sorted(by_root_cause.items(), key=lambda x: -x[1]):
        lines.append(f"| 根因：{rc_name} | {count} |")
    lines.append(f"| 已应用 AST 修复 | {fix_applied_count} |")
    lines.append(f"| 已应用类别修复（ENV/DATA/BUG/SCRIPT）| {category_repair_count} |")
    lines.append(f"| 验证通过 | {verify_passed_count} |")
    lines.append(f"| 验证失败 → 升级为 assertion_mismatch | {upgraded_count} |")
    lines.append(f"| 回滚（验证失败）| {rolled_back_count} |")
    lines.append("")

    # 明细
    lines.append("## 失败明细")
    lines.append("")
    for i, r in enumerate(records, 1):
        lines.extend(_render_record(i, r))
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _render_record(idx: int, record: DiagnosisRecord) -> list[str]:
    """渲染单条失败记录。"""
    out: list[str] = []
    f = record.failure
    out.append(f"### {idx}. `{f.nodeid}`")
    out.append("")
    out.append(f"- **失败阶段：** {f.failure_stage}")

    if record.classified:
        c = record.classified
        out.append(f"- **分类：** {getattr(c, 'category', '')}（置信度 {getattr(c, 'confidence', 0):.2f}）")
        signals = getattr(c, "signals", [])
        if signals:
            out.append(f"- **信号：** {', '.join(signals)}")

    if record.root_cause:
        rc = record.root_cause
        out.append(f"- **根因：** {getattr(rc, 'root_cause', '')}（策略：{getattr(rc, 'fix_strategy', '')}）")
        evidence = getattr(rc, "evidence", {}) or {}
        if evidence:
            evidence_str = "; ".join(f"{k}={v}" for k, v in evidence.items() if not isinstance(v, (list, dict)))
            if evidence_str:
                out.append(f"- **证据：** {evidence_str}")

    if record.fix_applied:
        fr = record.fix_applied
        if fr.modified:
            target_str = str(record.fix_target_file) if record.fix_target_file else "(unknown)"
            out.append(f"- **修复：** 已修改 `{target_str}`")
            if fr.backup_path:
                out.append(f"- **备份：** `{fr.backup_path}`")
        else:
            out.append("- **修复：** 未匹配到修改点")

    if record.verify_result:
        vr = record.verify_result
        status = getattr(vr, "status", "unknown")
        duration = getattr(vr, "duration_sec", 0)
        out.append(f"- **验证：** {status}（{duration:.1f}s）")
        if record.rolled_back:
            out.append("- **回滚：** 是（验证未通过，已恢复原文件）")

    if record.upgraded_root_cause:
        out.append(f"- **根因升级：** {record.upgraded_root_cause}（由 missing_async_list_wait 升级）")
        if record.upgrade_reason:
            out.append(f"- **升级原因：** {record.upgrade_reason}")

    # 类别相关修复（ENV/DATA/BUG/SCRIPT）
    if record.category_repair:
        cr = record.category_repair
        kind = cr.get("kind", "")
        if kind == "env":
            out.append(f"- **环境修复：** {_summarize_env_or_data(cr.get('result'))}")
        elif kind == "data":
            out.append(f"- **数据修复：** {_summarize_env_or_data(cr.get('result'))}")
        elif kind == "bug":
            out.append(f"- **BUG 容错：** {_summarize_env_or_data(cr.get('result'))}")
        elif kind == "script":
            sub = cr.get("subkind", "")
            typo = cr.get("typo", "")
            correct = cr.get("correct", "")
            target = cr.get("target_file")
            result = cr.get("result")
            modified = getattr(result, "modified", False) if result else False
            target_str = str(target) if target else "(unknown)"
            out.append(
                f"- **脚本修复（{sub}）：** `{typo}` → `{correct}`"
                f"  修改 `{target_str}`  {'✅ 已应用' if modified else '⚠️ 未匹配'}"
            )

    # 简要错误信息
    msg_preview = (f.message or "").split("\n", 1)[0][:200]
    out.append(f"- **原始错误：** `{msg_preview}`")
    return out


def _summarize_env_or_data(result: object | None) -> str:
    """把 env/data/bug 的 Result 对象转成一行摘要。"""
    if result is None:
        return "（无结果）"
    success = getattr(result, "success", False)
    message = getattr(result, "message", "")
    executed = getattr(result, "executed", []) or []
    actions = ", ".join(e.get("action", "?") for e in executed if isinstance(e, dict))
    prefix = "✅" if success else "⚠️"
    return f"{prefix} {message}（动作：{actions or 'none'}）"


# ============ CLI ============

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="diagnose",
        description="UI 失败诊断：JUnit XML + artifacts → 分类 → 定位 → 修复 → 报告",
    )
    parser.add_argument("--junit-xml", type=Path, required=True, help="JUnit XML 路径")
    parser.add_argument("--artifacts-dir", type=Path, required=True, help="artifacts 根目录")
    parser.add_argument("--project-dir", type=Path, required=True, help="项目根（含 pages/）")
    parser.add_argument("--pages-subdir", default="pages", help="pages 子目录名（默认 pages）")
    parser.add_argument("--output", type=Path, default=None, help="输出报告路径")
    parser.add_argument("--no-fix", action="store_true", help="只分类 + 定位，不应用 AST 修复")
    parser.add_argument("--dry-run", action="store_true", help="AST 修复 dry-run 模式（不写文件）")
    parser.add_argument("--verify", action="store_true", help="修复后重跑单用例验证")
    parser.add_argument("--base-url", default=None, help="verify 时 --base-url")
    parser.add_argument("--browser", default=None, help="verify 时 --browser")
    parser.add_argument("--audit-log", type=Path, default=None, help="审计日志路径（默认 <project>/.ui-failure-diagnoser/audit.log）")
    parser.add_argument("--conftest", type=Path, default=None, help="项目 tests/conftest.py 路径（bug_repair 注入 marker）")
    parser.add_argument("--pages-yaml", type=Path, default=None, help="项目 pages.yaml 路径（locator 对比金标准）")
    args = parser.parse_args(argv)

    if not args.junit_xml.exists():
        print(f"[ERROR] JUnit XML 不存在: {args.junit_xml}", file=sys.stderr)
        return 2
    if not args.artifacts_dir.exists():
        print(f"[ERROR] artifacts 目录不存在: {args.artifacts_dir}", file=sys.stderr)
        return 2
    if not args.project_dir.exists():
        print(f"[ERROR] 项目目录不存在: {args.project_dir}", file=sys.stderr)
        return 2

    output_path = args.output or (args.artifacts_dir.parent / "ui_repair_report.md")

    records = diagnose(
        junit_xml=args.junit_xml,
        artifacts_dir=args.artifacts_dir,
        project_dir=args.project_dir,
        pages_subdir=args.pages_subdir,
        apply_fixes=not args.no_fix,
        dry_run=args.dry_run,
        verify=args.verify,
        base_url=args.base_url,
        browser=args.browser,
        audit_log_path=args.audit_log,
        conftest_path=args.conftest,
        pages_yaml_path=args.pages_yaml,
    )

    generate_report(records, output_path)

    # stdout 摘要
    passed = sum(1 for r in records if r.verify_result and getattr(r.verify_result, "status") == "passed")
    fixed = sum(1 for r in records if r.fix_applied and r.fix_applied.modified)
    category_fixed = sum(1 for r in records if r.category_repair)
    print(f"[diagnose] 共诊断 {len(records)} 条失败")
    print(f"[diagnose] AST 修复：{fixed} 条")
    print(f"[diagnose] 类别修复（ENV/DATA/BUG/SCRIPT）：{category_fixed} 条")
    if args.verify:
        print(f"[diagnose] 验证通过：{passed} 条")
    print(f"[diagnose] 报告：{output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
