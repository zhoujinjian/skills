"""generate_report.py — ui-report-generator CLI 主入口

输入（按优先级）：
    --junit-xml (必需)         pytest JUnit XML
    --exec-json (可选)         ui-test-executor/generate_report.py 的 report.json
    --diagnose-md (可选)       ui-failure-diagnoser 的 ui_repair_report.md
    --artifacts-dir (可选)     失败 artifact 根目录
    --browser-env-json (可选)  detect_browsers.py 的 browser_env.json
    --history-json (可选)      历次执行累积，用于趋势图

输出：
    单文件 HTML 报告（含 base64 截图、CDN Chart.js、Trace 打开命令）
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# 让 scripts/ 内的模块互导（直接运行时需要）
sys.path.insert(0, str(Path(__file__).parent))

from analyzer import (  # noqa: E402
    aggregate_by_browser,
    aggregate_by_module,
    aggregate_by_priority,
    aggregate_diagnose,
    analyze_risk,
    cluster_failures,
    generate_suggestions,
)
from parsers import (  # noqa: E402
    ReportDocument,
    UISuiteSummary,
    attach_artifacts,
    load_browser_env,
    load_exec_json,
    load_history,
    parse_diagnose_md,
    parse_junit_xml,
)
from renderer import render_html  # noqa: E402


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="generate_report.py",
        description="ui-report-generator — UI 自动化测试报告生成",
    )
    p.add_argument("--junit-xml", type=Path, required=True, help="JUnit XML 路径")
    p.add_argument("--exec-json", type=Path, help="ui-test-executor report.json（可选，更丰富字段）")
    p.add_argument("--diagnose-md", type=Path, help="ui-failure-diagnoser ui_repair_report.md（可选）")
    p.add_argument("--artifacts-dir", type=Path, help="artifacts 根目录（可选）")
    p.add_argument("--browser-env-json", type=Path, help="detect_browsers.py browser_env.json（可选）")
    p.add_argument("--history-json", type=Path, help="历史执行 JSON（可选，用于趋势图）")
    p.add_argument("--output", type=Path, default=Path("./ui_test_report.html"),
                   help="HTML 输出路径，默认 ./ui_test_report.html")
    p.add_argument("--title", default="UI 自动化测试报告", help="报告标题")
    p.add_argument("--trace-launch-cmd", default=None,
                   help="Trace 打开命令模板，含 {trace_path} 占位（默认：python -m playwright show-trace {trace_path}）")
    p.add_argument("--no-inline-screenshots", action="store_true",
                   help="不内联截图 base64（生成相对路径 <img>，HTML 文件更小）")
    p.add_argument("--allure-url", default=None,
                   help="Allure 报告 URL（如 http://localhost:8088）；不指定则按 --auto-allure 探测")
    p.add_argument("--allure-url-file", type=Path, default=None,
                   help="Allure URL 文件路径（ui-test-executor --allure 写入）；默认查 <junit-xml 同目录>/allure_url.txt")
    p.add_argument("--auto-allure", action="store_true",
                   help="自动探测：先读 allure_url.txt，再探 localhost:8088；都失败则按钮 disabled")
    p.add_argument("--no-allure", action="store_true",
                   help="强制不渲染 Allure 入口（用于无 Allure 环境）")
    p.add_argument("--no-auto-open-traces", action="store_true",
                   help="不自动启动 Trace Viewer（默认对每个失败 trace.zip 后台启动 playwright show-trace）")
    return p


def _resolve_allure_url(args: argparse.Namespace) -> str | None:
    """解析 Allure URL：显式 > URL 文件 > 端口探测 > None。

    优先级：
        1. --no-allure → None
        2. --allure-url → 直接用
        3. --auto-allure 启用时：
           a) --allure-url-file 或 <junit-xml 同目录>/allure_url.txt
           b) 探测 localhost:8088（allure open 默认端口）
        4. 否则 None
    """
    if args.no_allure:
        return None
    if args.allure_url:
        return args.allure_url
    if not args.auto_allure:
        return None

    # a) 读 allure_url.txt
    url_file = args.allure_url_file or (args.junit_xml.parent / "allure_url.txt")
    if url_file.exists():
        url = url_file.read_text(encoding="utf-8").strip()
        if url and _probe_allure_url(url):
            return url
        if url:
            # 文件有 URL 但服务不可达，回退到探测
            print(f"[report] allure_url.txt 指向 {url} 但不可达，尝试探测 localhost", file=sys.stderr)

    # b) 探测默认端口
    return _probe_allure_url()


def _probe_allure_url(url_or_port: str | int = 8088, timeout: float = 1.0) -> str | None:
    """探测本地 allure open 服务，仅返回 200/3xx 时认为可用。

    Args:
        url_or_port: URL 字符串（如 http://localhost:8088）或端口号（int）
        timeout: 超时秒数
    """
    import urllib.request
    import urllib.error
    if isinstance(url_or_port, int):
        url = f"http://localhost:{url_or_port}"
    else:
        url = url_or_port
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 400:
                return url
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError):
        return None
    return None


def build_document(args: argparse.Namespace) -> ReportDocument:
    """编排数据解析 + 聚合分析。"""
    # 1. 解析 JUnit
    suite, cases = parse_junit_xml(args.junit_xml)

    # 2. 附加 artifacts（仅失败用例需要，但全扫一遍无害）
    if args.artifacts_dir:
        attach_artifacts(cases, args.artifacts_dir)

    # 3. 解析诊断报告
    diagnose_records = []
    diagnose_overview = {}
    if args.diagnose_md and args.diagnose_md.exists():
        diagnose_records, diagnose_overview = parse_diagnose_md(args.diagnose_md)

    # 4. 聚合分析
    by_module = aggregate_by_module(cases)
    by_priority = aggregate_by_priority(cases)
    by_browser = aggregate_by_browser(cases)
    by_category, by_root_cause = aggregate_diagnose(diagnose_records)

    # 5. 历史数据
    history = load_history(args.history_json)

    # 6. 浏览器环境
    browser_env = load_browser_env(args.browser_env_json)

    # 7. exec.json 的额外信息（如果给了）
    exec_json = load_exec_json(args.exec_json)
    meta = {}
    if exec_json:
        meta["exec_json_source"] = str(args.exec_json)

    failures = [c for c in cases if c.status in ("failed", "error")]

    return ReportDocument(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        suite=suite,
        tests=cases,
        failures=failures,
        diagnose_records=diagnose_records,
        diagnose_overview=diagnose_overview,
        by_module=by_module,
        by_priority=by_priority,
        by_browser=by_browser,
        by_category=by_category,
        by_root_cause=by_root_cause,
        artifact_root=str(args.artifacts_dir) if args.artifacts_dir else None,
        browser_env=browser_env,
        history=history,
        meta=meta,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)

    if not args.junit_xml.exists():
        print(f"[ERROR] JUnit XML 不存在：{args.junit_xml}", file=sys.stderr)
        return 2

    doc = build_document(args)

    # 截图内联策略
    artifact_base = args.artifacts_dir if args.no_inline_screenshots else None
    if args.no_inline_screenshots:
        # 清空 base64 路径，让 renderer 走相对路径
        for f in doc.failures:
            f.artifacts = {k: v for k, v in f.artifacts.items()}

    trace_cmd = args.trace_launch_cmd or "python -m playwright show-trace {trace_path}"

    html_text = render_html(
        doc,
        title=args.title,
        artifact_base=artifact_base,
        trace_launch_cmd_template=trace_cmd,
        allure_url=_resolve_allure_url(args),
        report_output_path=args.output,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html_text, encoding="utf-8")

    allure_state = "active" if _resolve_allure_url(args) else "disabled"

    # 自动启动 Trace Viewer（detached），让用户点击按钮时窗口已就绪
    started_traces = _maybe_open_traces(doc, trace_cmd) if not args.no_auto_open_traces else 0

    print(f"[report] 已生成：{args.output}")
    print(f"[report] 用例：{doc.suite.total}（pass={doc.suite.passed} fail={doc.suite.failed}）")
    print(f"[report] 模块：{len(doc.by_module)} · 浏览器：{len(doc.by_browser)} · 诊断：{len(doc.diagnose_records)}")
    print(f"[report] Allure：{allure_state}")
    if started_traces:
        print(f"[report] Trace Viewer 已启动：{started_traces} 个失败用例的 trace.zip 在新窗口打开")
    return 0


def _maybe_open_traces(doc: ReportDocument, trace_cmd_template: str) -> int:
    """对每个失败用例的 trace.zip 后台启动 playwright show-trace。

    浏览器沙箱无法直接执行 shell 命令，所以在报告生成阶段就启动好 Trace Viewer，
    用户点击 HTML 按钮时窗口已存在；HTML 按钮文案为「Trace Viewer 已启动」。

    Returns:
        成功启动的 trace 数量
    """
    import shutil
    import subprocess

    python_bin = sys.executable or "python3"
    started = 0
    for f in doc.failures:
        traces = f.artifacts.get("traces") or []
        if not traces:
            continue
        trace_path = Path(traces[0])
        if not trace_path.exists():
            continue
        try:
            # detached 启动，父进程退出后 trace viewer 继续运行
            subprocess.Popen(
                [python_bin, "-m", "playwright", "show-trace", str(trace_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            started += 1
        except Exception as e:
            print(f"[report] WARN: 启动 Trace Viewer 失败 ({trace_path.name}): {e}", file=sys.stderr)
    return started


if __name__ == "__main__":
    sys.exit(main())
