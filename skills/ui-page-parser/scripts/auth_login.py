#!/usr/bin/env python3
"""
auth_login.py — 登录会话录制：弹出浏览器让用户手动登录，保存 Storage State

Playwright Storage State 包含 cookies + localStorage，可在后续抓取中复用，
实现免登录访问需要认证的页面。

用法：
    python3 auth_login.py <login_url> [--output auth_state.json] [--timeout 120]

完成信号：
    终端交互模式：按 Enter 键
    非交互模式（如 Claude Code）：创建信号文件
      touch /tmp/auth_login_done

后续使用：
    python3 fetch_dom.py <url> --storage-state auth_state.json
    python3 crawl_site.py <url> --storage-state auth_state.json
"""

import sys
import json
import os
import argparse
import asyncio
from pathlib import Path
from datetime import datetime, timezone

SIGNAL_FILE = "/tmp/auth_login_done"


def parse_args():
    parser = argparse.ArgumentParser(
        description="录制登录会话：弹出浏览器让用户手动登录，保存 Storage State"
    )
    parser.add_argument("login_url", help="登录页 URL")
    parser.add_argument(
        "--output", "-o", default="auth_state.json",
        help="Storage State 输出路径（默认 auth_state.json）"
    )
    parser.add_argument(
        "--timeout", type=int, default=120,
        help="最长等待时间/秒（默认 120，超时自动保存当前状态）"
    )
    return parser.parse_args()


def _cleanup_signal():
    if os.path.exists(SIGNAL_FILE):
        os.remove(SIGNAL_FILE)


async def _wait_for_signal(timeout: int):
    """同时等待 stdin Enter 或信号文件，带超时"""
    # 清理旧信号文件
    _cleanup_signal()

    deadline = asyncio.get_event_loop().time() + timeout

    async def _wait_stdin():
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, input)
            return "stdin"
        except EOFError:
            # stdin 不可用（非交互模式），无限等待让其他机制接管
            await asyncio.sleep(timeout + 10)
            return "timeout"

    async def _wait_file():
        while asyncio.get_event_loop().time() < deadline:
            if os.path.exists(SIGNAL_FILE):
                _cleanup_signal()
                return "signal_file"
            await asyncio.sleep(1)
        return "timeout"

    stdin_task = asyncio.ensure_future(_wait_stdin())
    file_task = asyncio.ensure_future(_wait_file())
    done, pending = await asyncio.wait(
        [stdin_task, file_task],
        timeout=timeout,
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()

    result = done.pop().result() if done else "timeout"

    # 确保信号文件被清理
    _cleanup_signal()
    return result


async def record_login(login_url: str, output_path: str, timeout: int):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("错误：playwright 未安装。请运行：pip install playwright && playwright install chromium", file=sys.stderr)
        sys.exit(1)

    print(f"正在启动浏览器...", file=sys.stderr)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        page = await context.new_page()

        print(f"正在打开登录页: {login_url}", file=sys.stderr)
        await page.goto(login_url, timeout=30000, wait_until="domcontentloaded")

        print("", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("  请在浏览器中完成登录操作", file=sys.stderr)
        print(f"  登录成功后，通过以下任一方式通知脚本：", file=sys.stderr)
        print(f"    - 在终端按 Enter 键", file=sys.stderr)
        print(f"    - 或运行: touch {SIGNAL_FILE}", file=sys.stderr)
        print(f"  最长等待 {timeout}s", file=sys.stderr)
        print("=" * 60, file=sys.stderr)

        # 等待用户完成登录（stdin Enter 或信号文件，带超时）
        result = await _wait_for_signal(timeout)

        if result == "timeout":
            print(f"\n等待超时（{timeout}s），自动保存当前状态...", file=sys.stderr)

        # 检查当前 URL（确认是否已离开登录页）
        current_url = page.url
        print(f"当前页面: {current_url}", file=sys.stderr)

        # 保存 Storage State
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(output))

        # 读取并统计
        with open(output, encoding="utf-8") as f:
            state = json.load(f)

        cookie_count = len(state.get("cookies", []))
        origin_count = len(state.get("origins", []))

        print("", file=sys.stderr)
        print(f"登录状态已保存: {output.absolute()}", file=sys.stderr)
        print(f"  Cookies: {cookie_count} 个", file=sys.stderr)
        print(f"  localStorage 源: {origin_count} 个", file=sys.stderr)
        print("", file=sys.stderr)
        print("后续使用方式：", file=sys.stderr)
        print(f"  python3 fetch_dom.py <URL> --storage-state {output}", file=sys.stderr)
        print(f"  python3 crawl_site.py <URL> --storage-state {output}", file=sys.stderr)

        await browser.close()


def main():
    args = parse_args()
    asyncio.run(record_login(args.login_url, args.output, args.timeout))


if __name__ == "__main__":
    main()
