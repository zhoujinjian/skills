"""parsers.py — UI 测试报告多源数据解析

输入源（按优先级）：
    1. JUnit XML（必需）：report.xml，pytest 原生产物
    2. 执行 JSON（可选）：ui-test-executor/generate_report.py 产出的 report.json
    3. 诊断报告（可选）：ui-failure-diagnoser 产出的 ui_repair_report.md
    4. artifacts 目录（可选）：截图/视频/trace/page-source/console-logs
    5. 浏览器环境 JSON（可选）：detect_browsers.py 产出的 browser_env.json
    6. 历史 JSON（可选）：多次执行累积，用于趋势图

输出：ReportDocument 数据结构，供 analyzer/renderer 消费。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


# ============ 数据模型 ============


@dataclass
class UITestCase:
    nodeid: str
    classname: str
    testname: str
    file: str
    line: int | None
    status: str  # passed / failed / error / skipped
    duration: float
    message: str | None = None
    traceback: str | None = None
    browser: str | None = None
    markers: list[str] = field(default_factory=list)
    failure_stage: str | None = None  # setup / call / teardown
    artifacts: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class DiagnoseRecord:
    """从 ui_repair_report.md 解析的诊断记录。"""
    nodeid: str
    failure_stage: str | None = None
    category: str | None = None
    confidence: float | None = None
    signals: list[str] = field(default_factory=list)
    root_cause: str | None = None
    fix_strategy: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    fix_target_file: str | None = None
    fix_applied: bool = False
    backup_path: str | None = None
    verify_status: str | None = None  # passed / failed
    verify_duration: float | None = None
    rolled_back: bool = False
    upgraded_root_cause: str | None = None
    upgrade_reason: str | None = None
    category_repair: dict[str, Any] | None = None
    raw_error: str = ""


@dataclass
class UISuiteSummary:
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    reruns: int = 0
    pass_rate: float = 0.0
    total_duration: float = 0.0
    slowest_test: str = ""
    slowest_duration: float = 0.0


@dataclass
class ReportDocument:
    generated_at: str
    suite: UISuiteSummary
    tests: list[UITestCase] = field(default_factory=list)
    failures: list[UITestCase] = field(default_factory=list)
    diagnose_records: list[DiagnoseRecord] = field(default_factory=list)
    diagnose_overview: dict[str, Any] = field(default_factory=dict)
    by_module: dict[str, dict] = field(default_factory=dict)
    by_priority: dict[str, dict] = field(default_factory=dict)
    by_browser: dict[str, dict] = field(default_factory=dict)
    by_category: dict[str, int] = field(default_factory=dict)
    by_root_cause: dict[str, int] = field(default_factory=dict)
    artifact_root: str | None = None
    browser_env: dict[str, Any] | None = None
    history: list[dict] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


# ============ JUnit XML 解析 ============


_BROWSER_RE = re.compile(r"\[BROWSER=([^\]]+)\]")
_WORKER_RE = re.compile(r"\[WORKER=([^\]]+)\]")
_PARAM_BROWSER_RE = re.compile(r"\[(chromium|firefox|webkit)[-\]]")


def parse_junit_xml(xml_path: Path) -> tuple[UISuiteSummary, list[UITestCase]]:
    """解析 JUnit XML。

    Returns:
        (suite_summary, test_cases)
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # pytest 的 XML 根可能是 <testsuites> 或单 <testsuite>
    suite_el = root if root.tag == "testsuite" else root.find("testsuite")
    if suite_el is None:
        return UISuiteSummary(generated_at=""), []

    suite = UISuiteSummary(
        total=int(suite_el.get("tests", 0)),
        passed=int(suite_el.get("tests", 0))
        - int(suite_el.get("failures", 0))
        - int(suite_el.get("errors", 0))
        - int(suite_el.get("skipped", 0)),
        failed=int(suite_el.get("failures", 0)),
        errors=int(suite_el.get("errors", 0)),
        skipped=int(suite_el.get("skipped", 0)),
        total_duration=float(suite_el.get("time", 0)),
    )

    if suite.total > 0:
        suite.pass_rate = round(suite.passed / suite.total * 100, 2)

    cases: list[UITestCase] = []
    for tc_el in suite_el.iter("testcase"):
        nodeid = _build_nodeid(tc_el)
        duration = float(tc_el.get("time", 0))
        status, message, traceback_text, failure_stage = _extract_status(tc_el)

        browser = _extract_browser(tc_el)
        markers = _extract_markers(tc_el)

        cases.append(
            UITestCase(
                nodeid=nodeid,
                classname=tc_el.get("classname", ""),
                testname=tc_el.get("name", ""),
                file=tc_el.get("file", ""),
                line=int(tc_el.get("line")) if tc_el.get("line") else None,
                status=status,
                duration=duration,
                message=message,
                traceback=traceback_text,
                browser=browser,
                markers=markers,
                failure_stage=failure_stage,
            )
        )

        if status in ("failed", "error"):
            suite.failed += 0  # 已计入
        if duration > suite.slowest_duration:
            suite.slowest_duration = duration
            suite.slowest_test = nodeid

    return suite, cases


