### Task 7: 渲染单条失败用例 MD 章节

**Files:**
- Create: `evals/failure_analysis/test_render_failure_section.py`
- Modify: `scripts/generate_failure_analysis.py`（追加 `render_failure_section` + 实现 `render_failure_analysis`）

- [ ] **Step 1: 写失败测试**

文件 `evals/failure_analysis/test_render_failure_section.py`：

```python
"""测试 render_failure_section：单条失败用例 → MD 章节。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load():
    """加载 generate_failure_analysis.py 作为模块"""
    spec = importlib.util.spec_from_file_location(
        "_gen_failure_analysis",
        Path(__file__).parent.parent.parent / "scripts" / "generate_failure_analysis.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_gen_failure_analysis"] = mod
    spec.loader.exec_module(mod)
    return mod


def _build_sidecar_native_assert():
    return {
        "nodeid": "tests/test_search.py::TestS::test_search[chromium-小米]",
        "slug_hint": "tests-test-search-py-tests-test-search-chromium-u5c0f-u7c73",
        "phase": "main",
        "duration": 1.56,
        "browser": "chromium",
        "url": "http://localhost:3000/search?q=小米",
        "title": "搜索结果",
        "failure_type": "AssertionError",
        "rule": "搜索「小米」应返回至少 1 件商品",
        "rule_source": "docstring",
        "assertion": {
            "statement": 'assert count > 0, f"搜索 \'{keyword}\' 应返回商品"',
            "file": "tests/test_search.py:55",
            "introspection": "assert 0 > 0\ncount = 0\nkeyword = '小米'",
            "message": "AssertionError: 搜索 '小米' 应返回商品，但结果数为 0",
        },
        "expect_failure": {
            "locator": "",
            "expected": "",
            "received": "",
            "action": "",
            "hint": "定位器与实际 DOM class 不匹配（推断，仅作参考）",
            "raw": "AssertionError: ...\nassert 0 > 0\ncount = 0",
        },
        "artifacts": {
            "screenshots": [
                "/tmp/screenshots/x-viewport.png",
                "/tmp/screenshots/x-fullpage.png",
            ],
            "page_source": "/tmp/x.html",
            "console_log": "/tmp/x.log",
        },
        "pytest_raw_dir": "/tmp/pytest-raw",
    }


def test_section_contains_required_sections():
    mod = _load()
    case = mod.FailureCase(
        nodeid="tests/test_search.py::TestS::test_search[chromium-小米]",
        classname="tests.test_search.TestS",
        name="test_search[chromium-小米]",
        file="tests/test_search.py",
        line="55",
        duration=1.56,
        message="AssertionError: ...",
    )
    md = mod.render_failure_section(case, sidecar=_build_sidecar_native_assert(), video_trace={})
    assert "判定规则" in md
    assert "断言原文" in md
    assert "预期 vs 实际" in md
    assert "页面元素校验" in md
    assert "失败截图" in md
    assert "失败录屏与 Trace" in md
    assert "搜索「小米」应返回至少 1 件商品" in md  # rule 出现
    assert "tests/test_search.py:55" in md  # 文件:行号


def test_section_native_assert_renders_empty_locator_row():
    """原生 assert 失败 → locator/expected/received 行显示「未提取」"""
    mod = _load()
    case = mod.FailureCase(
        nodeid="...", classname="...", name="...", duration=1, message="..."
    )
    md = mod.render_failure_section(case, sidecar=_build_sidecar_native_assert(), video_trace={})
    assert "原生 assert" in md or "未提取" in md


def test_section_playwright_expect_renders_locator():
    """playwright expect 失败 → locator/expected/received 行有值"""
    mod = _load()
    sidecar = _build_sidecar_native_assert()
    sidecar["expect_failure"] = {
        "locator": ".product-card",
        "expected": "visible",
        "received": "Timeout 30000ms",
        "action": "to_be_visible",
        "hint": "元素未在超时内出现/可见（推断，仅作参考）",
        "raw": "",
    }
    case = mod.FailureCase(nodeid="...", classname="...", name="...", duration=1, message="...")
    md = mod.render_failure_section(case, sidecar=sidecar, video_trace={})
    assert ".product-card" in md
    assert "visible" in md
    assert "Timeout" in md


def test_section_video_trace_paths_rendered():
    mod = _load()
    case = mod.FailureCase(nodeid="...", classname="...", name="...", duration=1, message="...")
    video_trace = {
        "video": "/tmp/pytest-raw/slug/video.webm",
        "trace": "/tmp/pytest-raw/slug/trace.zip",
    }
    md = mod.render_failure_section(case, sidecar=_build_sidecar_native_assert(), video_trace=video_trace)
    assert "video.webm" in md
    assert "trace.zip" in md
    assert "playwright show-trace" in md


def test_section_video_trace_missing_renders_warning():
    mod = _load()
    case = mod.FailureCase(nodeid="...", classname="...", name="...", duration=1, message="...")
    md = mod.render_failure_section(case, sidecar=_build_sidecar_native_assert(), video_trace={})
    assert "未生成" in md
```

