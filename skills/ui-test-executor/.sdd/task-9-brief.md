### Task 9: video/trace 路径补全的 slug 容错

**Files:**
- Create: `evals/failure_analysis/test_glob_video_trace.py`
- Modify: `scripts/generate_failure_analysis.py`（强化 `_resolve_video_trace` 多候选处理）

- [ ] **Step 1: 写失败测试**

文件 `evals/failure_analysis/test_glob_video_trace.py`：

```python
"""测试 _resolve_video_trace：slug 不匹配时的 glob fallback + 多候选警告。
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


def test_exact_slug_match(tmp_path):
    mod = _load()
    pytest_raw = tmp_path / "pytest-raw"
    slug = "tests-test-x-py-testx-test-a-chromium"
    (pytest_raw / slug).mkdir(parents=True)
    (pytest_raw / slug / "video.webm").write_bytes(b"fake")
    (pytest_raw / slug / "trace.zip").write_bytes(b"fake")
    sidecar = {"slug_hint": slug, "pytest_raw_dir": str(pytest_raw)}
    result = mod._resolve_video_trace(sidecar)
    assert result["video"].endswith("video.webm")
    assert result["trace"].endswith("trace.zip")


def test_no_matching_slug_returns_empty(tmp_path):
    mod = _load()
    sidecar = {"slug_hint": "does-not-exist", "pytest_raw_dir": str(tmp_path / "pytest-raw")}
    result = mod._resolve_video_trace(sidecar)
    assert result == {} or "video" not in result


def test_glob_fallback_when_slug_mismatch(tmp_path):
    """slug 完全不匹配，但 pytest-raw 下只有一个目录 → glob fallback 命中"""
    mod = _load()
    pytest_raw = tmp_path / "pytest-raw"
    slug_actual = "different-slug-actual"
    (pytest_raw / slug_actual).mkdir(parents=True)
    (pytest_raw / slug_actual / "video.webm").write_bytes(b"fake")
    sidecar = {"slug_hint": "different-slug-expected", "pytest_raw_dir": str(pytest_raw)}
    result = mod._resolve_video_trace(sidecar)
    # glob fallback：pytest-raw 下唯一目录被选中
    assert "video" in result


def test_multiple_candidates_warning(tmp_path):
    """pytest-raw 下多个目录都无法精确匹配 → 不静默选一个，返回空 + 警告字段"""
    mod = _load()
    pytest_raw = tmp_path / "pytest-raw"
    for s in ["slug-a", "slug-b"]:
        (pytest_raw / s).mkdir(parents=True)
        (pytest_raw / s / "video.webm").write_bytes(b"fake")
    sidecar = {"slug_hint": "slug-c", "pytest_raw_dir": str(pytest_raw)}
    result = mod._resolve_video_trace(sidecar)
    # 多候选时不应贸然选
    assert "video" not in result
    assert result.get("warning") or result.get("_multi_candidate")  # 警告标志
```

- [ ] **Step 2: 跑测试看失败**

```bash
python3 -m pytest evals/failure_analysis/test_glob_video_trace.py -v
```
Expected: 部分失败（Task 7 的实现只做了精确匹配）

- [ ] **Step 3: 强化 `_resolve_video_trace`**

替换 `scripts/generate_failure_analysis.py` 的 `_resolve_video_trace`：

```python
def _resolve_video_trace(sidecar: dict) -> dict:
    """根据 sidecar.slug_hint + sidecar.pytest_raw_dir 补全 video/trace 路径

    匹配策略（按优先级）:
      1. 精确匹配：<pytest_raw_dir>/<slug>/ 存在 → 直接用
      2. glob fallback：pytest-raw 下唯一目录 → 用唯一目录（容错 slug 转义差异）
      3. 多候选：pytest-raw 下多个目录 → 不选，返回 warning

    返回:
        {"video": str, "trace": str, "native_screenshot": str} 中任意子集
        多候选时追加 "_multi_candidate": True
    """
    result: dict[str, object] = {}
    slug = sidecar.get("slug_hint", "")
    pytest_raw_dir = sidecar.get("pytest_raw_dir", "")
    if not pytest_raw_dir:
        return result

    raw_root = Path(pytest_raw_dir)
    if not raw_root.exists():
        return result

    # 1. 精确匹配
    candidate_dirs: list[Path] = []
    if slug:
        exact = raw_root / slug
        if exact.exists() and exact.is_dir():
            candidate_dirs = [exact]

    # 2. fallback：列所有子目录
    if not candidate_dirs:
        all_dirs = [d for d in raw_root.iterdir() if d.is_dir()]
        if len(all_dirs) == 1:
            candidate_dirs = all_dirs
        elif len(all_dirs) > 1 and slug:
            # 尝试按 slug 的前缀匹配（容错 unicode 转义差异）
            slug_lower = slug.lower()
            prefix_matches = [d for d in all_dirs if d.name.lower().startswith(slug_lower[:30])]
            if len(prefix_matches) == 1:
                candidate_dirs = prefix_matches
            else:
                # 多候选不选
                result["_multi_candidate"] = True
                return result

    if not candidate_dirs:
        return result

    base = candidate_dirs[0]
    video = base / "video.webm"
    trace = base / "trace.zip"
    if video.exists():
        result["video"] = str(video)
    if trace.exists():
        result["trace"] = str(trace)
    failed_pngs = sorted(base.glob("test-failed-*.png"))
    if failed_pngs:
        result["native_screenshot"] = str(failed_pngs[0])

    return result
```

并在 `render_failure_section` 里，对 `_multi_candidate` 做出渲染反应。修改 video_trace 表格段（找到 `# 失败录屏与 Trace` 部分）：

把：
```python
    if video:
        lines.append(f"| 录屏 | `{video}` | `open {video}` |")
    else:
        lines.append("| 录屏 | *(未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off)* | - |")
```

改成：
```python
    if video:
        lines.append(f"| 录屏 | `{video}` | `open {video}` |")
    elif video_trace.get("_multi_candidate"):
        lines.append("| 录屏 | ⚠️ 多个候选目录匹配，请人工确认 | - |")
    else:
        lines.append("| 录屏 | *(未生成，可能此用例未失败到 call 阶段或 pytest-playwright 配置 off)* | - |")
```

trace 行同理。

- [ ] **Step 4: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_glob_video_trace.py -v
```
Expected: PASS (4 个测试)

- [ ] **Step 5: 跑全部 failure_analysis 测试确认无回归**

```bash
python3 -m pytest evals/failure_analysis/ -v
```
Expected: 所有测试 PASS

- [ ] **Step 6: Commit**

```bash
git add evals/failure_analysis/test_glob_video_trace.py scripts/generate_failure_analysis.py
git commit -m "feat(failure-analysis): resilient video/trace glob with multi-candidate warning"
```

---

## Phase 3：集成层（execute_tests.py）

