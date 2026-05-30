#!/usr/bin/env python3
"""
验证码识别专项测试脚本

用法:
  python3 scripts/test_captcha.py http://localhost:3000/login
  python3 scripts/test_captcha.py http://localhost:3000/login --rounds 5
  python3 scripts/test_captcha.py http://localhost:3000/login --selector "img.captcha"
  python3 scripts/test_captcha.py http://localhost:3000/login --headed   # 有头模式，观察浏览器

功能:
  1. 打开目标登录页
  2. 自动定位验证码图片区域（支持多种选择器）
  3. 截取验证码图片
  4. OCR 识别验证码文本
  5. 输出识别结果 + 保存截图，供人工对比校验
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 验证码图片候选选择器（按优先级）
CAPTCHA_SELECTORS = [
    # 常见 src 匹配
    "img[src*='captcha']",
    "img[src*='verify']",
    "img[src*='code']",
    "img[src*='CheckCode']",
    "img[src*='randcode']",
    "img[src*='authcode']",
    "img[src*='validate']",
    # 常见 id/class 匹配
    "#captcha-img",
    "#verify-img",
    "#code-img",
    "img.captcha-img",
    "img.verify-img",
    "img.code-img",
    "img.captcha",
    "img.verify",
    "img.auth-code",
    # 常见 alt 匹配
    "img[alt*='验证码']",
    "img[alt*='captcha']",
    "img[alt*='verify']",
    # SVG canvas 验证码
    "canvas.captcha",
    "canvas.verify",
    # 兜底：查找 input 旁边的 img（验证码通常紧跟在 input 附近）
    "img",
]


def find_captcha_element(page, custom_selector: str = ""):
    """在页面中定位验证码元素"""
    selectors = [custom_selector] if custom_selector else CAPTCHA_SELECTORS

    for selector in selectors:
        try:
            elements = page.locator(selector)
            count = elements.count()
            if count == 0:
                continue
            # 对于通用 img 选择器，做额外过滤
            if selector == "img":
                for i in range(min(count, 10)):
                    el = elements.nth(i)
                    src = el.get_attribute("src") or ""
                    alt = el.get_attribute("alt") or ""
                    size = el.bounding_box()
                    # 验证码图片通常是固定小尺寸
                    if size and 20 < size["width"] < 400 and 10 < size["height"] < 200:
                        if any(kw in src.lower() for kw in
                               ["captcha", "verify", "code", "check", "rand", "auth"]):
                            return el, selector, i
                    if any(kw in alt.lower() for kw in ["验证码", "captcha", "verify"]):
                        return el, selector, i
                continue
            # 优先使用第一个可见元素
            for i in range(count):
                el = elements.nth(i)
                if el.is_visible():
                    return el, selector, i
        except Exception:
            continue

    return None, None, None


def recognize_captcha(page, url, args):
    """单轮验证码识别"""
    # 导航到页面
    page.goto(url, wait_until="networkidle", timeout=args.timeout)
    page.wait_for_timeout(1000)

    # 查找验证码元素
    captcha_el, used_selector, idx = find_captcha_element(page, args.selector)

    if not captcha_el:
        print("  ❌ 未找到验证码元素")
        print("     尝试过的选择器: captcha, verify, code, CheckCode, randcode, authcode ...")
        print("     提示: 使用 --selector 参数指定自定义选择器")
        # 保存页面截图帮助调试
        debug_path = os.path.join(args.output, "debug_page.png")
        page.screenshot(path=debug_path, full_page=True)
        print(f"     页面截图已保存: {debug_path}")
        return None

    # 截取验证码图片
    captcha_path = os.path.join(args.output, f"captcha_raw.png")
    captcha_el.screenshot(path=captcha_path)

    # 获取验证码图片信息
    box = captcha_el.bounding_box()
    src = captcha_el.get_attribute("src") or ""

    print(f"  定位选择器: {used_selector}")
    print(f"  图片尺寸:   {int(box['width'])}x{int(box['height'])}")
    print(f"  图片 src:   {src[:80]}{'...' if len(src) > 80 else ''}")

    # OCR 识别
    try:
        import ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
        with open(captcha_path, "rb") as f:
            image_bytes = f.read()
        result = ocr.classification(image_bytes)
        result = result.strip()
    except ImportError:
        print("  ❌ ddddocr 未安装，请运行: pip install ddddocr")
        return None

    print(f"  识别结果:   【{result}】")
    return result


def main():
    parser = argparse.ArgumentParser(description="验证码识别专项测试")
    parser.add_argument("url", help="目标登录页 URL")
    parser.add_argument("--rounds", "-n", type=int, default=1,
                        help="识别轮数（每次刷新验证码，默认 1）")
    parser.add_argument("--selector", "-s", default="",
                        help="自定义验证码图片选择器")
    parser.add_argument("--output", "-o", default="./captcha_test_output",
                        help="截图输出目录（默认 ./captcha_test_output）")
    parser.add_argument("--headed", action="store_true",
                        help="有头模式（显示浏览器窗口）")
    parser.add_argument("--timeout", type=int, default=30000,
                        help="页面加载超时（毫秒，默认 30000）")
    args = parser.parse_args()

    # 创建输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output = os.path.join(args.output, timestamp)
    os.makedirs(args.output, exist_ok=True)

    print("=" * 60)
    print("  验证码识别专项测试")
    print("=" * 60)
    print(f"  目标 URL:  {args.url}")
    print(f"  识别轮数:  {args.rounds}")
    print(f"  输出目录:  {args.output}")
    print()

    # 启动浏览器
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright 未安装，请运行: pip install playwright && playwright install")
        sys.exit(1)

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = context.new_page()

        for i in range(args.rounds):
            print(f"--- 第 {i + 1}/{args.rounds} 轮 ---")

            # 重命名每轮截图
            round_dir = os.path.join(args.output, f"round_{i + 1}")
            os.makedirs(round_dir, exist_ok=True)

            # 临时修改输出目录
            original_output = args.output
            args.output = round_dir

            result = recognize_captcha(page, args.url, args)
            results.append(result)

            args.output = original_output

            # 保存页面完整截图（含验证码上下文）
            page_path = os.path.join(round_dir, "page_context.png")
            page.screenshot(path=page_path, full_page=True)
            print(f"  页面截图:   {page_path}")

            if i < args.rounds - 1:
                print()
                # 刷新页面获取新验证码
                page.reload(wait_until="networkidle")
                page.wait_for_timeout(1000)

        browser.close()

    # 汇总报告
    print()
    print("=" * 60)
    print("  识别汇总")
    print("=" * 60)
    success = sum(1 for r in results if r is not None)
    print(f"  总轮数:     {args.rounds}")
    print(f"  成功识别:   {success}")
    print(f"  识别失败:   {args.rounds - success}")
    print()
    print("  各轮识别结果:")
    for i, r in enumerate(results):
        status = f"【{r}】" if r else "❌ 失败"
        print(f"    轮 {i + 1}: {status}")

    print()
    print(f"  📂 所有截图保存在: {args.output}")
    print("  请打开截图与识别结果对比，验证识别准确度")


if __name__ == "__main__":
    main()