- [ ] **Step 2: 跑测试看失败**

```bash
python3 -m pytest evals/failure_analysis/test_render_failure_section.py -v
```
Expected: FAIL with `AttributeError: ... has no attribute 'render_failure_section'`

- [ ] **Step 3: 实现 `render_failure_section` + 替换 `render_failure_analysis` 占位**

在 `scripts/generate_failure_analysis.py` 文件末尾的 `render_failure_analysis` 占位函数之前，追加 `render_failure_section`：

```python
def _is_playwright_expect_failure(sidecar: dict) -> bool:
    """判断是否 playwright expect 失败（vs 原生 assert 失败）"""
    ef = sidecar.get("expect_failure", {}) or {}
    return any([ef.get("locator"), ef.get("expected"), ef.get("received"), ef.get("action")])


def render_failure_section(case: FailureCase, sidecar: dict, video_trace: dict) -> str:
    """渲染单条失败用例的 MD 章节

    Args:
        case: 从 JUnit XML 解析出的失败用例
        sidecar: failure-context/<nodeid>.json 内容（可能为空 dict = 降级模式）
        video_trace: {"video": str, "trace": str} 路径，空 dict = 未生成

    返回 MD 字符串（不含顶部 ## 标题前的空行；末尾含 ---）
    """
    lines: list[str] = []

    # 章节标题：rule 首行 或 函数名
    title_rule = (sidecar.get("rule") or "").splitlines()[0] if sidecar.get("rule") else case.name
    lines.append(f"## ❌ {title_rule}")
    lines.append("")

    # 元信息行
    phase = sidecar.get("phase", "main")
    duration = sidecar.get("duration") or case.duration
    browser = sidecar.get("browser", "")
    failure_type = sidecar.get("failure_type", "")
    meta_parts = [f"**阶段**: {phase}", f"**耗时**: {duration:.2f}s"]
    if browser:
        meta_parts.append(f"**浏览器**: {browser}")
    if failure_type:
        meta_parts.append(f"**失败类型**: {failure_type}")
    lines.append(f"**位置**: `{case.nodeid}`")
    lines.append(" · ".join(meta_parts))
    lines.append("")

    # 判定规则
    lines.append("### 判定规则")
    rule = sidecar.get("rule", "")
    if rule:
        lines.append(f"> {rule}")
        lines.append("")
        rule_source = sidecar.get("rule_source", "")
        if rule_source == "fallback_funcname":
            lines.append("> 📌 **来源**: 函数名 fallback（无 docstring）")
        elif rule_source == "docstring_unmatched_param":
            lines.append("> 📌 **来源**: docstring（含未匹配的参数化占位符）")
        else:
            lines.append("> 📌 **来源**: 测试 docstring 首行")
        lines.append("")
    else:
        lines.append("> *(无 sidecar，rule 字段缺失，详见断言原文)*")
        lines.append("")

    # 断言原文
    lines.append("### 断言原文")
    assertion = sidecar.get("assertion", {}) or {}
    statement = assertion.get("statement", "")
    file_loc = assertion.get("file", "")
    if statement:
        lines.append("```python")
        if file_loc:
            lines.append(f"# {file_loc}")
        lines.append(statement)
        lines.append("```")
    else:
        lines.append("*(sidecar 缺失或解析失败)*")
    lines.append("")

    # 预期 vs 实际
    lines.append("### 预期 vs 实际（pytest 内省）")
    introspection = assertion.get("introspection", "")
    if introspection:
        lines.append("```")
        lines.append(introspection)
        lines.append("```")
    else:
        lines.append("*(无内省信息)*")
    lines.append("")

    # 页面元素校验
    lines.append("### 页面元素校验")
    ef = sidecar.get("expect_failure", {}) or {}
    url = sidecar.get("url", "") or case.message
    is_pw = _is_playwright_expect_failure(sidecar)
    lines.append("| 字段 | 值 |")
    lines.append("|------|---|")
    lines.append(f"| 失败 URL | `{url}` |")
    if is_pw:
        lines.append(f"| 定位器 | `{ef.get('locator', '')}` |")
        lines.append(f"| 期望 | {ef.get('expected', '')} |")
        lines.append(f"| 实际 | {ef.get('received', '')} |")
    else:
        lines.append("| 定位器 | *(原生 assert，无 playwright 错误结构)* |")
        lines.append("| 期望 | *(原生 assert，未提取)* |")
        lines.append("| 实际 | *(原生 assert，未提取)* |")
    hint = ef.get("hint", "")
    lines.append(f"| 推断原因 | {hint or '（无）'} |")
    lines.append("")
    if not is_pw:
        lines.append("> ⚠️ 本用例是**原生 assert** 失败（非 playwright expect）。")
        lines.append("> 「定位器/期望/实际」仅在 playwright expect 失败时从错误消息结构化提取。")
        lines.append("")
    raw = ef.get("raw", "")
    if raw and not is_pw:
        lines.append("**错误消息原文**：")
        lines.append("```")
        lines.append(raw[:500])
        lines.append("```")
        lines.append("")

    # 失败截图
    lines.append("### 失败截图")
    lines.append("| 类型 | 路径 |")
    lines.append("|------|------|")
    artifacts = sidecar.get("artifacts", {}) or {}
    screenshots = artifacts.get("screenshots", [])
    if isinstance(screenshots, list) and len(screenshots) >= 2:
        lines.append(f"| 视口截图 | `{screenshots[0]}` |")
        lines.append(f"| 全页截图 | `{screenshots[1]}` |")
    elif screenshots:
        for s in screenshots:
            lines.append(f"| 截图 | `{s}` |")
    else:
        lines.append("| 视口截图 | *(未采集)* |")
        lines.append("| 全页截图 | *(未采集)* |")
    # Playwright 原生失败截图（在 pytest-raw/<slug>/test-failed-N.png）
    if video_trace.get("native_screenshot"):
        lines.append(f"| Playwright 原生失败截图 | `{video_trace['native_screenshot']}` |")
    lines.append("")

    # 失败录屏与 Trace
    lines.append("### 失败录屏与 Trace")
    lines.append("| 类型 | 路径 | 复现命令 |")
    lines.append("|------|------|---------|")
    video = video_trace.get("video", "")
    trace = video_trace.get("trace", "")
    if video:
        lines.append(f"| 录屏 | `{video}` | `open {video}` |")
    else:
        lines.append("| 录屏 | *(未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off)* | - |")
    if trace:
        lines.append(f"| Trace | `{trace}` | `python3 -m playwright show-trace {trace}` |")
    else:
        lines.append("| Trace | *(未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off)* | - |")
    lines.append("")

    # 其他诊断材料
    lines.append("### 其他诊断材料")
    page_source = artifacts.get("page_source", "")
    console_log = artifacts.get("console_log", "")
    if page_source:
        lines.append(f"- 页面源码: `{page_source}`")
    if console_log:
        lines.append(f"- Console 日志: `{console_log}`")
    if url:
        lines.append(f"- 失败时 URL: `{url}`")
    lines.append("")

    lines.append("---")
    return "\n".join(lines)
