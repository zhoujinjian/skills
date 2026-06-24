#!/usr/bin/env python3
"""
open_trace.py — Playwright Trace Viewer 快捷打开

扫描 <artifacts-dir>/pytest-raw/*/trace.zip，按 query 选择一个，后台启动 Trace Viewer。

用法:
    python3 open_trace.py                          # 最新一条
    python3 open_trace.py 小米                      # nodeid 关键词
    python3 open_trace.py /abs/path/to/trace.zip   # 全路径
    python3 open_trace.py --dry-run                # 不真启动，只 print 命令

退出码:
    0  成功 spawn（或 --dry-run）
    1  discovery/matching 错误（找不到、多候选等）
    2  环境错误（playwright 未装）
    3  spawn 异常
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def _sanitize_nodeid_to_slug(nodeid: str) -> str:
    """nodeid → pytest-playwright 目录名 slug（必须与 conftest_template.py 完全一致）

    pytest-playwright 把 nodeid 里的非 ASCII 字符转成 uXXXX-uXXXX 形式：
        小米 → u5c0f-u7c73

    所以「小米」字面无法匹配目录名，需要转成同样的 slug 再做子串匹配。
    """
    text = nodeid.strip().lower()
    text = re.sub(r"[\s/\\:\[\]]+", "-", text)
    text = re.sub(r"[^a-z0-9_-]+", lambda m: "-" + "-".join(f"u{ord(c):04x}" for c in m.group()) + "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    return text


def build_candidates(artifacts_dir: Path) -> list[dict]:
    """扫描 <artifacts-dir>/pytest-raw/*/trace.zip，返回候选列表。

    Returns:
        [{"path": Path, "mtime": float, "nodeid_hint": str}, ...]
        空列表表示无候选。
    """
    raw_root = artifacts_dir / "pytest-raw"
    if not raw_root.is_dir():
        return []

    candidates: list[dict] = []
    for sub in raw_root.iterdir():
        if not sub.is_dir():
            continue
        trace = sub / "trace.zip"
        if not trace.is_file():
            continue
        candidates.append({
            "path": trace,
            "mtime": trace.stat().st_mtime,
            "nodeid_hint": sub.name,
        })
    return candidates


def match_latest(candidates: list[dict]) -> dict | None:
    """从候选列表返回 mtime 最新的；mtime 相同则按文件名字典序取最小，保证确定性。

    Returns:
        单个候选 dict，或 None（候选为空）。
    """
    if not candidates:
        return None
    return min(candidates, key=lambda c: (-c["mtime"], c["path"].name))


def match_keyword(query: str, candidates: list[dict]) -> tuple[list[dict], str | None]:
    """按 query 子串匹配候选的 nodeid_hint；支持中文 slug 容错。

    匹配规则：对每个候选，判断 query lowered 是否为 hint lowered 的子串，
    或 _sanitize_nodeid_to_slug(query) 是否为 hint 的子串（覆盖中文 → uXXXX-uXXXX 场景）。

    Returns:
        (matches, error):
        - 命中 1 个：([match], None)
        - 命中 0 个：([], "未找到含 '<query>' 的 trace\\n候选: ...")
        - 命中 ≥2 个：([all_matches], "多条 trace 匹配 '<query>'\\n候选: ...")
    """
    q_lower = query.lower()
    q_slug = _sanitize_nodeid_to_slug(query)
    matches = [
        c for c in candidates
        if q_lower in c["nodeid_hint"].lower() or q_slug in c["nodeid_hint"]
    ]

    if not matches:
        hints = "\n".join(f"  - {c['nodeid_hint']}" for c in candidates)
        return [], f"未找到含 '{query}' 的 trace。候选:\n{hints}"
    if len(matches) > 1:
        hints = "\n".join(f"  - {c['nodeid_hint']}" for c in matches)
        return matches, f"多条 trace 匹配 '{query}'，请精确指定。命中:\n{hints}"
    return matches, None


def match_path(query: str) -> tuple[Path | None, str | None]:
    """把 query 当作文件路径处理。

    Returns:
        (resolved_path, error):
        - 存在且 .zip 后缀：(.resolve(), None)
        - 不存在：(None, "路径不存在: <query>")
        - 存在但非 .zip：(None, "不是 trace 文件（需 .zip 后缀）: <query>")
    """
    p = Path(query)
    if not p.is_file():
        return None, f"路径不存在: {query}"
    if p.suffix.lower() != ".zip":
        return None, f"不是 trace 文件（需 .zip 后缀）: {query}"
    return p.resolve(), None


def format_no_candidates_error(artifacts_dir: Path) -> str:
    """候选列表为空时的诊断提示。"""
    raw = artifacts_dir / "pytest-raw"
    return (
        f"[ERROR] 未找到任何 trace.zip in {raw}/\n\n"
        "可能原因:\n"
        "  - 用例通过了（pytest-playwright --tracing=retain-on-failure 不会保留通过用例的 trace）\n"
        "  - 项目 conftest 未集成 --tracing 选项\n"
        "  - 用例在 setup 阶段失败（page 未初始化，pytest-playwright 不会生成 trace）\n\n"
        "建议:\n"
        f"  确认目录存在: ls {raw}/\n"
        "  重跑并强制 trace: execute_tests.py ... --trace on"
    )


def format_playwright_missing_error() -> str:
    """playwright 未安装时的提示。"""
    return (
        "[ERROR] playwright 未安装\n"
        "  安装: pip install playwright && python -m playwright install chromium"
    )


def _is_path_query(query: str) -> bool:
    """query 看起来像路径（包含 / 或以 .zip 结尾）时返回 True。"""
    return "/" in query or "\\" in query or query.endswith(".zip")


def _check_playwright_available(python_exe: str) -> bool:
    try:
        result = subprocess.run(
            [python_exe, "-m", "playwright", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _spawn_viewer(trace_path: Path, artifacts_dir: Path, dry_run: bool) -> int:
    """后台启动 Trace Viewer。返回退出码。"""
    log_path = artifacts_dir / "trace-viewer.log"
    cmd = [sys.executable, "-m", "playwright", "show-trace", str(trace_path)]

    if dry_run:
        print("[DRY-RUN] 会启动:")
        print(f"  {' '.join(cmd)}")
        print(f"  stdout/stderr → {log_path}")
        return 0

    if not _check_playwright_available(sys.executable):
        print(format_playwright_missing_error(), file=sys.stderr)
        return 2

    try:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_path.open("a")
        subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
        print(f"[OK] Trace Viewer 已后台启动: {trace_path}")
        print(f"     日志: {log_path}")
        return 0
    except Exception as e:
        print(f"[ERROR] 启动失败: {e}", file=sys.stderr)
        return 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Playwright Trace Viewer 快捷打开")
    parser.add_argument("query", nargs="?", default="latest",
                        help="查询：'latest'（默认）/ 关键词 / 文件路径")
    parser.add_argument("--artifacts-dir", default="./test-results/artifacts",
                        help="artifact 根目录（默认 ./test-results/artifacts）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印会启动的命令，不 spawn")
    args = parser.parse_args(argv)

    artifacts_dir = Path(args.artifacts_dir).resolve()
    query = args.query.strip()

    if _is_path_query(query):
        trace_path, err = match_path(query)
        if err:
            print(f"[ERROR] {err}", file=sys.stderr)
            return 1
        return _spawn_viewer(trace_path, artifacts_dir, args.dry_run)

    candidates = build_candidates(artifacts_dir)

    if query in ("", "latest", "最新"):
        if not candidates:
            print(format_no_candidates_error(artifacts_dir), file=sys.stderr)
            return 1
        chosen = match_latest(candidates)
        return _spawn_viewer(chosen["path"], artifacts_dir, args.dry_run)

    if not candidates:
        print(format_no_candidates_error(artifacts_dir), file=sys.stderr)
        return 1

    matches, err = match_keyword(query, candidates)
    if err:
        print(f"[ERROR] {err}", file=sys.stderr)
        return 1
    return _spawn_viewer(matches[0]["path"], artifacts_dir, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
