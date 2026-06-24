### Task 5: `_dump_failure_context` 集成（组装 + 写 JSON）

**Files:**
- Create: `evals/failure_analysis/test_dump_failure_context.py`
- Modify: `assets/conftest_template.py`（追加 `_dump_failure_context` + 修改 `_collect_failure_artifacts` 调用链）

- [ ] **Step 1: 写失败测试**

文件 `evals/failure_analysis/test_dump_failure_context.py`：

```python
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
```

- [ ] **Step 2: 跑测试看失败**

```bash
python3 -m pytest evals/failure_analysis/test_dump_failure_context.py -v
```
Expected: FAIL with `AttributeError: ... has no attribute '_dump_failure_context'`

- [ ] **Step 3: 实现 `_dump_failure_context`**

在 `assets/conftest_template.py` 的 `_parse_playwright_error` / `_infer_hint` 后追加：

```python
def _dump_failure_context(item, report, *, browser: str, url: str, title: str) -> None:
    """失败时把 rule/assertion/expect_failure/artifacts 组装成 JSON 写到 failure-context/<nodeid>.json

    设计：
      - 整个函数包 try/except，失败时只往 report.sections 加一条 [WARN]，不抛
      - 失败用例的 sidecar 文件名 = sanitize_filename(nodeid)（与 screenshots 同一规则，便于跨目录关联）
    """
    import json as _json
    import os as _os

    try:
        artifact_root = Path(
            item.config.getoption("--artifact-root", "./test-results/artifacts")
        ).resolve()
        sidecar_dir = artifact_root / "failure-context"
        sidecar_dir.mkdir(parents=True, exist_ok=True)

        safe_nodeid = _sanitize_filename(report.nodeid)
        sidecar_path = sidecar_dir / f"{safe_nodeid}.json"

        # 1. 判定规则
        test_func = getattr(item, "function", None) or getattr(item, "func", None)
        try:
            if test_func is not None:
                rule_info = _extract_rule_from_docstring(test_func, report.nodeid)
            else:
                rule_info = {"rule": "", "rule_source": "no_test_func"}
        except Exception:
            rule_info = {"rule": "", "rule_source": "fallback_funcname"}

        # 2. 断言解析
        try:
            assertion_info = _parse_assertion_from_longrepr(report)
        except Exception as e:
            assertion_info = {
                "statement": "",
                "file": "",
                "introspection": "",
                "message": f"(assertion 解析失败: {e})",
            }

        # 3. playwright 错误解析（输入：longreprtext 全文）
        longreprtext = getattr(report, "longreprtext", "") or ""
        try:
            expect_info = _parse_playwright_error(longreprtext)
        except Exception:
            expect_info = {
                "locator": "",
                "expected": "",
                "received": "",
                "action": "",
                "hint": "",
                "raw": longreprtext[:500],
            }

        # 4. phase
        phase = _os.environ.get("PYTEST_RUN_PHASE", "main")

        # 5. slug + pytest_raw_dir
        slug = _sanitize_nodeid_to_slug(report.nodeid)
        pytest_raw_dir = str(artifact_root / "pytest-raw")
        # 前置阶段产物在 pytest-raw-pre
        if phase == "pre-run":
            pytest_raw_dir = str(artifact_root / "pytest-raw-pre")

        # 6. 失败类型
        failure_type = ""
        msg = assertion_info.get("message", "")
        if msg:
            # ExceptionClass: ... 取冒号前
            failure_type = msg.split(":", 1)[0].strip()

        # 7. 已采集 artifact 路径（screenshots / page_source / console_log）
        screenshots_dir = artifact_root / "screenshots"
        page_source_dir = artifact_root / "page-source"
        console_dir = artifact_root / "console-logs"
        artifacts = {
            "screenshots": [
                str(screenshots_dir / f"{safe_nodeid}-viewport.png"),
                str(screenshots_dir / f"{safe_nodeid}-fullpage.png"),
            ],
            "page_source": str(page_source_dir / f"{safe_nodeid}.html"),
            "console_log": str(console_dir / f"{safe_nodeid}.log"),
        }

        # 8. 组装
        sidecar = {
            "nodeid": report.nodeid,
            "slug_hint": slug,
            "phase": phase,
            "duration": float(getattr(report, "duration", 0.0) or 0.0),
            "browser": browser,
            "url": url,
            "title": title,
            "failure_type": failure_type,
            "rule": rule_info.get("rule", ""),
            "rule_source": rule_info.get("rule_source", ""),
            "assertion": assertion_info,
            "expect_failure": expect_info,
            "artifacts": artifacts,
            "pytest_raw_dir": pytest_raw_dir,
            "dumped_at": datetime.now().isoformat(timespec="seconds"),
        }

        sidecar_path.write_text(
            _json.dumps(sidecar, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report.sections.append(("ui-test-executor", f"[failure-context] {sidecar_path}"))
    except Exception as e:
        try:
            report.sections.append(
                ("ui-test-executor", f"[WARN] failure-context 写入失败: {e}")
            )
        except Exception:
            pass  # 报告 sections 不可写就算了
```

- [ ] **Step 4: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_dump_failure_context.py -v
```
Expected: PASS (3 个测试)

- [ ] **Step 5: 把 `_dump_failure_context` 接到 `_collect_failure_artifacts`**

修改 `assets/conftest_template.py` 中 `_collect_failure_artifacts` 函数末尾（在 `info_line` 那段之前），追加对 `_dump_failure_context` 的调用。找到：

```python
    # 4. 当前 URL 与浏览器信息写入 report
    try:
        browser = page.context.browser.browser_type.name
    except Exception:
        browser = "unknown"

    info_line = (
        f"[failure-context] browser={browser} | url={page.url} | "
        f"duration={report.duration:.2f}s"
    )
    report.sections.append(("ui-test-executor", info_line))
```

替换为：

```python
    # 4. 当前 URL 与浏览器信息写入 report
    try:
        browser = page.context.browser.browser_type.name
    except Exception:
        browser = "unknown"

    info_line = (
        f"[failure-context] browser={browser} | url={page.url} | "
        f"duration={report.duration:.2f}s"
    )
    report.sections.append(("ui-test-executor", info_line))

    # 5. dump 失败上下文 sidecar JSON（供 generate_failure_analysis.py 渲染深度报告）
    try:
        page_title = ""
        try:
            page_title = page.title()
        except Exception:
            pass
        _dump_failure_context(item, report, browser=browser, url=page.url, title=page_title)
    except Exception as e:
        # sidecar 写入失败不能影响测试结果
        report.sections.append(
            ("ui-test-executor", f"[WARN] _dump_failure_context 调用失败: {e}")
        )
```

- [ ] **Step 6: 跑所有 failure_analysis 测试看通过**

```bash
python3 -m pytest evals/failure_analysis/ -v
```
Expected: PASS（之前 5 个文件的所有测试都过）

- [ ] **Step 7: Commit**

```bash
git add evals/failure_analysis/test_dump_failure_context.py assets/conftest_template.py
git commit -m "feat(failure-analysis): dump structured sidecar JSON on test failure"
```

---

## Phase 2：渲染层（generate_failure_analysis.py）

