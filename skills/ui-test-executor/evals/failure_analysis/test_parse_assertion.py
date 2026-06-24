"""测试 _parse_assertion_from_longrepr。

测试策略：构造 fake report 对象，模拟 pytest 的 ReprExceptionInfo 关键属性。
不直接 mock pytest 内部，因为接口在不同 pytest 版本下会变。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def _load():
    spec = importlib.util.spec_from_file_location(
        "_conftest_under_test",
        Path(__file__).parent.parent.parent / "assets" / "conftest_template.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_conftest_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_fake_longrepr(statement: str, file_loc: str, message: str, longreprtext: str):
    """构造与 pytest ReprExceptionInfo 接口兼容的 fake 对象

    file_loc 形如 "tests/product/test_search.py:55" —— 拆成 path + lineno，
    对齐 pytest _pytest._code.code.ReprFileLocation 的真实属性布局。
    """
    # file_loc 拆分为 path 与 lineno，与 pytest ReprFileLocation 对齐
    if ":" in file_loc:
        path, _, lineno_str = file_loc.rpartition(":")
        lineno = int(lineno_str) if lineno_str.isdigit() else lineno_str
    else:
        path, lineno = file_loc, ""
    reprfileloc = SimpleNamespace(source_line=statement, path=path, lineno=lineno)
    reprcrash = SimpleNamespace(message=message)
    reprtraceback = SimpleNamespace(
        reprentries=[SimpleNamespace(reprfileloc=reprfileloc)]
    )
    return SimpleNamespace(
        reprcrash=reprcrash,
        reprtraceback=reprtraceback,
        longreprtext=longreprtext,
    )


def _build_fake_report(longrepr):
    return SimpleNamespace(longrepr=longrepr, longreprtext=getattr(longrepr, "longreprtext", ""))


def test_native_assert_extraction():
    mod = _load()
    longrepr = _build_fake_longrepr(
        statement='assert count > 0, f"搜索 \'{keyword}\' 应返回商品，但结果数为 {count}"',
        file_loc="tests/product/test_search.py:55",
        message="AssertionError: 搜索 '小米' 应返回商品，但结果数为 0\nassert 0 > 0",
        longreprtext="...",
    )
    report = _build_fake_report(longrepr)
    result = mod._parse_assertion_from_longrepr(report)
    assert result["statement"].startswith("assert count > 0")
    assert result["file"] == "tests/product/test_search.py:55"
    assert "0 > 0" in result["introspection"]
    assert "AssertionError" in result["message"]


def test_longrepr_is_string():
    """setup 阶段失败时 longrepr 可能是字符串"""
    mod = _load()
    report = SimpleNamespace(longrepr="fixture 'foo' not found", longreprtext="fixture 'foo' not found")
    result = mod._parse_assertion_from_longrepr(report)
    assert result["statement"] == ""
    assert result["file"] == ""
    assert "fixture 'foo' not found" in result["message"]


def test_longrepr_without_reprcrash():
    mod = _load()
    longrepr = SimpleNamespace(longreprtext="some error", spec=None)
    longrepr.reprcrash = None  # type: ignore[assignment]
    # longrepr 没有 reprcrash 属性的 fallback
    report = _build_fake_report(longrepr)
    # 模拟 hasattr 链路失败
    delattr(report.longrepr, "reprcrash") if hasattr(report.longrepr, "reprcrash") else None
    result = mod._parse_assertion_from_longrepr(report)
    # 至少能给出 message
    assert "message" in result


def test_empty_longrepr():
    mod = _load()
    report = SimpleNamespace(longrepr=None, longreprtext="")
    result = mod._parse_assertion_from_longrepr(report)
    assert result["statement"] == ""
    assert result["message"] == ""
