"""trace_launcher.py — Playwright Trace Viewer 快捷打开

生成报告时把 trace.zip 的打开命令嵌入 HTML；
本模块提供独立的 CLI，方便用户从命令行快速打开任意 trace。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def find_trace_files(root: Path) -> list[Path]:
    """递归查找所有 trace.zip。"""
    if not root.exists():
        return []
    return sorted(root.rglob("trace.zip"))


def open_trace(trace_path: Path, browser: str | None = None) -> int:
    """打开单个 trace.zip。"""
    if not trace_path.exists():
        print(f"[ERROR] trace 文件不存在：{trace_path}", file=sys.stderr)
        return 2

    cmd = ["python3", "-m", "playwright", "show-trace", str(trace_path)]
    print(f"[trace] 启动：{' '.join(cmd)}")
    try:
        return subprocess.call(cmd)
    except FileNotFoundError:
        if shutil.which("playwright"):
            cmd = ["playwright", "show-trace", str(trace_path)]
            return subprocess.call(cmd)
        print("[ERROR] 未找到 playwright CLI。请先 pip install playwright", file=sys.stderr)
        return 127


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="trace_launcher.py", description="打开 Playwright Trace Viewer")
    p.add_argument("trace", type=Path, nargs="?", help="trace.zip 路径；不给则列出 artifacts 下所有 trace")
    p.add_argument("--artifacts-dir", type=Path, default=Path("./test-results/artifacts"),
                   help="artifacts 根目录，用于列出 trace")
    return_code = 0
    args = p.parse_args(argv)

    if args.trace:
        return open_trace(args.trace)

    traces = find_trace_files(args.artifacts_dir)
    if not traces:
        print(f"[trace] {args.artifacts_dir} 下未找到 trace.zip", file=sys.stderr)
        return 1

    print(f"[trace] 找到 {len(traces)} 个 trace：")
    for i, t in enumerate(traces, 1):
        print(f"  {i}. {t}")
    print()
    if len(traces) == 1:
        return open_trace(traces[0])
    print("请用 `python trace_launcher.py <path>` 打开指定 trace")
    return 0


if __name__ == "__main__":
    sys.exit(main())