def _build_nodeid(tc_el: ET.Element) -> str:
    """从 testcase 元素重建 nodeid：file::classname::name。

    classname 通常是 'tests.module.test_file.TestClass'，name 可能含 [param]。
    """
    classname = tc_el.get("classname", "")
    name = tc_el.get("name", "")
    file = tc_el.get("file", "")

    # classname: tests.product.test_search.TestSearchPositive
    # 取 TestClass 段
    if "." in classname:
        class_part = classname.rsplit(".", 1)[-1]
    else:
        class_part = classname

    # file: tests/product/test_search.py
    file_part = file.replace("\\", "/").replace("/", ".").replace(".py", "")

    if file_part and class_part:
        return f"{file}::{class_part}::{name}"
    return f"{classname}::{name}"


def _extract_status(tc_el: ET.Element) -> tuple[str, str | None, str | None, str | None]:
    """返回 (status, message, traceback, failure_stage)。

    JUnit 中：
        <failure> = call 阶段失败
        <error> = setup/teardown 阶段失败（含 failure_stage 信息）
        <skipped> = 跳过
        都没有 = passed
    """
    fail_el = tc_el.find("failure")
    err_el = tc_el.find("error")
    skip_el = tc_el.find("skipped")

    if err_el is not None:
        # Error 阶段：setup/teardown 失败。type 是异常类，从 message 推断具体阶段。
        msg = err_el.get("message", "") or ""
        if "teardown" in msg.lower():
            stage = "teardown"
        else:
            stage = "setup"
        return ("error", err_el.get("message"), (err_el.text or "").strip(), stage)

    if fail_el is not None:
        return ("failed", fail_el.get("message"), (fail_el.text or "").strip(), "call")

    if skip_el is not None:
        return ("skipped", skip_el.get("message"), None, None)

    return ("passed", None, None, None)


def _extract_browser(tc_el: ET.Element) -> str | None:
    """从 <system-out>[BROWSER=chromium] 或 nodeid 参数化后缀提取浏览器。"""
    syso = tc_el.find("system-out")
    if syso is not None and syso.text:
        m = _BROWSER_RE.search(syso.text)
        if m:
            return m.group(1).strip()

    # 兜底：从 name 后缀 [chromium-手机] 提取
    name = tc_el.get("name", "")
    m = _PARAM_BROWSER_RE.search(name)
    if m:
        # 还要拼回原始 nodeid 检查
        return m.group(1)
    return None


def _extract_markers(tc_el: ET.Element) -> list[str]:
    """从 <system-out>[MARKER=xxx] 提取 marker 列表（如果 conftest 注入了的话）。"""
    markers: list[str] = []
    syso = tc_el.find("system-out")
    if syso is not None and syso.text:
        for m in re.finditer(r"\[MARKER=([^\]]+)\]", syso.text):
            markers.append(m.group(1).strip())
    return markers


# ============ ui_repair_report.md 解析 ============


def parse_diagnose_md(md_path: Path) -> tuple[list[DiagnoseRecord], dict[str, Any]]:
    """解析 ui-failure-diagnoser 输出的 Markdown 报告。

    Returns:
        (records, overview_dict)
    """
    text = md_path.read_text(encoding="utf-8")
    overview = _parse_diagnose_overview(text)
    records = _parse_diagnose_records(text)
    return records, overview


