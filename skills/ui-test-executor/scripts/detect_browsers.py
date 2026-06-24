#!/usr/bin/env python3
"""
detect_browsers.py — 扫描本地系统已安装的浏览器与 Playwright 浏览器二进制

支持平台: macOS / Linux / Windows (WSL)
检测内容:
  - Playwright 内置浏览器（chromium / firefox / webkit）的安装状态与版本
  - 系统浏览器（Chrome / Chrome Canary / Edge / Firefox / Safari）
  - Playwright Python 包版本
  - 各浏览器是否支持 headless

输出:
  - STDOUT: 人类可读表格
  - --json: 标准 JSON（供 execute_tests.py 消费）

用法:
  python3 detect_browsers.py                  # 表格输出
  python3 detect_browsers.py --json           # JSON 输出
  python3 detect_browsers.py --json -o env.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


# ============================================================
# 数据模型
# ============================================================

@dataclass
class BrowserInfo:
    name: str                          # 显示名: Chromium (Playwright)
    engine: str                        # playwright_chromium / system_chrome / ...
    browser_type: str                  # playwright 内部 type: chromium / firefox / webkit
    version: str = ""                  # 版本号
    path: str = ""                     # 可执行文件路径
    source: str = "playwright"         # playwright / system
    installed: bool = False
    supports_headless: bool = True
    notes: str = ""


@dataclass
class DetectionReport:
    system: str
    platform: str
    playwright_version: str = ""
    browsers: list[BrowserInfo] = field(default_factory=list)

    def available(self) -> list[BrowserInfo]:
        return [b for b in self.browsers if b.installed]


# ============================================================
# Playwright 元数据
# ============================================================

# Playwright 内置浏览器 → (engine name, browser_type, 默认安装标志文件)
PLAYWRIGHT_BROWSERS = [
    ("chromium", "chromium"),
    ("firefox", "firefox"),
    ("webkit", "webkit"),
]


def _playwright_install_root() -> Optional[Path]:
    """获取 Playwright 浏览器二进制的安装根目录"""
    # macOS/Linux: ~/Library/Caches/ms-playwright (mac) 或 ~/.cache/ms-playwright (linux)
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    elif platform.system() == "Linux":
        return Path.home() / ".cache" / "ms-playwright"
    elif platform.system() == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ms-playwright"
    return None


def _get_playwright_version() -> str:
    """获取已安装的 Playwright Python 包版本"""
    try:
        import playwright
        return getattr(playwright, "__version__", "unknown")
    except ImportError:
        return ""
    except Exception:
        return ""


def _detect_playwright_browsers() -> list[BrowserInfo]:
    """检测 Playwright 内置浏览器（chromium / firefox / webkit）"""
    results: list[BrowserInfo] = []
    install_root = _playwright_install_root()

    for display_name, browser_type in PLAYWRIGHT_BROWSERS:
        info = BrowserInfo(
            name=f"{display_name.capitalize()} (Playwright)",
            engine=f"playwright_{browser_type}",
            browser_type=browser_type,
        )

        # 检测策略（按优先级）:
        #   1. 扫描 ms-playwright 缓存目录是否含 <browser_type>-<version>/ 子目录（最可靠）
        #   2. 解析 `playwright install --dry-run` 输出，从 "Install location" 提取路径并验证存在
        # 不依赖文本 "is already installed"，因为新版本 Playwright（1.50+）不再输出该字样
        info.installed = False

        # 策略 1: 扫描安装根目录
        if install_root and install_root.exists():
            for sub in install_root.iterdir():
                name_lower = sub.name.lower()
                # 匹配 chromium-1223 / chromium_headless_shell-1223 / firefox-1456 / webkit-2103
                # 但要排除 headless_shell（ headed 模式不可用）
                if name_lower.startswith(f"{browser_type}-") and "headless_shell" not in name_lower:
                    info.installed = True
                    info.path = str(sub)
                    # 从目录名提取版本号
                    version_part = sub.name.split("-", 1)[-1] if "-" in sub.name else ""
                    if version_part.isdigit():
                        info.version = version_part
                    break

        # 策略 2: dry-run 输出补充版本号与路径（不作为安装判定的唯一依据）
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "--dry-run", browser_type],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output_lines = (result.stdout + result.stderr).splitlines()
            for line in output_lines:
                line_lower = line.lower()
                if browser_type in line_lower and "version" not in line_lower:
                    # 形如 "Chrome for Testing 148.0.7778.96 (playwright chromium v1223)"
                    # 提取括号中的 v1223
                    if "(playwright" in line_lower:
                        import re as _re
                        m = _re.search(r"v(\d+)", line)
                        if m and not info.version:
                            info.version = f"v{m.group(1)}"
                    # 提取版本号（如 148.0.7778.96）
                    if not info.version:
                        for token in line.split():
                            if token and token[0].isdigit() and "." in token:
                                info.version = token
                                break
                    break
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        if not info.installed:
            info.notes = "未安装，运行 `python3 -m playwright install {}`".format(browser_type)

        # 二进制路径已在策略 1 中填充；若仍为空，回退到目录扫描
        if not info.path and install_root and install_root.exists():
            for sub in install_root.iterdir():
                name_lower = sub.name.lower()
                if name_lower.startswith(browser_type) and "headless_shell" not in name_lower:
                    info.path = str(sub)
                    break

        info.supports_headless = True
        results.append(info)

    return results


# ============================================================
# 系统浏览器检测（macOS / Linux / Windows）
# ============================================================

def _detect_system_browsers() -> list[BrowserInfo]:
    system = platform.system()
    if system == "Darwin":
        return _detect_system_browsers_macos()
    elif system == "Linux":
        return _detect_system_browsers_linux()
    elif system == "Windows":
        return _detect_system_browsers_windows()
    return []


def _detect_system_browsers_macos() -> list[BrowserInfo]:
    """macOS 系统浏览器检测"""
    candidates = [
        ("Google Chrome", "Google Chrome.app/Contents/MacOS/Google Chrome", "chromium"),
        ("Google Chrome Canary", "Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary", "chromium"),
        ("Microsoft Edge", "Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "chromium"),
        ("Firefox", "Firefox.app/Contents/MacOS/firefox", "firefox"),
        ("Safari", "Safari.app/Contents/MacOS/Safari", "webkit"),
        ("Chromium", "Chromium.app/Contents/MacOS/Chromium", "chromium"),
    ]
    results: list[BrowserInfo] = []
    apps_dir = Path("/Applications")

    for display_name, relative_path, browser_type in candidates:
        full_path = apps_dir / relative_path
        info = BrowserInfo(
            name=f"{display_name} (System)",
            engine=f"system_{browser_type}",
            browser_type=browser_type,
        )
        if full_path.exists():
            info.installed = True
            info.path = str(full_path)
            info.version = _get_app_version_macos(full_path)
            info.supports_headless = browser_type != "webkit" or display_name != "Safari"
        else:
            info.installed = False
            info.notes = "未在 /Applications 找到"
        results.append(info)

    return results


def _detect_system_browsers_linux() -> list[BrowserInfo]:
    """Linux 系统浏览器检测（通过 which/whereis）"""
    candidates = [
        ("Google Chrome", ["google-chrome", "google-chrome-stable"], "chromium"),
        ("Chromium", ["chromium", "chromium-browser"], "chromium"),
        ("Microsoft Edge", ["microsoft-edge", "microsoft-edge-stable"], "chromium"),
        ("Firefox", ["firefox"], "firefox"),
    ]
    results: list[BrowserInfo] = []
    for display_name, cmds, browser_type in candidates:
        info = BrowserInfo(
            name=f"{display_name} (System)",
            engine=f"system_{browser_type}",
            browser_type=browser_type,
        )
        path = None
        for cmd in cmds:
            path = shutil.which(cmd)
            if path:
                break
        if path:
            info.installed = True
            info.path = path
            info.version = _get_binary_version(path)
            info.supports_headless = True
        else:
            info.installed = False
            info.notes = "未在 PATH 中找到"
        results.append(info)
    return results


def _detect_system_browsers_windows() -> list[BrowserInfo]:
    """Windows 系统浏览器检测"""
    candidates = [
        ("Google Chrome", r"Google\Chrome\Application\chrome.exe", "chromium"),
        ("Microsoft Edge", r"Microsoft\Edge\Application\msedge.exe", "chromium"),
        ("Firefox", r"Mozilla Firefox\firefox.exe", "firefox"),
    ]
    results: list[BrowserInfo] = []
    for display_name, relative_path, browser_type in candidates:
        info = BrowserInfo(
            name=f"{display_name} (System)",
            engine=f"system_{browser_type}",
            browser_type=browser_type,
        )
        for env_var in ["PROGRAMFILES", "PROGRAMFILES(X86)"]:
            base = os.environ.get(env_var)
            if not base:
                continue
            full_path = Path(base) / relative_path
            if full_path.exists():
                info.installed = True
                info.path = str(full_path)
                info.version = _get_binary_version(str(full_path))
                info.supports_headless = True
                break
        if not info.installed:
            info.notes = "未在 Program Files 找到"
        results.append(info)
    return results


def _get_app_version_macos(app_path: Path) -> str:
    """从 macOS 应用 Info.plist 读取版本"""
    try:
        result = subprocess.run(
            ["/usr/bin/defaults", "read", str(app_path.parent.parent / "Contents" / "Info"), "CFBundleShortVersionString"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        # 备选：直接调用 --version
        result = subprocess.run(
            [str(app_path), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return (result.stdout or "").strip()
    except Exception:
        return ""


def _get_binary_version(binary_path: str) -> str:
    """通过 --version 获取版本号"""
    try:
        result = subprocess.run(
            [binary_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        out = (result.stdout or result.stderr).strip()
        # 提取版本号（最后一段数字）
        for token in reversed(out.split()):
            if token and token[0].isdigit():
                return token
        return out
    except Exception:
        return ""


# ============================================================
# 报告渲染
# ============================================================

def render_table(report: DetectionReport) -> str:
    lines = []
    lines.append("=" * 90)
    lines.append("  浏览器环境检测报告")
    lines.append("=" * 90)
    lines.append(f"  系统: {report.system} ({report.platform})")
    lines.append(f"  Playwright 版本: {report.playwright_version or '<未安装>'}")
    lines.append("")

    # 可用浏览器
    available = report.available()
    if not available:
        lines.append("  ⚠️  未检测到任何可用浏览器！")
        lines.append("     请安装 Playwright 浏览器: python3 -m playwright install chromium")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"  ✅ 检测到 {len(available)} 个可用浏览器:")
    lines.append("")
    lines.append(f"  {'#':<3} {'名称':<30} {'引擎':<22} {'版本':<14} {'Headless':<10}")
    lines.append(f"  {'-'*3} {'-'*30} {'-'*22} {'-'*14} {'-'*10}")
    for i, b in enumerate(available, 1):
        headless = "✓" if b.supports_headless else "✗"
        lines.append(
            f"  {i:<3} {b.name:<30} {b.engine:<22} {(b.version or '-'):<14} {headless:<10}"
        )
    lines.append("")

    # 未安装的浏览器（简略）
    not_installed = [b for b in report.browsers if not b.installed]
    if not_installed:
        lines.append(f"  未安装的浏览器（{len(not_installed)} 个，跳过）:")
        for b in not_installed[:5]:
            lines.append(f"    - {b.name}: {b.notes}")
        lines.append("")

    lines.append("=" * 90)
    return "\n".join(lines)


def to_json(report: DetectionReport) -> str:
    return json.dumps(
        {
            "system": report.system,
            "platform": report.platform,
            "playwright_version": report.playwright_version,
            "available_count": len(report.available()),
            "browsers": [asdict(b) for b in report.browsers],
        },
        ensure_ascii=False,
        indent=2,
    )


# ============================================================
# 主流程
# ============================================================

def run_detection() -> DetectionReport:
    report = DetectionReport(
        system=platform.system(),
        platform=platform.platform(),
        playwright_version=_get_playwright_version(),
    )
    report.browsers.extend(_detect_playwright_browsers())
    report.browsers.extend(_detect_system_browsers())
    return report


def main():
    parser = argparse.ArgumentParser(
        description="检测本地系统已安装的浏览器，供 ui-test-executor 选择执行环境"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("-o", "--output", help="输出到文件（默认 STDOUT）")
    args = parser.parse_args()

    report = run_detection()

    if args.json:
        content = to_json(report)
    else:
        content = render_table(report)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(content, encoding="utf-8")
        print(f"[INFO] 已写入 {args.output}", file=sys.stderr)
    else:
        print(content)

    # 退出码: 0 = 至少 1 个可用浏览器，1 = 无可用
    sys.exit(0 if report.available() else 1)


if __name__ == "__main__":
    main()
