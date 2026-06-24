"""merge_reports.py — 合并多轮 JUnit XML 为单一完整报告

用法:
    python merge_reports.py \
        --base test-results/report-round-0.xml \
        --overlay test-results/report-round-1.xml \
        [--overlay test-results/report-round-N.xml ...] \
        --output test-results/report.xml

合并规则:
    1. 以 --base 为基底（通常含所有用例的首轮完整结果）
    2. 每个 --overlay 按 (classname, name) 唯一键覆盖基底中的同名用例
    3. 重新统计每个 testsuite 的 tests/failures/errors/skipped 计数
    4. 写入 --output

用途:
    ui-pipeline-scheduler Step 4.5，把首轮完整 XML + 多轮重试 XML 合并成
    最终报告用的 XML，保证 generate_report.py 看到的是完整 N 条用例
    （每条用例展示「最新一次执行结果」）。
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="merge_reports.py",
        description="合并多轮 JUnit XML，输出完整 N 条用例的最终 XML",
    )
    p.add_argument("--base", type=Path, required=True, help="首轮完整 XML（基底）")
    p.add_argument("--overlay", type=Path, action="append", default=[], required=True,
                   help="后续轮 XML（可多次指定，按顺序覆盖）")
    p.add_argument("--output", type=Path, required=True, help="合并后输出路径")
    return p.parse_args(argv)


def case_key(tc: ET.Element) -> tuple[str, str]:
    """testcase 唯一键：(classname, name)。参数化变体的 name 含 [...] 后缀天然区分。"""
    return (tc.get("classname", ""), tc.get("name", ""))


def read_overlay_cases(overlay_path: Path) -> dict[tuple[str, str], ET.Element]:
    """读 overlay XML，返回 {key: testcase_element} 字典（深拷贝）。"""
    tree = ET.parse(overlay_path)
    root = tree.getroot()
    return {case_key(tc): tc for tc in root.iter("testcase")}


def replace_testcase(target: ET.Element, source: ET.Element) -> None:
    """用 source 的属性和子节点完全替换 target（保持 target 在父节点中的位置）。"""
    for k in list(target.attrib.keys()):
        del target.attrib[k]
    for child in list(target):
        target.remove(child)
    for k, v in source.attrib.items():
        target.set(k, v)
    for child in source:
        target.append(child)


def merge_overlay_into_base(base_root: ET.Element, overlay_cases: dict[tuple[str, str], ET.Element]) -> int:
    """把 overlay_cases 合并进 base_root，返回成功替换的用例数。"""
    replaced = 0
    for tc in base_root.iter("testcase"):
        key = case_key(tc)
        if key in overlay_cases:
            replace_testcase(tc, overlay_cases[key])
            replaced += 1
    return replaced


def recompute_stats(root: ET.Element) -> None:
    """重新统计 testsuite + testsuites 根节点的 tests/failures/errors/skipped 属性。"""
    for suite in root.iter("testsuite"):
        cases = suite.findall("testcase")
        suite.set("tests", str(len(cases)))
        suite.set("failures", str(sum(1 for c in cases if c.find("failure") is not None)))
        suite.set("errors", str(sum(1 for c in cases if c.find("error") is not None)))
        suite.set("skipped", str(sum(1 for c in cases if c.find("skipped") is not None)))

    if root.tag == "testsuites":
        all_cases = list(root.iter("testcase"))
        root.set("tests", str(len(all_cases)))
        root.set("failures", str(sum(1 for c in all_cases if c.find("failure") is not None)))
        root.set("errors", str(sum(1 for c in all_cases if c.find("error") is not None)))
        root.set("skipped", str(sum(1 for c in all_cases if c.find("skipped") is not None)))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.base.exists():
        print(f"[ERROR] 基底 XML 不存在: {args.base}", file=sys.stderr)
        return 2

    base_tree = ET.parse(args.base)
    base_root = base_tree.getroot()
    base_keys = {case_key(tc) for tc in base_root.iter("testcase")}
    print(f"[merge] 基底 {args.base.name}: {len(base_keys)} 条用例")

    for overlay_path in args.overlay:
        if not overlay_path.exists():
            print(f"[merge] WARN: overlay 不存在，跳过: {overlay_path}", file=sys.stderr)
            continue
        overlay_cases = read_overlay_cases(overlay_path)
        matched = sum(1 for k in overlay_cases if k in base_keys)
        extra = len(overlay_cases) - matched
        replaced = merge_overlay_into_base(base_root, overlay_cases)
        print(f"[merge] + {overlay_path.name}: {len(overlay_cases)} 条（匹配 {matched}，覆盖 {replaced}，额外 {extra}）")
        if extra > 0:
            print(f"[merge]   WARN: {extra} 条 overlay 用例不在 base 中（已忽略）", file=sys.stderr)

    recompute_stats(base_root)
    base_root.set("timestamp", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    base_tree.write(args.output, encoding="utf-8", xml_declaration=True)

    final_cases = list(base_root.iter("testcase"))
    final_fail = sum(1 for c in final_cases if c.find("failure") is not None)
    final_err = sum(1 for c in final_cases if c.find("error") is not None)
    print(f"[merge] 输出 {args.output}: {len(final_cases)} 条用例（failures={final_fail} errors={final_err}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