def _parse_diagnose_overview(text: str) -> dict[str, Any]:
    """从「## 概览」表格提取统计字段。"""
    overview: dict[str, Any] = {}
    in_overview = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## 概览"):
            in_overview = True
            continue
        if in_overview:
            if stripped.startswith("## "):
                break
            if stripped.startswith("|") and not stripped.startswith("|---") and not stripped.startswith("| 维度"):
                # 解析 "| 分类：SCRIPT_ERROR | 2 |"
                parts = [p.strip() for p in stripped.strip("|").split("|")]
                if len(parts) >= 2:
                    key = parts[0]
                    val = parts[1]
                    try:
                        overview[key] = int(val)
                    except ValueError:
                        overview[key] = val
    return overview


def _parse_diagnose_records(text: str) -> list[DiagnoseRecord]:
    """从「## 失败明细」解析每条记录。"""
    records: list[DiagnoseRecord] = []
    in_detail = False
    current: DiagnoseRecord | None = None

    for line in text.splitlines():
        stripped = line.strip()
        # 进入明细区
        if stripped.startswith("## 失败明细"):
            in_detail = True
            continue
        if not in_detail:
            continue

        # 新记录开始：### N. `nodeid`
        m = re.match(r"^###\s+\d+\.\s+`([^`]+)`", stripped)
        if m:
            if current is not None:
                records.append(current)
            current = DiagnoseRecord(nodeid=m.group(1))
            continue

        if current is None:
            continue

        # 字段：`- **字段：** 值`
        fm = re.match(r"^-\s+\*\*([^：*]+)：?\*\*\s*(.*)$", stripped)
        if fm:
            key = fm.group(1).strip().rstrip("：:").strip()
            val = fm.group(2).strip()
            _fill_record_field(current, key, val)

    if current is not None:
        records.append(current)

    return records


def _fill_record_field(rec: DiagnoseRecord, key: str, val: str) -> None:
    """把 Markdown 字段映射到 DiagnoseRecord。"""
    key_lower = key.lower()
    if key in ("失败阶段",):
        rec.failure_stage = val or None
    elif key in ("分类",):
        # 「SCRIPT_ERROR（置信度 0.65）」
        rec.category = val.split("（")[0].split("(")[0].strip() or None
        m = re.search(r"置信度\s*([\d.]+)", val)
        if m:
            rec.confidence = float(m.group(1))
    elif key in ("信号",):
        rec.signals = [s.strip() for s in val.split(",") if s.strip()]
    elif key in ("根因",):
        # 「missing_async_list_wait（策略：ast_rewrite）」
        rec.root_cause = val.split("（")[0].split("(")[0].strip() or None
        m = re.search(r"策略[：:]\s*([\w_]+)", val)
        if m:
            rec.fix_strategy = m.group(1)
    elif key in ("证据",):
        rec.evidence = {"raw": val}
    elif key in ("修复",):
        if "已修改" in val or "已应用" in val:
            rec.fix_applied = True
            m = re.search(r"`?([^`]+\.py)`?", val)
            if m:
                rec.fix_target_file = m.group(1)
        elif "未匹配" in val or "未应用" in val:
            rec.fix_applied = False
    elif key in ("备份",):
        if val and "无" not in val:
            rec.backup_path = val.replace("`", "").strip() or None
    elif key in ("验证",):
        if "passed" in val.lower():
            rec.verify_status = "passed"
        elif "failed" in val.lower():
            rec.verify_status = "failed"
        m = re.search(r"([\d.]+)\s*s", val)
        if m:
            rec.verify_duration = float(m.group(1))
    elif key in ("回滚",):
        rec.rolled_back = "是" in val or "true" in val.lower()
    elif key in ("根因升级", "升级根因"):
        rec.upgraded_root_cause = val or None
    elif key in ("升级原因",):
        rec.upgrade_reason = val or None
    elif key in ("BUG 容错", "类别修复"):
        rec.category_repair = {"raw": val}
    elif key in ("原始错误",):
        rec.raw_error = val.replace("`", "").strip()


# ============ artifacts 关联 ============


