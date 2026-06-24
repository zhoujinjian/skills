#!/usr/bin/env python3
"""
generate_failure_analysis.py — 失败用例 Markdown 故障分析报告生成器

输入:
  - JUnit XML (test-results/report.xml) — 失败用例的权威来源
  - failure-context/<nodeid>.json sidecar — conftest 落的深度信息
  - pytest-raw/<slug>/{video.webm,trace.zip} — pytest-playwright 原生产物

输出:
  - test-results/failure_analysis.md（仅当 ≥1 失败时生成）

降级链：
  sidecar JSON 缺失 → 退化到 JUnit XML 渲染（仅 nodeid+message+traceback）
  JUnit XML 解析失败 → 退出码 2，stderr 报错

用法:
  python3 generate_failure_analysis.py \
      --junit-xml ./test-results/report.xml \
      --artifacts-dir ./test-results/artifacts \
      --output-dir ./test-results
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FailureCase:
    """从 JUnit XML 解析出的失败用例"""
    nodeid: str          # classname::name 拼回（粗略）
    classname: str
    name: str
    file: str = ""
    line: str = ""
    duration: float = 0.0
    message: str = ""
    traceback: str = ""
    sidecar: dict = field(default_factory=dict)  # failure-context/<nodeid>.json 内容（可选）


def parse_junit_failures(xml_path: Path) -> list[FailureCase]:
    """从 JUnit XML 解析所有 failed 用例（含 setup 阶段的 error）

    JUnit XML 结构：
        <testsuite>
          <testcase classname time file line>
            <failure message type>traceback</failure>  # call 阶段失败
            <error message type>traceback</error>      # setup 阶段失败
            <system-out>...</system-out>
          </testcase>
        </testsuite>
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    failures: list[FailureCase] = []
    for tc in root.iter("testcase"):
        # 失败标志：有 <failure> 或 <error> 子节点
        fail_node = tc.find("failure")
        err_node = tc.find("error")
        bad_node = fail_node if fail_node is not None else err_node
        if bad_node is None:
            continue

        # nodeid 拼回：JUnit 把 nodeid 拆成 classname + name
        # 但参数化方括号在 name 里
        classname = tc.attrib.get("classname", "")
        name = tc.attrib.get("name", "")
        nodeid = f"{classname}::{name}" if classname else name

        case = FailureCase(
            nodeid=nodeid,
            classname=classname,
            name=name,
            file=tc.attrib.get("file", ""),
            line=tc.attrib.get("line", ""),
            duration=float(tc.attrib.get("time", "0") or "0"),
            message=bad_node.attrib.get("message", "") or "",
            traceback=(bad_node.text or "").strip(),
        )
        failures.append(case)

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="失败用例 Markdown 故障分析报告生成器")
    parser.add_argument("--junit-xml", required=True, help="JUnit XML 报告路径")
    parser.add_argument("--artifacts-dir", default="./test-results/artifacts", help="artifact 根目录")
    parser.add_argument("--output-dir", default=".", help="MD 输出目录")
    parser.add_argument("--execution-summary", default="", help="执行概述（用于报告头部，如 'P0 and run_smoke · chromium · headless'）")
    args = parser.parse_args(argv)

    junit_path = Path(args.junit_xml).resolve()
    if not junit_path.exists():
        print(f"[ERROR] JUnit XML 不存在: {junit_path}", file=sys.stderr)
        return 2

    failures = parse_junit_failures(junit_path)
    if not failures:
        print(f"[OK] 无失败用例，不生成 failure_analysis.md", file=sys.stderr)
        return 0

    print(f"[INFO] 检测到 {len(failures)} 个失败用例，开始生成 failure_analysis.md", file=sys.stderr)

    # 渲染（Task 7-10 实现）
    md = render_failure_analysis(
        failures=failures,
        artifacts_dir=Path(args.artifacts_dir).resolve(),
        execution_summary=args.execution_summary,
    )

    output_path = Path(args.output_dir).resolve() / "failure_analysis.md"
    output_path.write_text(md, encoding="utf-8")
    print(f"[OK] 已生成 {output_path}", file=sys.stderr)
    return 0


def _is_playwright_expect_failure(sidecar: dict) -> bool:
    """判断是否 playwright expect 失败（vs 原生 assert 失败）"""
    ef = sidecar.get("expect_failure", {}) or {}
    return any([ef.get("locator"), ef.get("expected"), ef.get("received"), ef.get("action")])


