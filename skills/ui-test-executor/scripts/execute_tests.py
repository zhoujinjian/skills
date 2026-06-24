#!/usr/bin/env python3
"""
execute_tests.py — UI 测试智能执行调度器

职责:
  1. 解析用户筛选意图（标签 / 模块 / 优先级）→ 构建 pytest -m 表达式
  2. 注入 artifact 采集配置（截图 / 录屏 / Trace / HAR / console log）
  3. 拼接 pytest 命令行（--browser / --headless / --output-dir / --retry / --parallel）
  4. 实时流式输出 pytest stdout/stderr
  5. 监控执行超时、捕获子进程异常
  6. 退出码透传（0=全过 / 1=有失败 / 2=执行异常）

设计原则:
  - 不重新实现 pytest，而是用 pytest-playwright 插件已有的能力
  - 通过 --self-contained-html / --junit-xml 输出标准报告
  - artifact 路径通过 conftest.py 中的 fixture 决定（test-results/artifacts/...）

用法:
  python3 execute_tests.py tests/ \
      --tags P0 scene_positive \
      --modules login \
      --browser chromium \
      --headless \
      --retry 2 \
      --video retain-on-failure \
      --trace retain-on-failure \
      --output-dir ./test-results

  # 查看构建的命令但不执行
  python3 execute_tests.py tests/ --tags P0 --dry-run
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# ============================================================
# 标签表达式构建
# ============================================================

# 优先级层次: P0 ⊂ P0+P1 ⊂ ... 全集
PRIORITY_LEVELS = ["P0", "P1", "P2", "P3"]


def build_marker_expression(
    tags: list[str] | None,
    modules: list[str] | None,
    priority: str | None,
    extra: str | None,
) -> str:
    """根据 tags/modules/priority 构建 pytest -m 表达式

    规则:
      - tags: AND 关系（必须同时满足）— 每个 tag 自动添加 _ 后缀映射
      - modules: OR 关系（任一模块）— 转为 module_xxx
      - priority: 包含 P0..P{N}，例如 P1 = P0 or P1
      - extra: 用户提供原始 -m 表达式，直接拼到最后（最高优先级覆盖）

    返回值示例:
        "(P0 or P1) and (module_login or module_checkout) and scene_positive"
    """
    parts: list[str] = []

    # 优先级: P0..P{N} 都要
    if priority and priority in PRIORITY_LEVELS:
        idx = PRIORITY_LEVELS.index(priority)
        prio_set = PRIORITY_LEVELS[: idx + 1]
        if len(prio_set) == 1:
            parts.append(prio_set[0])
        else:
            parts.append(f"({' or '.join(prio_set)})")

    # 模块: OR
    if modules:
        normalized = [f"module_{m.replace('-', '_').lower()}" for m in modules]
        if len(normalized) == 1:
            parts.append(normalized[0])
        else:
            parts.append(f"({' or '.join(normalized)})")

    # 标签: AND（用户列的每个 tag 都要满足）
    if tags:
        normalized_tags = [_normalize_tag(t) for t in tags]
        parts.extend(normalized_tags)

    expr = " and ".join(parts)

    # extra 用户表达式直接覆盖（用括号包裹 AND）
    if extra:
        if expr:
            expr = f"({expr}) and ({extra})"
        else:
            expr = extra

    return expr


def _normalize_tag(tag: str) -> str:
    """用户输入的 tag 标准化为 pytest marker 名

    输入示例 → 输出:
        "P0" → "P0"
        "@smoke" → "smoke"
        "scene_positive" → "scene_positive"
        "scene:positive" → "scene_positive"
        "smoke" → "smoke"
        "module:login" → "module_login"
    """
    tag = tag.strip().lstrip("@")
    tag = tag.replace(":", "_")
    return tag


# ============================================================
# Artifact 配置映射
# ============================================================

def build_pytest_args(args: argparse.Namespace) -> list[str]:
    """根据执行参数构建 pytest 命令行参数列表"""
    pytest_args: list[str] = []

    # ============ 筛选 ============
    if args.test_files:
        pytest_args.extend(args.test_files)
    else:
        pytest_args.append(args.test_dir)

    # ============ Base URL 透传（POM 项目普遍用相对路径 page.goto("/login")）============
    if getattr(args, "base_url", None):
        pytest_args.extend(["--base-url", args.base_url])

    marker_expr = build_marker_expression(
        tags=args.tags,
        modules=args.modules,
        priority=args.priority,
        extra=args.marker_expr,
    )
    if marker_expr:
        pytest_args.extend(["-m", marker_expr])

    if args.keyword:
        pytest_args.extend(["-k", args.keyword])

    # ============ 执行控制 ============
    if args.parallel and args.parallel > 1:
        pytest_args.extend(["-n", str(args.parallel)])
        if args.dist:
            pytest_args.extend(["--dist", args.dist])

    if args.retry and args.retry > 0:
        # 依赖 pytest-rerunfailures
        pytest_args.extend(["--reruns", str(args.retry)])
        pytest_args.extend(["--reruns-delay", "2"])

    if args.timeout:
        # 依赖 pytest-timeout
        pytest_args.extend(["--timeout", str(args.timeout)])

    if args.fail_fast:
        pytest_args.append("-x")
    if args.verbose:
        pytest_args.append("-v")

    # ============ 浏览器 / Playwright ============
    if args.browser:
        # 支持多次 --browser 形成矩阵
        for b in args.browser:
            pytest_args.extend(["--browser", b])

    # 浏览器 channel（连接系统真实 Chrome/Edge）
    # 默认 'chrome'，传 'none' 时跳过（用 playwright 内置 chromium）
    # 用户显式传 --browser 时也跳过（避免 chromium 浏览器 + chrome channel 冲突）
    channel = getattr(args, "browser_channel", "chrome") or "chrome"
    user_specified_browser = bool(args.browser)
    if channel and channel.lower() != "none" and not user_specified_browser:
        pytest_args.extend(["--browser-channel", channel])
        # 暴露给测试代码（视觉基线按 channel 区分等）
        os.environ["UI_TEST_CHANNEL"] = channel
    else:
        os.environ["UI_TEST_CHANNEL"] = "chromium"

    # 默认 headed（方便观察界面）；--headless 显式开启无头模式
    # pytest-playwright 0.8.0+: --headless 标志被移除，--headed 是显式 headed 开关
    # 所以默认（无 --headless）时追加 --headed；加 --headless 时不追加任何标志（新版默认就是无头）
    if not args.headless:
        pytest_args.append("--headed")

    if args.slow_mo:
        pytest_args.extend(["--slowmo", str(args.slow_mo)])

    # ============ Artifact 采集（pytest-playwright 原生支持）============
    # 设计约束：所有 artifact 均在用例失败时生成（用户明确要求）
    # 通过 --screenshot=only-on-failure / --video=retain-on-failure / --tracing=retain-on-failure
    # 三者都是 "采集但通过用例自动删除" 模式，符合约束
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = output_dir / "artifacts"
    for sub in ["screenshots", "videos", "traces", "har", "console-logs", "page-source"]:
        (artifacts_dir / sub).mkdir(parents=True, exist_ok=True)

    # pytest-playwright 原生产物（失败用例的 video.webm / trace.zip / test-failed-N.png）
    # 写到 artifacts/pytest-raw/<nodeid-slug>/，与 conftest 直写的 6 子目录分离
    pytest_args.extend(["--output", str(artifacts_dir / "pytest-raw")])

    # 暴露 artifact 根给 conftest（项目 conftest 注册了 --artifact-root 选项）
    pytest_args.extend(["--artifact-root", str(artifacts_dir)])

    # 失败截图（pytest-playwright 原生）
    if args.screenshot_on_failure:
        pytest_args.append("--screenshot=only-on-failure")

    # 录屏：retain-on-failure 模式（失败用例保留 webm，通过用例自动删除）
    video_mode = args.video or "retain-on-failure"
    pytest_args.append(f"--video={video_mode}")

    # Trace：pytest-playwright 0.8.0 的实际参数名是 --tracing（不是 --trace）
    # 之前注释错误声称被移除，导致 Trace 永远不采集；此处修正
    trace_mode = args.trace or "retain-on-failure"
    pytest_args.append(f"--tracing={trace_mode}")

    # ============ 报告输出 ============
    # JUnit XML（CI 标准）
    pytest_args.extend(["--junit-xml", str(output_dir / "report.xml")])
    pytest_args.extend(["--junit-prefix", "ui-test"])

    # HTML 报告（pytest-html）
    # 探测可用性：部分环境（如 PEP 668 保护的 system Python）未装 pytest-html
    try:
        import importlib.util
        has_pytest_html = importlib.util.find_spec("pytest_html") is not None
    except Exception:
        has_pytest_html = False

    if has_pytest_html:
        pytest_args.extend(["--html", str(output_dir / "report.html"), "--self-contained-html"])
    else:
        print("[WARN] pytest-html 未安装，跳过 HTML 报告（不影响 JUnit XML / report.json 生成）", file=sys.stderr)

    # 注: report.json 不通过 pytest 命令行产出，而是由 generate_report.py 从 JUnit XML 解析生成
    # 这样不依赖项目 conftest 注册 --report-json 自定义选项

    # ============ Allure results ============
    # --allure 开关打开时，透传 --alluredir 给 pytest（allure-pytest 插件消费）
    if getattr(args, "allure", False):
        alluredir = args.alluredir or str(output_dir / "allure-results")
        pytest_args.extend(["--alluredir", alluredir])

    # ============ 配置覆盖 ============
    if args.no_header:
        pytest_args.append("--no-header")

    return pytest_args


# ============================================================
# 执行 + 实时监控
# ============================================================

def collect_tests(pytest_args: list[str], cwd: str) -> list[str]:
    """通过 pytest --collect-only -q 收集筛选后的用例 nodeid 列表

    输出目标格式（每行一个 nodeid）:
        tests/auth/test_register.py::TestRegister::test_register_with_valid_data_redirects_to_login
        tests/product/test_search.py::TestSearchPositive::test_search_valid_keyword_shows_results[chromium-手机]

    关键: 必须追加 `-o addopts=""` 清空项目 pytest.ini 中的 addopts（特别是 -v），
    否则 pytest 8+ 会输出树状结构而不是 nodeid-per-line 格式。
    """
    python_bin = sys.executable
    # addopts="" 必须用引号包裹传给 pytest -o 选项，避免空字符串被 shell 误解
    cmd = (
        [python_bin, "-X", "utf8", "-m", "pytest"]
        + pytest_args
        + ["--collect-only", "--quiet", "--no-header", "-o", "addopts="]
    )

    # 强制 UTF-8 编码，避免 pytest 把中文参数化值转义成 手机
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=60, env=env, encoding="utf-8"
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        print(f"[WARN] collect 失败: {e}", file=sys.stderr)
        return []

    nodeids: list[str] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        # 跳过空行、错误摘要、pytest 自带说明、树状结构标签 <Dir>/<Package>/<Module>/<Class>/<Function>
        if not line:
            continue
        if line.startswith("=") or line.startswith("ERROR") or line.startswith("collected"):
            continue
        if line.startswith("<") and line.endswith(">"):
            continue
        # nodeid 必须含 :: 且不以 .py 结尾（.py 是文件路径，不是用例）
        if "::" in line and not line.endswith(".py"):
            nodeids.append(line)
    return nodeids


def _decode_unicode_escapes(s: str) -> str:
    """反转义 pytest collect 输出中的 \\uXXXX 序列

    pytest 内部对 nodeid 中的非 ASCII 字符做 ascii_ify 转义（如「手机」→ 手机），
    没有原生开关禁用。这里做反向解码，让中文参数化值原样显示。

    安全性：只匹配 \\u + 4 位 hex 的模式（pytest 的转义格式），不会误伤其他内容。
    """
    return re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda m: chr(int(m.group(1), 16)),
        s,
    )


def format_nodeid(nodeid: str) -> str:
    """nodeid → 文件名：类别：用例名

    输入: tests/product/test_search.py::TestSearchPositive::test_search_valid_keyword_shows_results[chromium-手机]
    输出: tests/product/test_search.py：TestSearchPositive：test_search_valid_keyword_shows_results[chromium-手机]

    规则:
      - 文件部分: 取 .py 之前（含 .py），保留相对路径方便定位
      - 类别部分: 第一个 :: 之后到第二个 :: 之前（即测试类名）；若无类名则填 "(no_class)"
      - 用例部分: 最后一个 :: 之后（含参数化方括号）
    """
    nodeid = _decode_unicode_escapes(nodeid)
    parts = nodeid.split("::")
    if len(parts) >= 3:
        file_part = parts[0]
        class_part = parts[1]
        test_part = "::".join(parts[2:])
    elif len(parts) == 2:
        file_part = parts[0]
        class_part = "(no_class)"
        test_part = parts[1]
    else:
        file_part = parts[0] if parts else ""
        class_part = "(unknown)"
        test_part = ""
    return f"{file_part}：{class_part}：{test_part}"


# ============================================================
# 标准化执行前打印（每次执行必输出，固化格式）
# ============================================================
# 设计目标：让"浏览器环境清单"和"待执行用例清单"在 pytest 大量输出中
# 依然醒目可辨，用户一眼能看到本次执行选了哪些浏览器、跑了哪些用例。
#
# 视觉规范：
#   - 章节标题用 === 双横线包夹（顶部+底部）
#   - 章节之间空一行，避免粘连
#   - 用例列表每行前缀 4 空格 + 序号右对齐 + . + nodeid 格式化文本
#   - 输出全部走 stderr（不污染 pytest stdout 报告）

_SECTION_WIDTH = 86


def _print_section_header(title: str, subtitle: str = "") -> None:
    """打印章节标题块：空行 + 顶部分隔线 + 标题 + 底部分隔线

    Args:
        title: 章节主标题（如 "浏览器环境清单"）
        subtitle: 副标题（如 "命中 8 个用例"），可选
    """
    print("", file=sys.stderr)
    print("=" * _SECTION_WIDTH, file=sys.stderr)
    if subtitle:
        print(f"  ▶ {title}  ·  {subtitle}", file=sys.stderr)
    else:
        print(f"  ▶ {title}", file=sys.stderr)
    print("=" * _SECTION_WIDTH, file=sys.stderr)


def _print_section_footer() -> None:
    """打印章节底部封闭分隔线 + 空行"""
    print("=" * _SECTION_WIDTH, file=sys.stderr)
    print("", file=sys.stderr)


def print_collected_tests(label: str, nodeids: list[str]) -> None:
    """按 文件名：类别：用例名 格式打印用例清单（标准化章节输出）

    Args:
        label: 阶段标签（如 "主筛选集 MAIN"、"前置阶段 PRE-RUN"）
        nodeids: pytest collect 得到的 nodeid 列表
    """
    if not nodeids:
        _print_section_header(f"待执行用例清单 — {label}", "未匹配到任何用例")
        print("  ⚠️  当前筛选条件下没有命中任何用例，请检查 --tags / --priority / --keyword 参数", file=sys.stderr)
        _print_section_footer()
        return

    _print_section_header(
        f"待执行用例清单 — {label}",
        f"命中 {len(nodeids)} 个用例",
    )
    for i, nid in enumerate(nodeids, 1):
        print(f"    {i:>3}. {format_nodeid(nid)}", file=sys.stderr)
    _print_section_footer()


def run_pytest(pytest_args: list[str], cwd: str, dry_run: bool = False, label: str = "MAIN", phase: str = "main") -> int:
    """执行 pytest 命令，实时流式输出

    label 用于在日志中区分"前置阶段"和"主测试"（如 --pre-run vs 主筛选集）
    phase 注入到子进程环境变量 PYTEST_RUN_PHASE，供 conftest 写 sidecar 时区分阶段
    """
    # 解析 python 解释器
    python_bin = sys.executable

    cmd = [python_bin, "-m", "pytest"] + pytest_args

    # 显示构建的命令
    print("=" * 80, file=sys.stderr)
    print(f"[{label}] 构建 pytest 命令:", file=sys.stderr)
    print("  " + " ".join(shlex.quote(c) for c in cmd), file=sys.stderr)
    print(f"  工作目录: {cwd}", file=sys.stderr)
    print("=" * 80, file=sys.stderr)

    if dry_run:
        print(f"[{label}] [DRY-RUN] 未实际执行", file=sys.stderr)
        return 0

    start_ts = datetime.now()
    print(f"[{label}] [START] {start_ts.isoformat()}", file=sys.stderr)

    try:
        env = os.environ.copy()
        env["PYTEST_RUN_PHASE"] = phase
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env,
        )
        # 实时透传 stdout
        for line in proc.stdout:  # type: ignore[union-attr]
            sys.stdout.write(line)
            sys.stdout.flush()

        proc.wait()
        exit_code = proc.returncode

    except KeyboardInterrupt:
        print(f"\n[{label}] [INTERRUPTED] 用户中断执行", file=sys.stderr)
        proc.terminate()
        proc.wait()
        return 130
    except FileNotFoundError:
        print(f"[{label}] [ERROR] 找不到 pytest，请确认环境: {python_bin} -m pytest --version", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[{label}] [ERROR] 执行异常: {e}", file=sys.stderr)
        return 2

    end_ts = datetime.now()
    duration = (end_ts - start_ts).total_seconds()
    print(f"\n[{label}] [DONE] 退出码={exit_code} | 耗时={duration:.1f}s | {start_ts.strftime('%H:%M:%S')} → {end_ts.strftime('%H:%M:%S')}", file=sys.stderr)
    return exit_code


# ============================================================
# CLI 入口
# ============================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="UI 测试智能执行调度器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 执行所有 P0 + 正向场景用例
  python3 execute_tests.py tests/ --priority P0 --tags scene_positive

  # 仅执行登录模块
  python3 execute_tests.py tests/ --modules login

  # 多标签 AND
  python3 execute_tests.py tests/ --tags P0 scene_positive visual

  # 跨浏览器矩阵 + 并行
  python3 execute_tests.py tests/ --browser chromium firefox --parallel 4

  # 失败重试 2 次
  python3 execute_tests.py tests/ --retry 2

  # CI 模式（headless + 失败截图 + Trace）
  python3 execute_tests.py tests/ --headless --video retain-on-failure --trace retain-on-failure

  # 预览构建的命令
  python3 execute_tests.py tests/ --priority P0 --dry-run
        """,
    )

    # ============ 范围 ============
    parser.add_argument("test_dir", nargs="?", default="tests/", help="测试目录（默认 tests/）")
    parser.add_argument("test_files", nargs="*", help="直接指定测试文件（覆盖 test_dir）")
    parser.add_argument("--tags", nargs="+", help="标签筛选（AND 关系，自动去除 @ 前缀和 : → _ 转换）")
    parser.add_argument("--modules", nargs="+", help="模块筛选（OR 关系，如 login checkout）")
    parser.add_argument("--priority", choices=PRIORITY_LEVELS, help="最低优先级（P0=只跑P0，P1=P0+P1，...）")
    parser.add_argument("--keyword", "-k", help="pytest 关键字筛选（按测试名/类名）")
    parser.add_argument("--marker-expr", "-m", dest="marker_expr", help="原始 pytest -m 表达式（覆盖自动构建）")

    # ============ 执行控制 ============
    parser.add_argument("--parallel", "-n", type=int, help="并行工作线程数（依赖 pytest-xdist）")
    parser.add_argument("--dist", choices=["load", "loadscope", "loadfile", "no"], help="xdist 分发策略（默认 loadscope）")
    parser.add_argument("--retry", type=int, default=0, help="失败重试次数（依赖 pytest-rerunfailures）")
    parser.add_argument("--timeout", type=int, default=300, help="单用例超时秒数（依赖 pytest-timeout）")
    parser.add_argument("--fail-fast", "-x", action="store_true", help="首失败立即停止")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细输出")

    # ============ 浏览器 / Playwright ============
    parser.add_argument("--browser", nargs="+", help="浏览器引擎（可多次指定形成矩阵）：chromium / firefox / webkit")
    # 默认行为: 有头模式（headed），方便观察界面交互。
    # CI 场景请显式加 --headless 切换到无头模式。
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="无头模式（CI 推荐，默认关闭以方便观察界面）",
    )
    parser.add_argument(
        "--no-headless",
        "--headed",
        dest="no_headless",
        action="store_true",
        help="有头模式（兼容参数，等价于默认行为，可不传）",
    )
    parser.add_argument(
        "--channel",
        dest="browser_channel",
        default="chrome",
        help=(
            "浏览器 channel（连接到系统的真实 Chrome/Edge）。"
            "默认 'chrome'，使用系统 Google Chrome；传 'none' 则用 playwright 内置 chromium；"
            "其他可选: 'msedge', 'chrome-beta', 'chrome-dev', 'chrome-canary'。"
            "需要目标浏览器已在系统安装。"
        ),
    )
    parser.add_argument("--slow-mo", type=int, dest="slow_mo", help="slow-mo 毫秒数（调试用）")
    parser.add_argument("--base-url", dest="base_url", help="被测站点 base URL（POM 项目用相对路径 page.goto('/login') 时必填）")

    # ============ Artifact 采集 ============
    parser.add_argument("--screenshot-on-failure", action="store_true", default=True, help="失败截图（默认开）")
    parser.add_argument("--no-screenshot", dest="screenshot_on_failure", action="store_false", help="关闭失败截图")
    parser.add_argument("--video", choices=["off", "on", "retain-on-failure"], default="retain-on-failure", help="录屏模式")
    parser.add_argument("--trace", choices=["off", "on", "retain-on-failure"], default="retain-on-failure", help="Trace 模式")

    # ============ 前置依赖 ============
    parser.add_argument(
        "--pre-run",
        nargs="+",
        default=[],
        help=(
            "前置依赖用例 — 在主筛选集之前先跑。"
            "典型场景: 主用例需要登录态，先跑注册用例创建账号。"
            "支持文件路径或 nodeid，如: --pre-run tests/auth/test_register.py "
            "或 --pre-run tests/auth/test_register.py::TestRegister::test_register_with_valid_data_redirects_to_login"
        ),
    )
    parser.add_argument(
        "--pre-run-marker",
        help="前置用例的 marker 表达式（如 'P0 and scene_positive'），与 --pre-run 二选一或组合使用",
    )

    # ============ 预览 / 输出 ============
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="只收集并打印匹配的用例清单，不实际执行。便于人工确认筛选条件是否正确",
    )
    parser.add_argument(
        "--no-confirm-print",
        action="store_true",
        help="跳过执行前的用例清单打印（默认每次执行前都打印，方便人工核对）",
    )
    parser.add_argument("--output-dir", default="./test-results", help="结果输出目录（默认 ./test-results）")
    parser.add_argument("--no-header", action="store_true", help="不显示 pytest 头部信息")
    parser.add_argument("--dry-run", action="store_true", help="只打印构建的命令，不实际执行")

    # ============ 失败报告 ============
    parser.add_argument(
        "--no-failure-analysis",
        dest="no_failure_analysis",
        action="store_true",
        help="关闭自动生成 failure_analysis.md（默认开启：有失败时自动生成）",
    )

    # ============ Allure 报告 ============
    parser.add_argument(
        "--allure",
        action="store_true",
        help="生成 Allure 报告：pytest --alluredir → allure generate → allure open（默认端口 8088）",
    )
    parser.add_argument(
        "--alluredir",
        default=None,
        help="Allure results 目录（默认 <output-dir>/allure-results）",
    )
    parser.add_argument(
        "--allure-port",
        type=int,
        default=8088,
        help="allure open 服务端口（默认 8088）",
    )
    parser.add_argument(
        "--no-allure-open",
        action="store_true",
        help="只生成 Allure 静态报告，不启动 allure open 服务",
    )

    return parser.parse_args(argv)


