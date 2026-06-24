### Task 1: 测试包骨架 + 第一个函数 `_sanitize_nodeid_to_slug`

**Files:**
- Create: `evals/failure_analysis/__init__.py`（空文件）
- Create: `evals/failure_analysis/test_sanitize_slug.py`
- Modify: `assets/conftest_template.py`（在 `_sanitize_filename` 后追加 `_sanitize_nodeid_to_slug`）

- [ ] **Step 1: 创建测试包标识**

```bash
mkdir -p /Users/zhoujinjian/.claude/skills/ui-test-executor/evals/failure_analysis/fixtures
touch /Users/zhoujinjian/.claude/skills/ui-test-executor/evals/failure_analysis/__init__.py
```

- [ ] **Step 2: 写失败测试**

文件 `evals/failure_analysis/test_sanitize_slug.py`：

```python
"""测试 _sanitize_nodeid_to_slug 与 pytest-playwright 0.8.0 的目录命名规则一致。

pytest-playwright 在 --output 目录下为每个失败用例创建子目录，
目录名由 nodeid 经 sanitize 得出。本测试覆盖关键场景：中文参数化值。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_conftest_template():
    """以模块方式加载 conftest_template.py（不执行 pytest 部分）"""
    spec = importlib.util.spec_from_file_location(
        "_conftest_under_test",
        Path(__file__).parent.parent.parent / "assets" / "conftest_template.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_conftest_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_basic_ascii_nodeid():
    mod = _load_conftest_template()
    nodeid = "tests/auth/test_login.py::TestLogin::test_valid_login[chromium]"
    slug = mod._sanitize_nodeid_to_slug(nodeid)
    # 关键断言：与 pytest-playwright 实际产物一致（参考 shop-lab-ui-test 实测目录名）
    assert slug == "tests-auth-test-login-py-testlogin-test-valid-login-chromium"


def test_chinese_param_value():
    """中文参数化值必须转成 uXXXX 形式，否则 glob 匹配失败"""
    mod = _load_conftest_template()
    nodeid = "tests/product/test_search.py::TestSearchPositive::test_search_valid_keyword_shows_results[chromium-小米]"
    slug = mod._sanitize_nodeid_to_slug(nodeid)
    # 「小」= U+5C0F, 「米」= U+7C73
    assert slug == (
        "tests-product-test-search-py-testsearchpositive-"
        "test-search-valid-keyword-shows-results-chromium-u5c0f-u7c73"
    )


def test_multiple_params():
    """多参数化值（如 [chromium-手机-北京]）依次转义"""
    mod = _load_conftest_template()
    nodeid = "tests/test_x.py::TestX::test_t[chromium-手机-北京]"
    slug = mod._sanitize_nodeid_to_slug(nodeid)
    assert slug == "tests-test-x-py-testx-test-t-chromium-u624b-u673a-u5317-u4eac"


def test_no_class_nodeid():
    """无测试类的 nodeid（函数级测试）"""
    mod = _load_conftest_template()
    nodeid = "tests/test_simple.py::test_basic"
    slug = mod._sanitize_nodeid_to_slug(nodeid)
    assert slug == "tests-test-simple-py-test-basic"


def test_collapses_consecutive_dashes():
    """连续分隔符折叠为单个 -"""
    mod = _load_conftest_template()
    nodeid = "tests//double.py::TestX::test_a"
    slug = mod._sanitize_nodeid_to_slug(nodeid)
    # 双斜杠不应产生连续 -
    assert "--" not in slug
```

- [ ] **Step 3: 跑测试看失败**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
python3 -m pytest evals/failure_analysis/test_sanitize_slug.py -v
```
Expected: FAIL with `AttributeError: module '_conftest_under_test' has no attribute '_sanitize_nodeid_to_slug'`

- [ ] **Step 4: 实现 `_sanitize_nodeid_to_slug`**

在 `assets/conftest_template.py` 文件末尾（`pytest_sessionfinish` 函数之后）追加：

```python
def _sanitize_nodeid_to_slug(nodeid: str) -> str:
    """nodeid → pytest-playwright --output 子目录名

    pytest-playwright 0.8.0 的 sanitize 规则（实测对齐）：
      1. '/' → '-'
      2. '::' → '-'（每对冒号折叠为单个 -）
      3. '[' → '-', ']' → ''（参数化方括号展开）
      4. '(' / ')' → '-'
      5. 空格 / '.'（py 文件后缀的 .）→ '-'
      6. 非 ASCII 字符 → 'uXXXX'（4 位 hex 小写，不加下划线）
      7. 连续 '-' 折叠为单个 '-'

    与 _sanitize_filename 的区别：_sanitize_filename 把非 ASCII 一律替换为 '-'，
    而 _sanitize_nodeid_to_slug 保留为 uXXXX 转义序列，便于跨进程匹配 pytest-raw/<slug>/ 目录。

    参考：实测 shop-lab-ui-test 项目 [chromium-小米] → chromium-u5c0f-u7c73
    """
    import re

    s = nodeid
    s = s.replace("::", "-")
    s = s.replace("/", "-")
    s = s.replace("[", "-")
    s = s.replace("]", "")
    s = s.replace("(", "-")
    s = s.replace(")", "-")
    s = s.replace(" ", "-")
    s = s.replace(".", "-")
    # 非 ASCII 字符 → uXXXX（不带上划线，对齐实测）
    s = re.sub(
        r"[-￿]",
        lambda m: f"u{ord(m.group(0)):04x}",
        s,
    )
    # 其他非法字符兜底转 -
    s = re.sub(r"[^A-Za-z0-9_-]", "-", s)
    # 折叠连续 -
    s = re.sub(r"-+", "-", s)
    return s
```

- [ ] **Step 5: 跑测试看通过**

```bash
python3 -m pytest evals/failure_analysis/test_sanitize_slug.py -v
```
Expected: PASS (5 个测试)

- [ ] **Step 6: Commit**

```bash
cd /Users/zhoujinjian/.claude/skills/ui-test-executor
git add evals/failure_analysis/__init__.py evals/failure_analysis/test_sanitize_slug.py assets/conftest_template.py
git commit -m "feat(failure-analysis): add _sanitize_nodeid_to_slug for pytest-playwright dir naming"
```

---

