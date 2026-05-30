#!/usr/bin/env python3
"""项目骨架生成脚本 — 创建 UI 自动化测试项目目录结构"""

import os
import sys
import shutil
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
ASSETS_DIR = os.path.join(SKILL_DIR, "assets")

# 目录结构定义
DIRECTORIES = [
    "config/environments",
    "pages/components",
    "workflows",
    "tests/fixtures",
    "utils",
    "data",
    "reports",
    "traces",
    "screenshots",
]

# 需要创建的 __init__.py
INIT_DIRS = [
    "config",
    "pages",
    "pages/components",
    "workflows",
    "tests",
    "tests/fixtures",
    "utils",
]

# 需要从 assets 复制的文件
ASSET_FILES = {
    "base_page.py": "pages/base_page.py",
    "conftest.py": "tests/conftest.py",
    "pytest.ini": "pytest.ini",
    "requirements.txt": "requirements.txt",
}


def create_project(output_dir: str, overwrite: bool = False):
    """创建项目骨架"""
    print(f"创建项目: {output_dir}")
    os.makedirs(output_dir, exist_ok=True)

    # 创建目录
    for dir_path in DIRECTORIES:
        full_path = os.path.join(output_dir, dir_path)
        os.makedirs(full_path, exist_ok=True)
        print(f"  创建目录: {dir_path}/")

    # 创建 __init__.py
    for dir_path in INIT_DIRS:
        init_file = os.path.join(output_dir, dir_path, "__init__.py")
        if not os.path.exists(init_file) or overwrite:
            with open(init_file, "w") as f:
                f.write("")
            print(f"  创建文件: {dir_path}/__init__.py")

    # 复制 asset 文件
    for asset_name, target_path in ASSET_FILES.items():
        src = os.path.join(ASSETS_DIR, asset_name)
        dst = os.path.join(output_dir, target_path)
        if not os.path.exists(dst) or overwrite:
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                print(f"  复制文件: {target_path}")

    # 创建空的 data/test_data.yaml
    data_file = os.path.join(output_dir, "data", "test_data.yaml")
    if not os.path.exists(data_file) or overwrite:
        with open(data_file, "w") as f:
            f.write("# 测试数据文件\n# 由 ui-testscript-generator 生成\n")
        print("  创建文件: data/test_data.yaml")

    # 创建 config/settings.py
    settings_file = os.path.join(output_dir, "config", "settings.py")
    if not os.path.exists(settings_file) or overwrite:
        with open(settings_file, "w") as f:
            f.write('''"""全局配置"""
import os

BASE_URL = os.getenv("BASE_URL", "http://localhost:3000")
TIMEOUT = int(os.getenv("TIMEOUT", "30000"))
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
BROWSER = os.getenv("BROWSER", "chromium")
SLOW_MO = int(os.getenv("SLOW_MO", "0"))
''')
        print("  创建文件: config/settings.py")

    # 创建 config/environments/dev.yaml
    env_file = os.path.join(output_dir, "config", "environments", "dev.yaml")
    if not os.path.exists(env_file) or overwrite:
        with open(env_file, "w") as f:
            f.write("base_url: http://localhost:3000\ntimeout: 30000\n")
        print("  创建文件: config/environments/dev.yaml")

    # 创建 .gitignore
    gitignore = os.path.join(output_dir, ".gitignore")
    if not os.path.exists(gitignore) or overwrite:
        with open(gitignore, "w") as f:
            f.write("reports/\ntraces/\nscreenshots/\n__pycache__/\n*.pyc\n.env\n")
        print("  创建文件: .gitignore")

    print(f"\n项目骨架创建完成: {output_dir}")
    print("下一步:")
    print("  1. pip install -r requirements.txt")
    print("  2. playwright install")
    print("  3. 开始编写 POM 和测试脚本")


def main():
    parser = argparse.ArgumentParser(description="创建 UI 自动化测试项目骨架")
    parser.add_argument("--output", "-o", default="./ui-test-automation", help="输出目录")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的文件")
    args = parser.parse_args()

    create_project(args.output, args.overwrite)


if __name__ == "__main__":
    main()