def _build_prerun_args(args: argparse.Namespace, output_dir: Path) -> list[str]:
    """构建前置阶段的 pytest 参数（不包含主筛选 marker）"""
    pre_args: list[str] = []

    # --pre-run 指定的文件/nodeid
    if args.pre_run:
        pre_args.extend(args.pre_run)

    # --pre-run-marker 表达式
    if args.pre_run_marker:
        pre_args.extend(["-m", args.pre_run_marker])

    # 如果两个都没给，回退到 test_dir（极少用）
    if not pre_args:
        pre_args.append(args.test_dir)

    # 共享 base-url / 浏览器 / artifact 配置
    if args.base_url:
        pre_args.extend(["--base-url", args.base_url])

    for b in (args.browser or ["chromium"]):
        pre_args.extend(["--browser", b])

    # 共享 channel（系统 Chrome）
    channel = getattr(args, "browser_channel", "chrome") or "chrome"
    if channel and channel.lower() != "none":
        pre_args.extend(["--browser-channel", channel])

    # 默认 headed（与主测试一致）
    if not args.headless:
        pre_args.append("--headed")

    if args.slow_mo:
        pre_args.extend(["--slowmo", str(args.slow_mo)])

    # 前置阶段 artifact 配置（与主测试保持一致）
    # 设计约束：所有 artifact 均在用例失败时生成（用户明确要求）
    pre_args.extend(["--output", str(output_dir / "artifacts" / "pytest-raw-pre")])
    pre_args.extend(["--artifact-root", str(output_dir / "artifacts")])
    pre_args.append("--screenshot=only-on-failure")
    pre_args.append(f"--video={args.video or 'retain-on-failure'}")
    # pytest-playwright 0.8.0 实际参数名是 --tracing（不是 --trace）
    pre_args.append(f"--tracing={args.trace or 'retain-on-failure'}")
    pre_args.extend(["--timeout", str(args.timeout)])

    # 前置阶段单独写一个 JUnit XML，避免与主报告混淆
    pre_args.extend(["--junit-xml", str(output_dir / "report-pre.xml")])
    pre_args.extend(["--junit-prefix", "ui-test-pre"])

    return pre_args


