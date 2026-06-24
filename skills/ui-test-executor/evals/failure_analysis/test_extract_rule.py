"""测试 _extract_rule_from_docstring。

约定：测试函数 docstring 首行作为「判定规则」。
若 docstring 含 {param} 占位符，用 nodeid 末尾参数化值替换
（去掉第一个 chromium/firefox/webkit 引擎段）。
无 docstring → fallback 到函数名做人类化转换，rule_source = "fallback_funcname"。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    spec = importlib.util.spec_from_file_location(
        "_conftest_under_test",
        Path(__file__).parent.parent.parent / "assets" / "conftest_template.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_conftest_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_docstring_first_line():
    mod = _load()

    def fake_test(self, keyword):
        """搜索「{keyword}」应返回至少 1 件商品"""

    result = mod._extract_rule_from_docstring(
        fake_test,
        "tests/test_search.py::TestS::test_search[chromium-小米]",
    )
    assert result["rule"] == "搜索「小米」应返回至少 1 件商品"
    assert result["rule_source"] == "docstring"


def test_docstring_without_placeholder():
    mod = _load()

    def fake_test(self):
        """登录成功后应跳转到首页"""

    result = mod._extract_rule_from_docstring(
        fake_test,
        "tests/test_login.py::TestL::test_login",
    )
    assert result["rule"] == "登录成功后应跳转到首页"
    assert result["rule_source"] == "docstring"


def test_docstring_multiple_placeholders():
    """多个占位符按 nodeid 中括号内顺序（去掉引擎段）依次填入"""
    mod = _load()

    def fake_test(self, browser, region, keyword):
        """搜索 {keyword}（区域：{region}）"""

    result = mod._extract_rule_from_docstring(
        fake_test,
        "tests/test_search.py::TestS::test_t[chromium-华北-手机]",
    )
    assert result["rule"] == "搜索 手机（区域：华北）"


def test_no_docstring_fallback_to_funcname():
    mod = _load()

    def fake_test_valid_login_redirects_to_home(self):
        pass  # 无 docstring

    result = mod._extract_rule_from_docstring(
        fake_test_valid_login_redirects_to_home,
        "tests/test_login.py::TestL::test_test_valid_login_redirects_to_home",
    )
    # fallback：test_ 前缀去掉 + 下划线转空格
    assert "valid login redirects to home" in result["rule"].lower()
    assert result["rule_source"] == "fallback_funcname"


def test_placeholder_without_param_match():
    """docstring 含 {param} 但 nodeid 无参数化 → 占位符保留并标注"""
    mod = _load()

    def fake_test(self):
        """用户 {name} 应能登录"""

    result = mod._extract_rule_from_docstring(
        fake_test,
        "tests/test_login.py::TestL::test_login",
    )
    assert "{name}" in result["rule"]
    assert "未匹配" in result["rule_source"] or result["rule_source"] == "docstring_unmatched_param"


def test_docstring_multiline_takes_first_line():
    mod = _load()

    def fake_test(self):
        """首行判定规则。

        详细描述......
        """

    result = mod._extract_rule_from_docstring(
        fake_test,
        "tests/test_login.py::TestL::test_t",
    )
    assert result["rule"] == "首行判定规则。"
