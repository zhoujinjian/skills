"""测试 _dump_failure_context：失败时把所有解析结果组装成 JSON 写到 failure-context/<nodeid>.json。
"""
from __future__ import annotations

import importlib.util
import json
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


def _build_fake_item_and_report(tmp_path, *, phase="main", browser="chromium"):
    """构造 fake pytest Item + TestReport"""
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)

    # 测试函数（带 docstring）
    def fake_test(self, keyword):
        """搜索「{keyword}」应返回至少 1 件商品"""

    item = SimpleNamespace(
        nodeid="tests/test_search.py::TestS::test_search[chromium-小米]",
        func=fake_test,
        funcargs={},
        config=SimpleNamespace(
            getoption=lambda name, default=None: {
                "--artifact-root": str(artifact_root),
            }.get(name, default)
        ),
    )

    # fake report
    longrepr = SimpleNamespace(
        reprcrash=SimpleNamespace(message="AssertionError: ...\nassert 0 > 0"),
        reprtraceback=SimpleNamespace(
            reprentries=[
                SimpleNamespace(
                    reprfileloc=SimpleNamespace(
                        source_line='assert count > 0',
                        path="tests/test_search.py",
                        lineno="55",
                    )
                )
            ]
        ),
        longreprtext="...",
    )
    report = SimpleNamespace(
        nodeid=item.nodeid,
        duration=1.56,
        longrepr=longrepr,
        sections=[],
        failed=True,
        when="call",
    )
    return item, report, artifact_root


def test_dump_writes_json(tmp_path, monkeypatch):
    mod = _load()
    item, report, artifact_root = _build_fake_item_and_report(tmp_path)

    # 把 phase 环境变量准备好
    monkeypatch.setenv("PYTEST_RUN_PHASE", "main")

    mod._dump_failure_context(item, report, browser="chromium", url="http://x/search?q=小", title="搜索")

    sidecar_dir = artifact_root / "failure-context"
    files = list(sidecar_dir.glob("*.json"))
    assert len(files) == 1, f"应只写 1 个 sidecar，实际: {files}"

    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["nodeid"] == item.nodeid
    assert data["phase"] == "main"
    assert data["browser"] == "chromium"
    assert data["url"] == "http://x/search?q=小"
    assert data["title"] == "搜索"
    assert data["duration"] == 1.56
    assert "搜索「小米」" in data["rule"]
    assert data["rule_source"] == "docstring"
    assert data["assertion"]["statement"].startswith("assert count > 0")
    assert data["assertion"]["file"] == "tests/test_search.py:55"
    assert data["expect_failure"]["hint"]  # 推断原因非空
    assert data["slug_hint"]  # slug 已生成
    assert data["pytest_raw_dir"]  # pytest-raw 路径已记录


def test_dump_phase_pre_run(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setenv("PYTEST_RUN_PHASE", "pre-run")
    item, report, artifact_root = _build_fake_item_and_report(tmp_path)
    mod._dump_failure_context(item, report, browser="chromium", url="http://x", title="t")
    sidecar = list((artifact_root / "failure-context").glob("*.json"))[0]
    assert json.loads(sidecar.read_text(encoding="utf-8"))["phase"] == "pre-run"


def test_dump_resilient_to_exception(tmp_path):
    """任何子步骤失败不应让 _dump_failure_context 抛异常（影响主测试流程）"""
    mod = _load()
    # 构造会引发异常的 fake item（inspect.getdoc 拿不到）
    item = SimpleNamespace(
        nodeid="bad/nodeid",
        func=None,  # inspect.getdoc(None) 会返回 None，不抛
        funcargs={},
        config=SimpleNamespace(
            getoption=lambda name, default=None: str(tmp_path / "artifacts") if name == "--artifact-root" else default
        ),
    )
    report = SimpleNamespace(
        nodeid="bad/nodeid",
        duration=0,
        longrepr="something went wrong",
        sections=[],
        failed=True,
        when="call",
    )
    # 不抛 = 通过
    mod._dump_failure_context(item, report, browser="chromium", url="", title="")
