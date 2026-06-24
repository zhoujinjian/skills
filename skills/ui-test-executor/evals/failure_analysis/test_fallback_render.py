"""测试 sidecar JSON 缺失时的降级渲染。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    spec = importlib.util.spec_from_file_location(
        "_gen_failure_analysis",
        Path(__file__).parent.parent.parent / "scripts" / "generate_failure_analysis.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_gen_failure_analysis"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_empty_sidecar_still_renders():
    """sidecar = {} → 仍然能渲染一个 MD 章节，不抛"""
    mod = _load()
    case = mod.FailureCase(
        nodeid="tests/test_x.py::TestX::test_a",
        classname="tests.test_x.TestX",
        name="test_a",
        file="tests/test_x.py",
        line="10",
        duration=2.3,
        message="AssertionError: expected 5 got 3",
        traceback="traceback...",
    )
    md = mod.render_failure_section(case, sidecar={}, video_trace={})
    assert "test_a" in md  # 标题 fallback 到函数名
    assert "expected 5 got 3" in md  # message 出现
    assert "判定规则" in md  # 章节骨架仍在
    assert "未采集" in md or "未生成" in md  # 截图/录屏提示


def test_no_sidecar_section_has_warning():
    """sidecar 缺失时章节顶部应有提示（可选，断言 sidecar 来源标注）"""
    mod = _load()
    case = mod.FailureCase(nodeid="x", classname="c", name="n", duration=1, message="m")
    md = mod.render_failure_section(case, sidecar={}, video_trace={})
    assert "无 sidecar" in md or "rule 字段缺失" in md