def render_failure_section(case: FailureCase, sidecar: dict, video_trace: dict) -> str:
    """渲染单条失败用例的 MD 章节

    Args:
        case: 从 JUnit XML 解析出的失败用例
        sidecar: failure-context/<nodeid>.json 内容（可能为空 dict = 降级模式）
        video_trace: {"video": str, "trace": str} 路径，空 dict = 未生成

    返回 MD 字符串（不含顶部 ## 标题前的空行；末尾含 ---）
    """
    lines: list[str] = []

    # 章节标题：rule 首行 或 函数名
    title_rule = (sidecar.get("rule") or "").splitlines()[0] if sidecar.get("rule") else case.name
    lines.append(f"## ❌ {title_rule}")
    lines.append("")

    # 元信息行
    phase = sidecar.get("phase", "main")
    duration = sidecar.get("duration") or case.duration
    browser = sidecar.get("browser", "")
    failure_type = sidecar.get("failure_type", "")
    meta_parts = [f"**阶段**: {phase}", f"**耗时**: {duration:.2f}s"]
    if browser:
        meta_parts.append(f"**浏览器**: {browser}")
    if failure_type:
        meta_parts.append(f"**失败类型**: {failure_type}")
    lines.append(f"**位置**: `{case.nodeid}`")
    lines.append(" · ".join(meta_parts))
    lines.append("")

    # 判定规则
    lines.append("### 判定规则")
    rule = sidecar.get("rule", "")
    if rule:
        lines.append(f"> {rule}")
        lines.append("")
        rule_source = sidecar.get("rule_source", "")
        if rule_source == "fallback_funcname":
            lines.append("> 📌 **来源**: 函数名 fallback（无 docstring）")
        elif rule_source == "docstring_unmatched_param":
            lines.append("> 📌 **来源**: docstring（含未匹配的参数化占位符）")
        else:
            lines.append("> 📌 **来源**: 测试 docstring 首行")
        lines.append("")
    else:
        lines.append("> *(无 sidecar，rule 字段缺失，详见断言原文)*")
        lines.append("")

    # 断言原文
    lines.append("### 断言原文")
    assertion = sidecar.get("assertion", {}) or {}
    statement = assertion.get("statement", "")
    file_loc = assertion.get("file", "")
    if statement:
        lines.append("```python")
        if file_loc:
            lines.append(f"# {file_loc}")
        lines.append(statement)
        lines.append("```")
    else:
        lines.append("*(sidecar 缺失或解析失败)*")
    lines.append("")

    # 预期 vs 实际
    lines.append("### 预期 vs 实际（pytest 内省）")
    introspection = assertion.get("introspection", "")
    if introspection:
        lines.append("```")
        lines.append(introspection)
        lines.append("```")
    else:
        lines.append("*(无内省信息)*")
    lines.append("")

    # 页面元素校验
    lines.append("### 页面元素校验")
    ef = sidecar.get("expect_failure", {}) or {}
    url = sidecar.get("url", "") or case.message
    is_pw = _is_playwright_expect_failure(sidecar)
    lines.append("| 字段 | 值 |")
    lines.append("|------|---|")
    lines.append(f"| 失败 URL | `{url}` |")
    if is_pw:
        lines.append(f"| 定位器 | `{ef.get('locator', '')}` |")
        lines.append(f"| 期望 | {ef.get('expected', '')} |")
        lines.append(f"| 实际 | {ef.get('received', '')} |")
    else:
        lines.append("| 定位器 | *(原生 assert，无 playwright 错误结构)* |")
        lines.append("| 期望 | *(原生 assert，未提取)* |")
        lines.append("| 实际 | *(原生 assert，未提取)* |")
    hint = ef.get("hint", "")
    lines.append(f"| 推断原因 | {hint or '（无）'} |")
    lines.append("")
    if not is_pw:
        lines.append("> ⚠️ 本用例是**原生 assert** 失败（非 playwright expect）。")
        lines.append("> 「定位器/期望/实际」仅在 playwright expect 失败时从错误消息结构化提取。")
        lines.append("")
    raw = ef.get("raw", "")
    if raw and not is_pw:
        lines.append("**错误消息原文**：")
        lines.append("```")
        lines.append(raw[:500])
        lines.append("```")
        lines.append("")

    # 失败截图
    lines.append("### 失败截图")
    lines.append("| 类型 | 路径 |")
    lines.append("|------|------|")
    artifacts = sidecar.get("artifacts", {}) or {}
    screenshots = artifacts.get("screenshots", [])
    if isinstance(screenshots, list) and len(screenshots) >= 2:
        lines.append(f"| 视口截图 | `{screenshots[0]}` |")
        lines.append(f"| 全页截图 | `{screenshots[1]}` |")
    elif screenshots:
        for s in screenshots:
            lines.append(f"| 截图 | `{s}` |")
    else:
        lines.append("| 视口截图 | *(未采集)* |")
        lines.append("| 全页截图 | *(未采集)* |")
    # Playwright 原生失败截图（在 pytest-raw/<slug>/test-failed-N.png）
    if video_trace.get("native_screenshot"):
        lines.append(f"| Playwright 原生失败截图 | `{video_trace['native_screenshot']}` |")
    lines.append("")

    # 失败录屏与 Trace
    lines.append("### 失败录屏与 Trace")
    lines.append("| 类型 | 路径 | 复现命令 |")
    lines.append("|------|------|---------|")
    video = video_trace.get("video", "")
    trace = video_trace.get("trace", "")
    if video:
        lines.append(f"| 录屏 | `{video}` | `open {video}` |")
    elif video_trace.get("_multi_candidate"):
        lines.append("| 录屏 | ⚠️ 多个候选目录匹配，请人工确认 | - |")
    else:
        lines.append("| 录屏 | *(未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off)* | - |")
    if trace:
        lines.append(f"| Trace | `{trace}` | `python3 -m playwright show-trace {trace}` |")
    elif video_trace.get("_multi_candidate"):
        lines.append("| Trace | ⚠️ 多个候选目录匹配，请人工确认 | - |")
    else:
        lines.append("| Trace | *(未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off)* | - |")
    lines.append("")

    # 其他诊断材料
    lines.append("### 其他诊断材料")
    page_source = artifacts.get("page_source", "")
    console_log = artifacts.get("console_log", "")
    if page_source:
        lines.append(f"- 页面源码: `{page_source}`")
    if console_log:
        lines.append(f"- Console 日志: `{console_log}`")
    if url:
        lines.append(f"- 失败时 URL: `{url}`")
    lines.append("")

    lines.append("---")
    return "\n".join(lines)