```

然后替换 `render_failure_analysis` 占位实现：

```python
def render_failure_analysis(failures: list[FailureCase], artifacts_dir: Path, execution_summary: str) -> str:
    """渲染完整 MD：顶部总览 + 每条失败用例一节"""
    from datetime import datetime

    lines: list[str] = []

    # 顶部总览
    lines.append("# 失败用例故障分析报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    exec_line = execution_summary or "(未指定)"
    lines.append(f"**测试执行**: {exec_line}")
    lines.append(f"**失败统计**: {len(failures)} 个失败用例")
    lines.append("")
    lines.append("> 本报告由 `ui-test-executor` 自动生成。每条失败用例一节，含判定规则、")
    lines.append("> 断言详情、元素校验、失败截图与录屏路径。Trace 复现命令见每节末尾。")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 每条失败用例
    for i, case in enumerate(failures, 1):
        # 读 sidecar
        sidecar = _load_sidecar(artifacts_dir, case)
        # 补 video/trace
        video_trace = _resolve_video_trace(sidecar)
        # 渲染
        section = render_failure_section(case, sidecar=sidecar, video_trace=video_trace)
        lines.append(section)
        lines.append("")

    return "\n".join(lines)


def _load_sidecar(artifacts_dir: Path, case: FailureCase) -> dict:
    """从 failure-context/<safe_nodeid>.json 读 sidecar；不存在返回空 dict（降级模式）"""
    import re
    safe = re.sub(r"[\[\]\s/\\:]", "-", case.nodeid)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", safe)
    safe = safe[:120]
    sidecar_path = artifacts_dir / "failure-context" / f"{safe}.json"
    if not sidecar_path.exists():
        return {}
    try:
        import json
        return json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_video_trace(sidecar: dict) -> dict:
    """根据 sidecar.slug_hint + sidecar.pytest_raw_dir 补全 video/trace 路径"""
    result: dict[str, str] = {}
    slug = sidecar.get("slug_hint", "")
    pytest_raw_dir = sidecar.get("pytest_raw_dir", "")
    if not slug or not pytest_raw_dir:
        return result

    base = Path(pytest_raw_dir) / slug
    video = base / "video.webm"
    trace = base / "trace.zip"
    # 也找 test-failed-N.png
    if video.exists():
        result["video"] = str(video)
    if trace.exists():
        result["trace"] = str(trace)
    # 找 test-failed-N.png（N=1,2,...）
    failed_pngs = sorted(base.glob("test-failed-*.png"))
    if failed_pngs:
        result["native_screenshot"] = str(failed_pngs[0])

    return result
```

- [ ] **Step 4: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_render_failure_section.py -v
```
Expected: PASS (5 个测试)

- [ ] **Step 5: 端到端冒烟（用现有 shop-lab-ui-test 的 report.xml）**

```bash
cd /Users/zhoujinjian/ai_project/shop-lab-ui-test
python3 /Users/zhoujinjian/.claude/skills/ui-test-executor/scripts/generate_failure_analysis.py \
    --junit-xml test-results/report.xml \
    --artifacts-dir test-results/artifacts \
    --output-dir test-results \
    --execution-summary "P0 and run_smoke · chromium · headless"
cat test-results/failure_analysis.md | head -80
```
Expected: 看到 MD 报告，每条失败用例一节，含判定规则/断言原文/截图路径

- [ ] **Step 6: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git add evals/failure_analysis/test_render_failure_section.py scripts/generate_failure_analysis.py
git commit -m "feat(failure-analysis): render per-failure MD section with rule/assertion/artifacts"
```

---

