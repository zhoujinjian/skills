"""test_probe_url.py — _probe_url 辅助函数测试。

覆盖：
    - 不可达 URL 返回 False
    - 端口格式 URL 返回 False（连接拒绝）
    - 不抛异常（吞掉 URLError / TimeoutError / ConnectionError）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from execute_tests import _probe_url


def test_probe_unreachable_url_returns_false():
    """本地随机高端口通常没有服务，探测应返回 False 而非抛错。"""
    # 49152 是 IANA 动态端口起点；找一个几乎肯定没被占用的端口
    result = _probe_url("http://localhost:49999", timeout=0.3)
    assert result is False


def test_probe_malformed_url_returns_false():
    """畸形 URL 也不应抛异常。"""
    result = _probe_url("not-a-url", timeout=0.3)
    assert result is False


def test_probe_nonexistent_host_returns_false():
    """不存在的主机快速失败。"""
    result = _probe_url("http://nonexistent.invalid.local:8088", timeout=0.3)
    assert result is False
