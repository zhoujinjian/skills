"""test_allure_args.py — 验证 --allure CLI 参数构建。

覆盖：
    - build_pytest_args 在 --allure 开启时追加 --alluredir
    - --alluredir 自定义路径透传
    - 未开启 --allure 时不出 --alluredir
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest

from execute_tests import build_pytest_args, parse_args


def _make_args(allure: bool = False, alluredir: str | None = None, output_dir: str = "./test-results"):
    """构造一个最小可用 args namespace，绕开 parse_args 的复杂默认值。"""
    argv = ["tests/", "--output-dir", output_dir]
    if allure:
        argv.append("--allure")
    if alluredir:
        argv.extend(["--alluredir", alluredir])
    return parse_args(argv)


def test_allure_flag_adds_alluredir_to_pytest_args():
    """--allure 开启时，pytest 命令必须包含 --alluredir <default>。"""
    args = _make_args(allure=True, output_dir="./test-results")
    pytest_args = build_pytest_args(args)
    assert "--alluredir" in pytest_args
    idx = pytest_args.index("--alluredir")
    # 默认值 = <output-dir>/allure-results
    assert pytest_args[idx + 1].endswith("allure-results")
    assert "test-results" in pytest_args[idx + 1]


def test_custom_alluredir_passed_through():
    """--alluredir 自定义路径必须原样透传。"""
    args = _make_args(allure=True, alluredir="/tmp/custom-allure")
    pytest_args = build_pytest_args(args)
    idx = pytest_args.index("--alluredir")
    assert pytest_args[idx + 1] == "/tmp/custom-allure"


def test_allure_disabled_by_default():
    """未指定 --allure 时，pytest 命令不应包含 --alluredir。"""
    args = _make_args(allure=False)
    pytest_args = build_pytest_args(args)
    assert "--alluredir" not in pytest_args
