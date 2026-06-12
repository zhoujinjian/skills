#!/usr/bin/env python3
"""
api-failure-diagnoser 核心诊断脚本
解析 execution_results.json，对失败用例进行分类和根因定位，输出结构化诊断结果。
"""

import json
import sys
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── 失败类型常量 ──
ENV_ERROR = "ENV_ERROR"
DATA_ERROR = "DATA_ERROR"
SCRIPT_ERROR = "SCRIPT_ERROR"
BUG = "BUG"

# ── 脚本问题根因子类型 ──
ROOT_API_CHANGE = "api_change"
ROOT_OVER_STRICT = "over_strict_assertion"
ROOT_PARAM_ERROR = "param_construction_error"
ROOT_MISSING_HANDLER = "missing_exception_handling"
ROOT_DATA_DEP = "data_dependency_error"
ROOT_TIMING = "timing_issue"
ROOT_UNKNOWN = "unknown"


def load_execution_results(filepath: str) -> dict:
    """加载并校验 execution_results.json"""
    path = Path(filepath)
    if not path.exists():
        print(f"错误：执行结果文件不存在: {filepath}", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "results" not in data and "test_results" not in data:
        print("错误：执行结果文件格式不合法，缺少 results/test_results 字段", file=sys.stderr)
        sys.exit(1)

    return data


def extract_failures(data: dict) -> List[dict]:
    """提取所有失败用例"""
    results = data.get("results") or data.get("test_results") or []
    return [r for r in results if r.get("status", "").upper() == "FAIL"]


# ── 分类判断函数 ──

def _match_env_error(error_msg: str, status_code: Optional[int]) -> bool:
    """判断是否为环境问题"""
    env_patterns = [
        r"ConnectTimeout", r"ConnectionTimeout", r"ConnectionRefused",
        r"Connection refused", r"Max retries exceeded",
        r"NameResolutionError", r"DNS resolution failed", r"getaddrinfo failed",
        r"Network is unreachable", r"NewConnectionError",
    ]
    for pat in env_patterns:
        if re.search(pat, error_msg, re.IGNORECASE):
            return True
    if status_code in (502, 503, 504):
        return True
    return False


def _match_data_error(error_msg: str, status_code: Optional[int]) -> bool:
    """判断是否为数据问题"""
    data_patterns = [
        r"UniqueViolation", r"DuplicateKeyError", r"IntegrityError",
        r"ForeignKeyViolation",
    ]
    for pat in data_patterns:
        if re.search(pat, error_msg, re.IGNORECASE):
            return True

    # 401/403 — 排除脚本传错 Token 的情况
    if status_code in (401, 403):
        if "token" not in error_msg.lower() or "field" not in error_msg.lower():
            return True

    # 404 — 仅当错误信息表明是"资源不存在"而非"路径不存在"
    if status_code == 404:
        resource_patterns = [
            r"resource not found", r"record not found", r"数据不存在",
            r"已删除", r"已过期",
        ]
        for pat in resource_patterns:
            if re.search(pat, error_msg, re.IGNORECASE):
                return True

    return False


def _match_bug(error_msg: str, status_code: Optional[int]) -> bool:
    """判断是否为产品缺陷"""
    if status_code == 500:
        bug_indicators = [
            r"NullPointerException", r"IndexOutOfBoundsException",
            r"RuntimeError", r"内部错误", r"Internal Server Error",
        ]
        for pat in bug_indicators:
            if re.search(pat, error_msg, re.IGNORECASE):
                return True
        # 500 + 有响应体 = 可能是业务逻辑异常
        return True
    return False


def classify_failure(case: dict, service_healthy: bool = True) -> Tuple[str, str]:
    """
    对失败用例进行分类。
    返回 (failure_type, root_cause) 元组。
    """
    error_msg = case.get("error_message", "") or case.get("error", "") or case.get("longrepr", "") or ""
    status_code = None

    # 从错误信息或响应中提取 HTTP 状态码
    resp = case.get("response") or {}
    if isinstance(resp, dict):
        status_code = resp.get("status_code") or resp.get("statusCode")

    # 从错误信息文本中提取状态码
    status_match = re.search(r"(\d{3})\s+(?:Client|Server)\s+Error", error_msg)
    if status_match and not status_code:
        status_code = int(status_match.group(1))

    # 按优先级判定
    if _match_env_error(error_msg, status_code):
        return ENV_ERROR, ""

    if _match_data_error(error_msg, status_code):
        return DATA_ERROR, ""

    if _match_bug(error_msg, status_code):
        return BUG, ""

    # 剩余归为脚本问题，进一步定位根因
    root_cause = _locate_script_root_cause(error_msg, status_code, case)
    return SCRIPT_ERROR, root_cause


def _locate_script_root_cause(error_msg: str, status_code: Optional[int], case: dict) -> str:
    """定位脚本问题的根因子类型"""
    # AssertionError → 检查是否断言过严
    if "AssertionError" in error_msg or "AssertionError" in error_msg:
        # 检查是否涉及时间戳/ID等不稳定字段
        unstable_patterns = [
            r"createdAt", r"updatedAt", r"timestamp", r"date",
            r"time.*match", r"expected.*got",
        ]
        for pat in unstable_patterns:
            if re.search(pat, error_msg, re.IGNORECASE):
                return ROOT_OVER_STRICT
        return ROOT_UNKNOWN

    # KeyError → 异常处理缺失
    if "KeyError" in error_msg:
        return ROOT_MISSING_HANDLER

    # TypeError / ValueError → 参数构造错误或数据依赖
    if "TypeError" in error_msg or "ValueError" in error_msg:
        if "NoneType" in error_msg:
            return ROOT_DATA_DEP
        return ROOT_PARAM_ERROR

    # 404/405 且服务正常 → 接口路径变更
    if status_code in (404, 405):
        return ROOT_API_CHANGE

    # NoneType → 数据依赖错误
    if "NoneType" in error_msg or "'None'" in error_msg:
        return ROOT_DATA_DEP

    # JSONDecodeError → 参数构造
    if "JSONDecodeError" in error_msg:
        return ROOT_PARAM_ERROR

    return ROOT_UNKNOWN


def generate_report(
    failures: List[dict],
    classifications: List[Tuple[str, str, dict]],
    output_dir: str,
) -> str:
    """
    生成 repair_report.md 诊断报告。
    classifications: [(failure_type, root_cause, original_case), ...]
    """
    counts = {ENV_ERROR: 0, DATA_ERROR: 0, SCRIPT_ERROR: 0, BUG: 0}
    script_issues = []
    env_issues = []
    data_issues = []
    bug_issues = []

    for i, (ftype, root, case) in enumerate(classifications):
        counts[ftype] += 1
        entry = {
            "index": i + 1,
            "case": case.get("nodeid", case.get("name", f"unknown_{i}")),
            "error": (case.get("error_message") or case.get("error") or case.get("longrepr") or "")[:500],
            "file": case.get("file", case.get("filename", "")),
        }
        if ftype == SCRIPT_ERROR:
            entry["root_cause"] = root
            script_issues.append(entry)
        elif ftype == ENV_ERROR:
            env_issues.append(entry)
        elif ftype == DATA_ERROR:
            data_issues.append(entry)
        else:
            bug_issues.append(entry)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# 接口测试脚本修复报告",
        f"",
        f"> 生成时间：{now}",
        f"",
        f"## 执行摘要",
        f"",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 分析用例数 | {len(failures)} |",
        f"| 环境问题 | {counts[ENV_ERROR]}（不修复） |",
        f"| 数据问题 | {counts[DATA_ERROR]}（不修复） |",
        f"| 脚本问题 | {counts[SCRIPT_ERROR]}（可修复） |",
        f"| 产品缺陷 | {counts[BUG]}（不修复，已生成Bug报告） |",
        f"",
    ]

    if script_issues:
        lines.append("## 脚本问题详情")
        lines.append("")
        root_cause_names = {
            ROOT_API_CHANGE: "接口变更",
            ROOT_OVER_STRICT: "断言过严",
            ROOT_PARAM_ERROR: "参数构造错误",
            ROOT_MISSING_HANDLER: "异常处理缺失",
            ROOT_DATA_DEP: "数据依赖错误",
            ROOT_TIMING: "时序/异步问题",
            ROOT_UNKNOWN: "待进一步分析",
        }
        for issue in script_issues:
            rc_name = root_cause_names.get(issue["root_cause"], "未知")
            lines.extend([
                f"### 问题 {issue['index']}：{rc_name}",
                f"- **用例**：`{issue['case']}`",
                f"- **失败信息**：`{issue['error'][:200]}`",
                f"- **根因类型**：{rc_name}",
                f"- **修复状态**：待修复",
                f"",
            ])

    if env_issues or data_issues:
        lines.append("## 未修复问题（需人工处理）")
        lines.append("")
        if env_issues:
            lines.append("### 环境问题")
            for issue in env_issues:
                lines.extend([
                    f"- **用例**：`{issue['case']}`",
                    f"  - 失败信息：`{issue['error'][:200]}`",
                    f"  - 建议：检查目标服务是否启动，网络配置是否正确",
                ])
            lines.append("")
        if data_issues:
            lines.append("### 数据问题")
            for issue in data_issues:
                lines.extend([
                    f"- **用例**：`{issue['case']}`",
                    f"  - 失败信息：`{issue['error'][:200]}`",
                    f"  - 建议：检查测试数据是否有效，依赖资源是否存在",
                ])
            lines.append("")

    if bug_issues:
        lines.append("### 产品缺陷（已生成Bug报告）")
        for issue in bug_issues:
            bug_id = f"BUG_{datetime.now().strftime('%Y%m%d')}_{issue['index']:03d}"
            lines.extend([
                f"- **用例**：`{issue['case']}`",
                f"  - Bug ID：{bug_id}",
                f"  - 失败信息：`{issue['error'][:200]}`",
            ])
        lines.append("")

    report_path = Path(output_dir) / "repair_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return str(report_path)


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="api-failure-diagnoser 诊断脚本")
    parser.add_argument("project_dir", help="测试脚本项目目录")
    parser.add_argument("--execution-results", required=True, help="execution_results.json 路径")
    parser.add_argument("--output-dir", default="./diagnosis_output", help="诊断输出目录")
    args = parser.parse_args()

    # 加载执行结果
    data = load_execution_results(args.execution_results)
    failures = extract_failures(data)

    if not failures:
        print("没有发现失败用例，无需诊断。")
        sys.exit(0)

    print(f"发现 {len(failures)} 个失败用例，开始诊断...")

    # 分类
    classifications = []
    for case in failures:
        ftype, root = classify_failure(case)
        classifications.append((ftype, root, case))
        case_name = case.get("nodeid", case.get("name", "unknown"))
        print(f"  [{ftype}] {case_name}" + (f" (根因: {root})" if root else ""))

    # 生成报告
    report_path = generate_report(failures, classifications, args.output_dir)
    print(f"\n诊断报告已生成：{report_path}")

    # 统计
    counts = {}
    for ftype, _, _ in classifications:
        counts[ftype] = counts.get(ftype, 0) + 1

    print(f"\n分类统计：")
    print(f"  环境问题: {counts.get(ENV_ERROR, 0)}")
    print(f"  数据问题: {counts.get(DATA_ERROR, 0)}")
    print(f"  脚本问题: {counts.get(SCRIPT_ERROR, 0)}（可自动修复）")
    print(f"  产品缺陷: {counts.get(BUG, 0)}")


if __name__ == "__main__":
    main()
