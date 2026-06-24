### Task 8: 降级渲染（sidecar JSON 缺失时）

**Files:**
- Create: `evals/failure_analysis/test_fallback_render.py`
- Modify: `scripts/generate_failure_analysis.py`（`render_failure_section` 接受空 sidecar）

- [ ] **Step 1: 写失败测试**

文件 `evals/failure_analysis/test_fallback_render.py`：

```python
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
```

- [ ] **Step 2: 跑测试看失败**

```bash
python3 -m pytest evals/failure_analysis/test_fallback_render.py -v
```
Expected: 取决于 Task 7 实现，可能部分通过部分失败。若失败，调整 render_failure_section。

- [ ] **Step 3: 如有失败，修正 render_failure_section**

Task 7 的实现已经处理空 sidecar（`sidecar.get("rule", "")` 等都返回空），所以测试应该已通过。若不过，检查：
- `title_rule` 在 rule 为空时是否 fallback 到 `case.name`
- 截图/录屏路径是否在 sidecar 为空时显示"未采集"

如确实需修，修 Task 7 的 `render_failure_section` 函数对应分支。

- [ ] **Step 4: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_fallback_render.py -v
```
Expected: PASS (2 个测试)

- [ ] **Step 5: Commit**

```bash
git add evals/failure_analysis/test_fallback_render.py scripts/generate_failure_analysis.py
git commit -m "test(failure-analysis): fallback render when sidecar JSON missing"
```

---