def detect_and_print_browsers() -> None:
    """执行前调用 detect_browsers.py 打印当前可用浏览器清单（标准化章节输出）

    每次执行都必打印，让用户在 pytest 输出之前就能看到：
      - 本机已安装哪些浏览器（playwright 内置 + 系统浏览器）
      - 当前默认使用哪个浏览器（--browser-channel）
      - 哪些浏览器没装（需要 playwright install）
    """
    script_dir = Path(__file__).parent
    detect_script = script_dir / "detect_browsers.py"
    if not detect_script.exists():
        _print_section_header("浏览器环境清单", "detect_browsers.py 缺失，跳过检测")
        _print_section_footer()
        return

    _print_section_header("浏览器环境清单", "execute_tests 调度前检测")
    try:
        result = subprocess.run(
            [sys.executable, str(detect_script)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = (result.stdout or "").strip()
        if output:
            for line in output.splitlines():
                print(f"  {line}", file=sys.stderr)
        else:
            err = (result.stderr or "").strip()
            if err:
                print(f"  ⚠️  detect_browsers 输出为空，stderr: {err[:200]}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("  ⚠️  detect_browsers 超时（>15s），跳过", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️  detect_browsers 执行失败: {e}", file=sys.stderr)
    _print_section_footer()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # 校验测试目录存在
    test_path = Path(args.test_dir)
    if not test_path.exists():
        print(f"[ERROR] 测试目录不存在: {test_path}", file=sys.stderr)
        return 2

    cwd = os.getcwd()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # ============ 打印当前可用浏览器清单 ============
    # 默认每次执行前都打印，让用户清楚知道本机环境状态
    detect_and_print_browsers()

    # ============ 收集 + 打印前置用例 ============
    pre_pytest_args: list[str] | None = None
    if args.pre_run or args.pre_run_marker:
        pre_pytest_args = _build_prerun_args(args, output_dir)
        pre_nodeids = collect_tests(pre_pytest_args, cwd)
        print_collected_tests("前置阶段 PRE-RUN", pre_nodeids)

    # ============ 收集 + 打印主用例 ============
    main_pytest_args = build_pytest_args(args)
    main_nodeids = collect_tests(main_pytest_args, cwd)
    print_collected_tests("主筛选集 MAIN", main_nodeids)

    # --list-only: 只收集不执行
    if args.list_only:
        print("[LIST-ONLY] 已打印用例清单，未执行", file=sys.stderr)
        return 0

    # --dry-run: 打印命令但不执行
    if args.dry_run:
        if pre_pytest_args:
            run_pytest(pre_pytest_args, cwd=cwd, dry_run=True, label="PRE-RUN")
        run_pytest(main_pytest_args, cwd=cwd, dry_run=True, label="MAIN")
        return 0

    # ============ 实际执行 ============
    if pre_pytest_args:
        pre_exit = run_pytest(pre_pytest_args, cwd=cwd, label="PRE-RUN", phase="pre-run")
        if pre_exit not in (0, 1):
            # 0=全过 / 1=有失败（仍允许继续主测试）/ 其他=异常
            print(f"[PRE-RUN] 前置阶段异常退出（exit={pre_exit}），终止后续执行", file=sys.stderr)
            return pre_exit

    main_exit = run_pytest(main_pytest_args, cwd=cwd, label="MAIN", phase="main")

    # 自动生成 failure_analysis.md（仅当有失败且未显式关闭）
    if not args.no_failure_analysis and not args.dry_run and not args.list_only:
        _maybe_generate_failure_analysis(output_dir, args, main_exit)

    # --allure：测试完成后生成静态报告 + 启动 allure open 服务
    if getattr(args, "allure", False) and not args.dry_run and not args.list_only:
        _maybe_start_allure(output_dir, args)

    return main_exit


def _maybe_start_allure(output_dir: Path, args: argparse.Namespace) -> None:
    """测试执行后的 Allure 报告生成 + 服务启动。

    流程：
        1. 检查 allure CLI 是否安装
        2. 检查 alluredir 是否有结果文件（没有则跳过）
        3. 运行 `allure generate` 生成静态报告（同步阻塞）
        4. 探测目标端口；若已被 allure 占用则直接复用，否则后台启动 `allure open`
        5. 写入 allure_url.txt，供 ui-report-generator 读取

    任何步骤失败都不影响 execute_tests.py 的退出码（仅打印 [WARN]）。
    """
    import shutil

    print("=" * 80, file=sys.stderr)
    print("[ALLURE] 开始处理 Allure 报告", file=sys.stderr)

    # 1. 检查 allure CLI
    allure_bin = shutil.which("allure")
    if not allure_bin:
        print("[ALLURE] [WARN] 未找到 allure CLI，跳过（安装：brew install allure）", file=sys.stderr)
        return

    alluredir = Path(args.alluredir) if args.alluredir else output_dir / "allure-results"
    if not alluredir.exists() or not any(alluredir.iterdir()):
        print(f"[ALLURE] [WARN] allure-results 目录为空：{alluredir}（pytest 是否成功写入？）", file=sys.stderr)
        return

    report_dir = output_dir / "allure-report"
    port = args.allure_port
    url = f"http://localhost:{port}"

    # 2. 生成静态报告（同步阻塞，通常 2-5 秒）
    print(f"[ALLURE] 生成静态报告：{alluredir} → {report_dir}", file=sys.stderr)
    gen_result = subprocess.run(
        [allure_bin, "generate", str(alluredir), "-o", str(report_dir), "--clean"],
        capture_output=True, text=True,
    )
    if gen_result.returncode != 0:
        print(f"[ALLURE] [WARN] allure generate 失败（exit={gen_result.returncode}）", file=sys.stderr)
        print(gen_result.stderr, file=sys.stderr)
        return
    print(f"[ALLURE] 静态报告已生成：{report_dir}", file=sys.stderr)

    # 3. 写 URL 文件（无论是否启动 open 服务，让 ui-report-generator 能找到）
    url_file = output_dir / "allure_url.txt"
    url_file.write_text(url, encoding="utf-8")

    if args.no_allure_open:
        print(f"[ALLURE] --no-allure-open 已指定，未启动服务（URL 文件已写入）", file=sys.stderr)
        return

    # 4. 探测端口；若已在跑则复用
    if _probe_url(url, timeout=1.0):
        print(f"[ALLURE] 端口 {port} 已有服务，复用：{url}", file=sys.stderr)
    else:
        # 后台启动 allure open（detached，父进程退出后继续运行）
        print(f"[ALLURE] 后台启动 allure open --port {port} {report_dir}", file=sys.stderr)
        try:
            log_path = output_dir / "allure_open.log"
            log_fp = open(log_path, "w", encoding="utf-8")
            subprocess.Popen(
                [allure_bin, "open", "--port", str(port), str(report_dir)],
                stdout=log_fp, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,  # detach from parent process group
            )
            # 等待 2 秒让服务起来
            import time
            for _ in range(20):
                time.sleep(0.5)
                if _probe_url(url, timeout=0.5):
                    break
        except Exception as e:
            print(f"[ALLURE] [WARN] 启动 allure open 失败：{e}", file=sys.stderr)
            return

    if _probe_url(url, timeout=1.0):
        print(f"[ALLURE] ✅ Allure 报告已就绪：{url}", file=sys.stderr)
        print(f"[ALLURE]    URL 文件：{url_file}", file=sys.stderr)
        print(f"[ALLURE]    日志：{output_dir / 'allure_open.log'}", file=sys.stderr)
    else:
        print(f"[ALLURE] [WARN] allure open 启动后端口仍不可达，但 URL 文件已写入", file=sys.stderr)
    print("=" * 80, file=sys.stderr)


def _probe_url(url: str, timeout: float = 1.0) -> bool:
    """探测 URL 是否可访问（HEAD 请求）。"""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError):
        return False


def _maybe_generate_failure_analysis(output_dir: Path, args: argparse.Namespace, main_exit: int) -> None:
    """执行后自动生成 failure_analysis.md（若 report.xml 显示有失败）

    - 找不到 generate_failure_analysis.py → 跳过（脚本缺失不应阻塞主流程）
    - 脚本本身崩溃 → 仅打印 [WARN]，不改 execute_tests.py 退出码
    """
    report_xml = output_dir / "report.xml"
    if not report_xml.exists():
        return

    # 先扫 JUnit XML 看有没有失败
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(report_xml)
        root = tree.getroot()
        failures = sum(int(ts.attrib.get("failures", "0")) for ts in root.iter("testsuite"))
        errors = sum(int(ts.attrib.get("errors", "0")) for ts in root.iter("testsuite"))
        if failures == 0 and errors == 0:
            return
    except Exception:
        # XML 解析失败 → 仍然尝试调脚本，让脚本自己报错
        pass

    script = Path(__file__).parent / "generate_failure_analysis.py"
    if not script.exists():
        return

    # 构造执行概述（写到报告头部）
    summary_parts = []
    if args.priority or args.tags or args.marker_expr:
        m_expr = build_marker_expression(args.tags, args.modules, args.priority, args.marker_expr)
        if m_expr:
            summary_parts.append(m_expr)
    if args.browser:
        summary_parts.append("+".join(args.browser))
    summary_parts.append("headless" if args.headless else "headed")
    exec_summary = " · ".join(summary_parts) if summary_parts else "(未指定)"

    cmd = [
        sys.executable,
        str(script),
        "--junit-xml", str(report_xml),
        "--artifacts-dir", str(output_dir / "artifacts"),
        "--output-dir", str(output_dir),
        "--execution-summary", exec_summary,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode not in (0,):
            print(f"[WARN] generate_failure_analysis.py 退出码 {result.returncode}", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] failure_analysis 生成失败: {e}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
