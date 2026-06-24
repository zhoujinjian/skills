"""test_allure_resolver.py — ui-report-generator Allure URL 解析测试。

覆盖：
    - 显式 --allure-url 优先级最高
    - --no-allure 短路返回 None
    - --auto-allure 优先读 allure_url.txt（含文件无效时回退）
    - --auto-allure 无文件时探测 localhost
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

import pytest

from generate_report import _resolve_allure_url, _probe_allure_url


class _Args:
    """轻量 stand-in for argparse.Namespace，便于构造测试场景。"""
    def __init__(self, allure_url=None, allure_url_file=None, auto_allure=False, no_allure=False, junit_xml=None):
        self.allure_url = allure_url
        self.allure_url_file = allure_url_file
        self.auto_allure = auto_allure
        self.no_allure = no_allure
        self.junit_xml = junit_xml


def test_no_allure_short_circuits_to_none(tmp_path):
    """--no-allure 永远返回 None，不管其他参数。"""
    args = _Args(
        no_allure=True,
        allure_url="http://localhost:8088",
        auto_allure=True,
        junit_xml=tmp_path / "report.xml",
    )
    assert _resolve_allure_url(args) is None


def test_explicit_allure_url_wins(tmp_path):
    args = _Args(
        allure_url="http://example.com:9999",
        auto_allure=True,
        junit_xml=tmp_path / "report.xml",
    )
    # 即使端口探测失败，显式 URL 也应直接返回（不做健康检查）
    assert _resolve_allure_url(args) == "http://example.com:9999"


def test_auto_allure_reads_url_file(tmp_path):
    """--auto-allure 时优先读 junit-xml 同目录的 allure_url.txt。"""
    (tmp_path / "allure_url.txt").write_text("http://localhost:8088", encoding="utf-8")
    args = _Args(auto_allure=True, junit_xml=tmp_path / "report.xml")
    # mock 探测函数：url_file 指向的 URL 必须 probe 成功才返回
    with patch("generate_report._probe_allure_url", return_value="http://localhost:8088"):
        assert _resolve_allure_url(args) == "http://localhost:8088"


def test_auto_allure_falls_through_when_url_file_unreachable(tmp_path):
    """url_file 存在但 URL 不可达时，回退到 localhost 探测。"""
    (tmp_path / "allure_url.txt").write_text("http://localhost:9999", encoding="utf-8")
    args = _Args(auto_allure=True, junit_xml=tmp_path / "report.xml")

    # _probe_allure_url 接收任意 URL 时都失败；接收默认端口时返回 8088
    def fake_probe(url_or_port=8088, timeout=1.0):
        if isinstance(url_or_port, str) and "9999" in url_or_port:
            return None
        return "http://localhost:8088"

    with patch("generate_report._probe_allure_url", side_effect=fake_probe):
        result = _resolve_allure_url(args)
    assert result == "http://localhost:8088"


def test_auto_allure_probes_localhost_when_no_file(tmp_path):
    """无 url_file 时直接探测 localhost:8088。"""
    args = _Args(auto_allure=True, junit_xml=tmp_path / "report.xml")
    with patch("generate_report._probe_allure_url", return_value="http://localhost:8088"):
        assert _resolve_allure_url(args) == "http://localhost:8088"


def test_no_auto_allure_returns_none_when_url_file_exists(tmp_path):
    """--auto-allure 没开时，即便有 allure_url.txt 也不读取。"""
    (tmp_path / "allure_url.txt").write_text("http://localhost:8088", encoding="utf-8")
    args = _Args(auto_allure=False, junit_xml=tmp_path / "report.xml")
    assert _resolve_allure_url(args) is None


def test_probe_accepts_port_int_or_url_string():
    """_probe_allure_url 既接受 int 端口也接受 str URL。"""
    # 用一个几乎肯定没在监听的端口 → 返回 None
    assert _probe_allure_url(49999, timeout=0.3) is None
    assert _probe_allure_url("http://localhost:49999", timeout=0.3) is None