def attach_artifacts(cases: list[UITestCase], artifacts_dir: Path) -> None:
    """为每个 case 扫描 artifacts 目录，匹配截图/视频/trace/page-source/console-log。

    匹配策略：
        1. 多 slug 变体（方法名 / 方法名+浏览器 / 全 nodeid）匹配文件名子串，提高命中率
        2. 同时扫描两种目录布局：
           - conftest 直写：artifacts/screenshots, videos, traces, page-source, console-logs
           - pytest-playwright 原生：artifacts/pytest-raw/<slug>/...
        3. 失败上下文 sidecar：artifacts/failure-context/<slug>*.json（可选）
    """
    if not artifacts_dir.exists():
        return

    # 预扫描各子目录
    buckets = {
        "screenshots": list((artifacts_dir / "screenshots").glob("*.png")) if (artifacts_dir / "screenshots").exists() else [],
        "page_source": list((artifacts_dir / "page-source").glob("*.html")) if (artifacts_dir / "page-source").exists() else [],
        "console_logs": list((artifacts_dir / "console-logs").glob("*.log")) if (artifacts_dir / "console-logs").exists() else [],
        "videos_flat": list((artifacts_dir / "videos").glob("*.webm")) if (artifacts_dir / "videos").exists() else [],
        "traces_flat": [p for p in (artifacts_dir / "traces").glob("*.zip") if "trace" in p.name.lower()] if (artifacts_dir / "traces").exists() else [],
        "pytest_raw": list((artifacts_dir / "pytest-raw").rglob("*")) if (artifacts_dir / "pytest-raw").exists() else [],
        "failure_context": list((artifacts_dir / "failure-context").glob("*.json")) if (artifacts_dir / "failure-context").exists() else [],
    }

    for case in cases:
        slugs = _nodeid_slug_variants(case.nodeid)
        if not slugs:
            continue

        def find_matches(
            files: list[Path],
            *,
            suffix: str | None = None,
            name_kw: str | None = None,
            limit: int = 1,
        ) -> list[str]:
            """按 slug 变体精确度顺序匹配，命中即返回，避免宽松变体跨用例误匹配。

            slugs 已按精确度从高到低排序（含参数化 ID 的精确变体在最前），
            遍历时一旦当前 slug 命中就 return，不再尝试更宽松的变体——
            这保证「仅参数化 ID 不同的用例」只会匹配到自己的 artifact。
            """
            cands = list(files)
            if suffix:
                cands = [p for p in cands if p.suffix == suffix]
            if name_kw:
                cands = [p for p in cands if name_kw in p.name.lower()]
            for slug in slugs:
                hits = [str(p.resolve()) for p in cands if slug in str(p)]
                if hits:
                    return hits[:limit]
            return []

        # 截图：conftest flat（视口+全页命名规范）+ pytest-raw test-failed-N.png
        all_screenshots = buckets["screenshots"] + [
            p for p in buckets["pytest_raw"]
            if p.suffix == ".png" and "failed" in p.name.lower()
        ]
        # 视频 / trace：flat + pytest-raw 合并
        all_videos = buckets["videos_flat"] + [
            p for p in buckets["pytest_raw"] if p.suffix == ".webm"
        ]
        all_traces = buckets["traces_flat"] + [
            p for p in buckets["pytest_raw"]
            if p.suffix == ".zip" and "trace" in p.name.lower()
        ]

        case.artifacts = {
            "screenshots": find_matches(all_screenshots, suffix=".png", limit=5),
            "page_source": find_matches(buckets["page_source"], suffix=".html", limit=1),
            "console_logs": find_matches(buckets["console_logs"], suffix=".log", limit=1),
            "videos": find_matches(all_videos, suffix=".webm", limit=1),
            "traces": find_matches(all_traces, suffix=".zip", limit=1),
            "failure_context": find_matches(buckets["failure_context"], suffix=".json", limit=1),
        }


def _slugify_with_unicode_escape(s: str) -> str:
    """把字符串转为 slug，非 ASCII 字符按 pytest 的 unicode escape 规则转义。

    '小米' → 'u5c0f-u7c73'（pytest 把参数化 ID 写入文件名时用 \\uXXXX 转义，hex 间用 - 分隔）
    'chromium-手机' → 'chromium-u624b-u673a'

    关键：每个非 ASCII char 转义为 -uXXXX- 包夹，避免连续两个 unicode 字符
    生成粘连的 uXXXXuYYYY（应生成 uXXXX-uYYYY）。
    """
    parts: list[str] = []
    for ch in s:
        if ch.isascii() and ch.isalnum():
            parts.append(ch.lower())
        elif ch.isascii():
            parts.append("-")
        else:
            # 非 ASCII：pytest 写成 \\uXXXX（小写 hex），文件名里表现为 uXXXX
            # 用 -uXXXX- 包夹，re.sub 后会合并多余 -，确保 hex 之间必有分隔
            parts.append(f"-u{format(ord(ch), '04x')}-")
    return re.sub(r"-+", "-", "".join(parts)).strip("-")


