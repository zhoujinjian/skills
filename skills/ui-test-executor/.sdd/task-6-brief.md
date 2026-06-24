### Task 6: 脚本骨架 + JUnit XML 解析（复用 generate_report 模式）

**Files:**
- Create: `scripts/generate_failure_analysis.py`

- [ ] **Step 1: 写脚本骨架（仅含 main + XML 解析，渲染留 TODO 占位由后续 Task 实现）**

文件 `scripts/generate_failure_analysis.py`：

```python
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


def render_failure_analysis(failures: list[FailureCase], artifacts_dir: Path, execution_summary: str) -> str:
    """渲染完整 MD（Task 7-10 实现）"""
    # 占位，后续 Task 替换
    raise NotImplementedError("render_failure_analysis 由 Task 7-10 实现")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 冒烟测试脚本能跑（用现有 report.xml）**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py \
    --junit-xml test-results/report.xml \
    --artifacts-dir test-results/artifacts \
    --output-dir test-results
```
Expected: `[INFO] 检测到 N 个失败用例...` 然后崩在 `NotImplementedError`（Task 7 会修复）

- [ ] **Step 3: Commit（骨架先入库，后续 Task 渐进实现）**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git add scripts/generate_failure_analysis.py
git commit -m "feat(failure-analysis): scaffold generate_failure_analysis.py with JUnit XML parsing"
```

---