def render_failure_analysis(failures: list[FailureCase], artifacts_dir: Path, execution_summary: str) -> str:
    """渲染完整 MD：顶部总览 + 每条失败用例一节"""
    from datetime import datetime

    lines: list[str] = []

    # 顶部总览
    lines.append("# 失败用例故障分析报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    exec_line = execution_summary or "(未指定)"
    lines.append(f"**测试执行**: {exec_line}")
    lines.append(f"**失败统计**: {len(failures)} 个失败用例")
    lines.append("")
    lines.append("> 本报告由 `ui-test-executor` 自动生成。每条失败用例一节，含判定规则、")
    lines.append("> 断言详情、元素校验、失败截图与录屏路径。Trace 复现命令见每节末尾。")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 每条失败用例
    for i, case in enumerate(failures, 1):
        # 读 sidecar
        sidecar = _load_sidecar(artifacts_dir, case)
        # 补 video/trace
        video_trace = _resolve_video_trace(sidecar)
        # 渲染
        section = render_failure_section(case, sidecar=sidecar, video_trace=video_trace)
        lines.append(section)
        lines.append("")

    return "\n".join(lines)


def _load_sidecar(artifacts_dir: Path, case: FailureCase) -> dict:
    """从 failure-context/<safe_nodeid>.json 读 sidecar；不存在返回空 dict（降级模式）

    filename 规则必须与 conftest_template.py::_sanitize_filename 完全一致：
    1. `::` → `-`（nodeid 的 class::method 分隔符）
    2. `[]`、空白、`/`、`\\`、`:` → `-`
    3. 非 `[A-Za-z0-9_.-]` → `-`
    4. 截断到 120 字符
    """
    import re
    safe = case.nodeid.replace("::", "-")
    safe = re.sub(r"[\[\]\s/\\:]", "-", safe)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", safe)
    safe = safe[:120]
    sidecar_path = artifacts_dir / "failure-context" / f"{safe}.json"
    if not sidecar_path.exists():
        return {}
    try:
        import json
        return json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_video_trace(sidecar: dict) -> dict:
    """根据 sidecar.slug_hint + sidecar.pytest_raw_dir 补全 video/trace 路径

    匹配策略（按优先级）:
      1. 精确匹配：<pytest_raw_dir>/<slug>/ 存在 → 直接用
      2. glob fallback：pytest-raw 下唯一目录 → 用唯一目录（容错 slug 转义差异）
      3. 多候选：pytest-raw 下多个目录 → 不选，返回 warning

    返回:
        {"video": str, "trace": str, "native_screenshot": str} 中任意子集
        多候选时追加 "_multi_candidate": True
    """
    result: dict[str, object] = {}
    slug = sidecar.get("slug_hint", "")
    pytest_raw_dir = sidecar.get("pytest_raw_dir", "")
    if not pytest_raw_dir:
        return result

    raw_root = Path(pytest_raw_dir)
    if not raw_root.exists():
        return result

    # 1. 精确匹配
    candidate_dirs: list[Path] = []
    if slug:
        exact = raw_root / slug
        if exact.exists() and exact.is_dir():
            candidate_dirs = [exact]

    # 2. fallback：列所有子目录
    if not candidate_dirs:
        all_dirs = [d for d in raw_root.iterdir() if d.is_dir()]
        if len(all_dirs) == 1:
            candidate_dirs = all_dirs
        elif len(all_dirs) > 1 and slug:
            # 尝试按 slug 的前缀匹配（容错 unicode 转义差异）
            slug_lower = slug.lower()
            prefix_matches = [d for d in all_dirs if d.name.lower().startswith(slug_lower[:30])]
            if len(prefix_matches) == 1:
                candidate_dirs = prefix_matches
            else:
                # 多候选不选
                result["_multi_candidate"] = True
                return result

    if not candidate_dirs:
        return result

    base = candidate_dirs[0]
    video = base / "video.webm"
    trace = base / "trace.zip"
    if video.exists():
        result["video"] = str(video)
    if trace.exists():
        result["trace"] = str(trace)
    failed_pngs = sorted(base.glob("test-failed-*.png"))
    if failed_pngs:
        result["native_screenshot"] = str(failed_pngs[0])

    return result


if __name__ == "__main__":
    sys.exit(main())