def _nodeid_slug_variants(nodeid: str) -> list[str]:
    """生成多种 slug 变体用于 artifact 文件名匹配。

    返回顺序按精确度从高到低：含参数化 ID 的精确变体优先（避免误匹配），宽松变体兜底。

    'tests/x.py::TestY::test_z[chromium-小米]' →
        ['tests-x-testy-test-z-chromium-u5c0f-u7c73',  # 含参数化 ID 全 slug（最精确）
         'test-z-chromium-u5c0f-u7c73',                 # 含参数化 ID 方法 slug
         'test-z',                                       # 方法名（去参数化）
         'test-z-chromium',                              # 浏览器 + 方法名
         'tests-x-testy-test-z']                         # 全 slug（去参数化）

    精确变体优先确保「仅参数化 ID 不同的用例」（如 [chromium-小米] vs [chromium-手表]）
    不会互相误匹配对方的 video / trace。
    """
    if not nodeid:
        return []
    variants: list[str] = []
    seen: set[str] = set()

    def add(v: str | None) -> None:
        if v and v not in seen:
            seen.add(v)
            variants.append(v)

    # 提取参数化部分（含方括号内容），用于生成精确变体
    param_match = re.search(r"\[([^\]]+)\]", nodeid)
    param_inner = param_match.group(1) if param_match else ""

    # 变体 A：完整 nodeid slug，含参数化 ID 转义（pytest-raw 目录名风格）
    # tests/x.py::TestY::test_z[chromium-小米] → 'tests-x-testy-test-z-chromium-u5c0f-u7c73'
    full_with_param = nodeid.replace(".py", "").replace("::", "-").replace("/", "-").replace("[", "-").replace("]", "").replace(".", "-")
    add(_slugify_with_unicode_escape(full_with_param))

    # 变体 B：方法名 + 参数化 ID（conftest flat 命名风格）
    # test_z[chromium-小米] → 'test-z-chromium-u5c0f-u7c73'
    last_full = nodeid.split("::")[-1].replace("[", "-").replace("]", "")
    last_full_slug = _slugify_with_unicode_escape(last_full)
    add(last_full_slug)

    # 变体 C：方法名 slug（去参数化，最短，兼容老 conftest）
    bare = re.sub(r"\[[^\]]+\]", "", nodeid)
    last_bare = bare.split("::")[-1]
    method_slug = re.sub(r"[^A-Za-z0-9]+", "-", last_bare).strip("-").lower()
    add(method_slug)

    # 变体 D：浏览器 + 方法名（ASCII only，适配 [chromium] 后缀）
    m = re.search(r"\[([a-z]+)[-_]", nodeid)
    if m and method_slug:
        add(f"{method_slug}-{m.group(1)}")

    # 变体 E：全 nodeid slug（去参数化，最长兜底）
    full_no_param = re.sub(r"\[[^\]]*\]", "", nodeid).replace(".py", "").replace("::", "-").replace("/", "-").replace(".", "-")
    full_slug = re.sub(r"[^A-Za-z0-9]+", "-", full_no_param).strip("-").lower()
    if full_slug:
        add(full_slug[:80])

    return variants


def _nodeid_slug(nodeid: str) -> str:
    """把 nodeid slug 化，匹配 artifacts 文件命名。

    'tests/x.py::TestY::test_z[chromium-手机]' → 'tests-x-test-y-test-z-chromium-u624b-u673a'
    真实文件名通常是降级版（下划线、unicode 转义），这里返回多种 slug 让 substring 匹配更鲁棒。
    """
    # 简化版：取最后一段 ::，去掉参数化方括号内容，转小写
    last = nodeid.split("::")[-1]
    # 去除 [chromium-手机] 后缀
    base = re.sub(r"\[[^\]]+\]", "", last)
    base = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").lower()
    return base


# ============ 浏览器环境 / 历史 JSON ============


def load_browser_env(path: Path | None) -> dict[str, Any] | None:
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_history(path: Path | None) -> list[dict]:
    if not path or not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "history" in data:
            return data["history"]
    except Exception:
        pass
    return []


def load_exec_json(path: Path | None) -> dict[str, Any] | None:
    """读取 ui-test-executor/generate_report.py 产出的 report.json（可选，提供更丰富字段）。"""
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
