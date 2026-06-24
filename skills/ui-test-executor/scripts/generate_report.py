#!/usr/bin/env python3
"""
generate_report.py — UI 测试执行结果统一报告生成器

输入:
  - JUnit XML 报告（pytest --junit-xml 产出）
  - artifacts 目录（截图 / 视频 / Trace / HAR / console 日志）

输出:
  - report.json — 结构化 JSON（供 CI/CD、看板消费）
  - summary.md  — 人类可读 Markdown 摘要
  - summary.txt — 单行 CI/CD 摘要（一行字符串）

用法:
  python3 generate_report.py \
      --junit-xml ./test-results/report.xml \
      --artifacts-dir ./test-results/artifacts \
      --output-dir ./test-results
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


# ============================================================
# 数据模型
# ============================================================

@dataclass
class TestCaseResult:
    nodeid: str
    name: str
    classname: str
    file: str = ""
    line: str = ""
    status: str = "passed"  # passed / failed / error / skipped / rerun
    duration: float = 0.0
    message: str = ""        # 失败摘要
    traceback: str = ""      # 完整 traceback
    markers: list[str] = field(default_factory=list)
    artifacts: dict[str, list[str]] = field(default_factory=dict)
    browser: str = ""
    worker: str = ""


@dataclass
class TestSuiteSummary:
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
    suite: TestSuiteSummary
    by_marker: dict[str, dict[str, int]] = field(default_factory=dict)
    by_module: dict[str, dict[str, int]] = field(default_factory=dict)
    by_priority: dict[str, dict[str, int]] = field(default_factory=dict)
    by_browser: dict[str, dict[str, int]] = field(default_factory=dict)
    failures: list[TestCaseResult] = field(default_factory=list)
    tests: list[TestCaseResult] = field(default_factory=list)


# ============================================================
# JUnit XML 解析
# ============================================================

STATUS_MAP = {
    "passed": "passed",
    "failure": "failed",
    "error": "error",
    "skipped": "skipped",
}


def parse_junit_xml(xml_path: Path) -> tuple[list[TestCaseResult], TestSuiteSummary]:
    """解析 pytest 产出的 JUnit XML

    pytest JUnit 格式:
        <testsuite name="..." tests="N" failures="F" errors="E" skipped="S" time="T">
          <testcase classname="..." name="..." file="..." line="..." time="...">
            <failure message="..." type="...">traceback</failure>
            <system-out>...</system-out>
          </testcase>
          ...
        </testsuite>
    """
    if not xml_path.exists():
        raise FileNotFoundError(f"JUnit XML 不存在: {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    # pytest JUnit XML 可能有两种根:
    #   <testsuite tests="N" .../>                  (单 suite)
    #   <testsuites><testsuite tests="N" .../></testsuites>  (多 suite 包装)
    # 统计属性在 testsuite 节点上，需要遍历汇总
    suite_nodes = list(root.iter("testsuite"))
    if not suite_nodes:
        # 极端情况: 没有 testsuite 节点
        total = int(root.get("tests", 0) or 0)
        failed = int(root.get("failures", 0) or 0)
        errors = int(root.get("errors", 0) or 0)
        skipped = int(root.get("skipped", 0) or 0)
        duration = float(root.get("time", 0) or 0)
    else:
        total = sum(int(s.get("tests", 0) or 0) for s in suite_nodes)
        failed = sum(int(s.get("failures", 0) or 0) for s in suite_nodes)
        errors = sum(int(s.get("errors", 0) or 0) for s in suite_nodes)
        skipped = sum(int(s.get("skipped", 0) or 0) for s in suite_nodes)
        duration = sum(float(s.get("time", 0) or 0) for s in suite_nodes)

    summary = TestSuiteSummary(
        total=total,
        failed=failed,
        errors=errors,
        skipped=skipped,
        total_duration=duration,
    )

    test_cases: list[TestCaseResult] = []

    for tc in root.iter("testcase"):
        nodeid = tc.get("name", "")
        classname = tc.get("classname", "")
        file = tc.get("file", "")
        line = tc.get("line", "")
        duration = float(tc.get("time", 0) or 0)

        # 拼接完整 nodeid（与 pytest 输出一致）
        full_nodeid = f"{file}::{nodeid}" if file else f"{classname}::{nodeid}"

        # 判定状态
        status = "passed"
        message = ""
        traceback = ""

        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")

        if failure is not None:
            status = "failed"
            message = failure.get("message", "") or ""
            traceback = failure.text or ""
        elif error is not None:
            status = "error"
            message = error.get("message", "") or ""
            traceback = error.text or ""
        elif skipped is not None:
            status = "skipped"
            message = skipped.get("message", "") or ""

        # 从 system-out 提取浏览器 / 工作进程信息
        browser = ""
        worker = ""
        sys_out = tc.find("system-out")
        if sys_out is not None and sys_out.text:
            browser_match = re.search(r"\[BROWSER=([\w-]+)\]", sys_out.text)
            if browser_match:
                browser = browser_match.group(1)
            worker_match = re.search(r"\[WORKER=(gw\d+)\]", sys_out.text)
            if worker_match:
                worker = worker_match.group(1)

        # 重试痕迹（pytest-rerunfailures 会把重试作为多 testcase 或 system-out 记录）
        is_rerun = tc.get("rerun", "0") != "0"

        test_cases.append(
            TestCaseResult(
                nodeid=full_nodeid,
                name=nodeid,
                classname=classname,
                file=file,
                line=line,
                status="rerun" if is_rerun else status,
                duration=duration,
                message=message,
                traceback=traceback[:4000],  # 截断超长 traceback
                browser=browser,
                worker=worker,
            )
        )

    # 统计 passed
    summary.passed = sum(1 for t in test_cases if t.status == "passed")
    summary.reruns = sum(1 for t in test_cases if t.status == "rerun")
    summary.pass_rate = (summary.passed / summary.total * 100) if summary.total else 0.0

    # 找出最慢的用例
    if test_cases:
        slowest = max(test_cases, key=lambda t: t.duration)
        summary.slowest_test = slowest.nodeid
        summary.slowest_duration = slowest.duration

    return test_cases, summary


# ============================================================
# Artifact 关联
# ============================================================

# pytest-playwright artifact 命名规则:
#   test.py::TestClass::test_method
# → 文件名形如: test-method-mod-N-chromium-...-{screenshot,video,trace}.png|webm|zip
# 关键 token: method name, classname 简化名

def normalize_method_token(nodeid: str) -> str:
    """nodeid → artifact 文件名中使用的 token

    pytest-playwright 把 :: 转成 -，参数化用 - 替换 [] 和 -
    """
    # 取方法名（最后一个 :: 之后）
    method = nodeid.split("::")[-1]
    # 去除参数化方括号内特殊字符（保留数字与字母）
    method = re.sub(r"[\[\]\s/]", "-", method)
    method = re.sub(r"[^A-Za-z0-9_-]", "-", method)
    method = re.sub(r"-+", "-", method).strip("-").lower()
    return method


def associate_artifacts(
    tests: list[TestCaseResult], artifacts_dir: Path
) -> None:
    """为每个测试用例关联 artifact 文件路径

    pytest-playwright 产出的 artifact 目录结构:
        test-results/pytest-output/
          ├── test-login-test-login-with-valid-credentials-mod-N-chromium/
          │   ├── test-failed-1.png        # 失败截图
          │   ├── video.webm                # 录屏
          │   └── trace.zip                 # Trace
    """
    if not artifacts_dir.exists():
        return

    # 索引 artifact 文件: 按方法名 token 归类
    method_to_files: dict[str, list[Path]] = defaultdict(list)
    for sub in artifacts_dir.rglob("*"):
        if sub.is_file():
            # 文件名包含方法名片段 → 加入索引
            method_to_files[sub.stem.lower()].append(sub)
            method_to_files[sub.parent.name.lower()].append(sub)

    for test in tests:
        method_token = normalize_method_token(test.nodeid)

        screenshots: list[str] = []
        videos: list[str] = []
        traces: list[str] = []
        har: list[str] = []
        page_sources: list[str] = []
        console_logs: list[str] = []

        for key, files in method_to_files.items():
            if method_token not in key and key not in method_token:
                continue
            for f in files:
                suffix = f.suffix.lower()
                rel = str(f)
                # 父目录名（用于区分 conftest 直写的 artifact 子目录）
                parent_name = f.parent.name.lower()
                parent_path = str(f.parent).lower()
                if suffix in (".png", ".jpg", ".jpeg"):
                    screenshots.append(rel)
                elif suffix in (".webm", ".mp4"):
                    videos.append(rel)
                elif suffix == ".zip" and "trace" in f.name.lower():
                    traces.append(rel)
                elif suffix == ".har":
                    har.append(rel)
                # 页面源码：按父目录 page-source/ 判定（conftest 写的文件名是 <nodeid>.html）
                elif suffix in (".html", ".mhtml") and (
                    parent_name == "page-source" or "page-source" in parent_path
                ):
                    page_sources.append(rel)
                # Console 日志：按父目录 console-logs/ 判定（conftest 写的文件名是 <nodeid>.log）
                elif suffix == ".log" and (
                    parent_name == "console-logs" or "console-logs" in parent_path
                ):
                    console_logs.append(rel)

        test.artifacts = {
            "screenshots": sorted(set(screenshots))[:5],
            "videos": sorted(set(videos)),
            "traces": sorted(set(traces)),
            "har": sorted(set(har)),
            "page_source": sorted(set(page_sources)),
            "console_logs": sorted(set(console_logs)),
        }


# ============================================================
# Marker 维度聚合
# ============================================================

def aggregate_by_marker(
    tests: list[TestCaseResult],
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]], dict[str, dict[str, int]]]:
    """按 priority / module / scene 维度聚合统计

    返回: (by_priority, by_module, by_scene)
    每个 dict 形如 {"P0": {"passed": 3, "failed": 1, "total": 4}, ...}
    """
    def _empty() -> dict[str, int]:
        return {"passed": 0, "failed": 0, "error": 0, "skipped": 0, "total": 0}

    by_priority: dict[str, dict[str, int]] = defaultdict(_empty)
    by_module: dict[str, dict[str, int]] = defaultdict(_empty)
    by_scene: dict[str, dict[str, int]] = defaultdict(_empty)

    # 由于 JUnit XML 默认不包含 marker 信息，从 classname 推断模块
    for test in tests:
        # module 推断: classname 通常是 tests.module.test_xxx.TestClass
        # 提取路径中的 module 段
        parts = test.classname.split(".")
        module = "unknown"
        for i, p in enumerate(parts):
            if p == "tests" and i + 1 < len(parts):
                module = parts[i + 1]
                break
        if module.startswith("test_"):
            module = module.replace("test_", "")

        bucket = by_module[module]
        bucket[test.status] = bucket.get(test.status, 0) + 1
        bucket["total"] += 1

    return by_priority, by_module, by_scene


# ============================================================
# 输出格式
# ============================================================

def to_json(doc: ReportDocument) -> str:
    return json.dumps(
        {
            "generated_at": doc.generated_at,
            "suite": asdict(doc.suite),
            "by_module": doc.by_module,
            "by_priority": doc.by_priority,
            "by_browser": doc.by_browser,
            "failures": [asdict(t) for t in doc.failures],
            "tests": [asdict(t) for t in doc.tests],
        },
        ensure_ascii=False,
        indent=2,
    )


def to_markdown(doc: ReportDocument) -> str:
    s = doc.suite
    lines = []
    lines.append("# UI 测试执行报告")
    lines.append("")
    lines.append(f"**生成时间**: {doc.generated_at}")
    lines.append("")

    # 概览
    lines.append("## 概览")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|----|")
    lines.append(f"| 用例总数 | {s.total} |")
    lines.append(f"| 通过 ✅ | {s.passed} ({s.pass_rate:.1f}%) |")
    lines.append(f"| 失败 ❌ | {s.failed} |")
    lines.append(f"| 错误 ⛔ | {s.errors} |")
    lines.append(f"| 跳过 ⏭️  | {s.skipped} |")
    lines.append(f"| 重试 🔄 | {s.reruns} |")
    lines.append(f"| 总耗时 | {s.total_duration:.1f}s |")
    if s.slowest_test:
        lines.append(f"| 最慢用例 | `{s.slowest_test}` ({s.slowest_duration:.1f}s) |")
    lines.append("")

    # 按模块聚合
    if doc.by_module:
        lines.append("## 按模块分布")
        lines.append("")
        lines.append("| 模块 | 通过 | 失败 | 错误 | 跳过 | 总数 | 通过率 |")
        lines.append("|------|-----:|-----:|-----:|-----:|-----:|------:|")
        for module, counts in sorted(doc.by_module.items()):
            rate = (counts["passed"] / counts["total"] * 100) if counts["total"] else 0
            lines.append(
                f"| {module} | {counts['passed']} | {counts['failed']} | "
                f"{counts['error']} | {counts['skipped']} | {counts['total']} | {rate:.0f}% |"
            )
        lines.append("")

    # 失败明细
    if doc.failures:
        lines.append(f"## 失败用例明细（{len(doc.failures)} 个）")
        lines.append("")
        for i, t in enumerate(doc.failures, 1):
            lines.append(f"### {i}. `{t.name}`")
            lines.append(f"- **位置**: `{t.nodeid}`")
            lines.append(f"- **耗时**: {t.duration:.2f}s")
            if t.browser:
                lines.append(f"- **浏览器**: {t.browser}")
            if t.message:
                lines.append(f"- **失败摘要**: {t.message.splitlines()[0] if t.message else ''}")
            if t.traceback:
                # 截取最后 20 行 traceback
                tb_lines = t.traceback.strip().splitlines()
                excerpt = "\n```\n" + "\n".join(tb_lines[-20:]) + "\n```"
                lines.append("- **Traceback** (末 20 行):")
                lines.append(excerpt)
            if t.artifacts:
                arts = []
                for kind, files in t.artifacts.items():
                    if files:
                        arts.append(f"{kind}: {len(files)} 个")
                if arts:
                    lines.append(f"- **Artifacts**: {' / '.join(arts)}")
            lines.append("")

    # 末尾提示
    lines.append("---")
    lines.append("")
    lines.append("**Artifacts 目录**: `./test-results/artifacts/`")
    lines.append("**HTML 报告**: `./test-results/report.html`")
    lines.append("**JUnit XML**: `./test-results/report.xml`")
    lines.append("")
    return "\n".join(lines)


def to_summary_line(doc: ReportDocument) -> str:
    """单行 CI/CD 友好摘要"""
    s = doc.suite
    status_emoji = "✅" if s.failed == 0 and s.errors == 0 else "❌"
    return (
        f"{status_emoji} UI Test: "
        f"{s.passed}/{s.total} passed ({s.pass_rate:.1f}%) | "
        f"{s.failed} failed, {s.errors} errors, {s.skipped} skipped | "
        f"{s.total_duration:.1f}s"
    )


# ============================================================
# 主流程
# ============================================================

def build_report(
    junit_xml: Path, artifacts_dir: Path, output_dir: Path
) -> ReportDocument:
    tests, summary = parse_junit_xml(junit_xml)

    # 关联 artifacts
    associate_artifacts(tests, artifacts_dir)

    # 聚合
    by_priority, by_module, by_scene = aggregate_by_marker(tests)

    # 失败用例
    failures = [t for t in tests if t.status in ("failed", "error")]

    return ReportDocument(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        suite=summary,
        by_priority=by_priority,
        by_module=by_module,
        by_browser={},
        failures=failures,
        tests=tests,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="UI 测试执行结果统一报告生成器"
    )
    parser.add_argument("--junit-xml", required=True, help="JUnit XML 报告路径")
    parser.add_argument("--artifacts-dir", help="artifacts 根目录（用于关联截图/视频/Trace）")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    parser.add_argument("--formats", nargs="+", default=["json", "md", "summary"],
                        choices=["json", "md", "summary"],
                        help="输出格式（默认全部）")
    args = parser.parse_args(argv)

    junit_xml = Path(args.junit_xml).resolve()
    artifacts_dir = Path(args.artifacts_dir).resolve() if args.artifacts_dir else junit_xml.parent / "artifacts"
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = build_report(junit_xml, artifacts_dir, output_dir)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    written: list[str] = []

    if "json" in args.formats:
        json_path = output_dir / "report.json"
        json_path.write_text(to_json(doc), encoding="utf-8")
        written.append(str(json_path))

    if "md" in args.formats:
        md_path = output_dir / "summary.md"
        md_path.write_text(to_markdown(doc), encoding="utf-8")
        written.append(str(md_path))

    if "summary" in args.formats:
        summary_line = to_summary_line(doc)
        summary_path = output_dir / "summary.txt"
        summary_path.write_text(summary_line + "\n", encoding="utf-8")
        written.append(str(summary_path))
        # 同时打到 stderr（CI 日志友好）
        print(f"\n[SUMMARY] {summary_line}", file=sys.stderr)

    for p in written:
        print(f"[OK] 已生成 {p}", file=sys.stderr)

    # 退出码: 0 = 全过, 1 = 有失败, 2 = 异常
    s = doc.suite
    if s.failed > 0 or s.errors > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
