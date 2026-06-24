"""Tests for apply_fix.py — AST rewrite 确定性修复."""
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from apply_fix import (
    apply_insufficient_wait_fix,
    apply_iframe_switch_fix,
    apply_method_typo_fix,
    apply_deprecated_api_fix,
    apply_async_wait_fix,
    suggest_method_correction,
    DEPRECATED_API_MAPPING,
    generate_patch,
    FixResult,
)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return p


# ============ insufficient_wait: timeout 数字上调 ============

def test_insufficient_wait_updates_timeout_in_safe_fill(tmp_path):
    """base_page.py 的 safe_fill(timeout=10000) → 30000."""
    src = _write(tmp_path, "base_page.py", """
        class BasePage:
            def safe_fill(self, locator, text, timeout=10000):
                locator.wait_for(state="visible", timeout=timeout)
    """)
    result = apply_insufficient_wait_fix(
        src, original_timeout_ms=10000, suggested_timeout_ms=30000,
    )
    assert result.modified is True
    assert "timeout=30000" in result.new_source
    assert "timeout=10000" not in result.new_source


def test_insufficient_wait_skips_when_timeout_already_high(tmp_path):
    """如果 timeout 已经 >= suggested，不修改."""
    src = _write(tmp_path, "base_page.py", """
        def f(locator, timeout=60000):
            locator.wait_for(timeout=timeout)
    """)
    result = apply_insufficient_wait_fix(
        src, original_timeout_ms=10000, suggested_timeout_ms=30000,
    )
    assert result.modified is False


def test_insufficient_wait_creates_bak_when_requested(tmp_path):
    src = _write(tmp_path, "base_page.py", """
        def f(locator, timeout=10000):
            locator.wait_for(timeout=timeout)
    """)
    apply_insufficient_wait_fix(
        src, original_timeout_ms=10000, suggested_timeout_ms=30000, backup=True,
    )
    assert src.with_suffix(".py.bak").exists()
    assert "timeout=10000" in src.with_suffix(".py.bak").read_text()


def test_insufficient_wait_no_bak_when_not_requested(tmp_path):
    src = _write(tmp_path, "base_page.py", """
        def f(locator, timeout=10000):
            locator.wait_for(timeout=timeout)
    """)
    apply_insufficient_wait_fix(
        src, original_timeout_ms=10000, suggested_timeout_ms=30000, backup=False,
    )
    assert not src.with_suffix(".py.bak").exists()


def test_insufficient_wait_preserves_file_when_dry_run(tmp_path):
    src = _write(tmp_path, "base_page.py", """
        def f(timeout=10000): pass
    """)
    original = src.read_text()
    apply_insufficient_wait_fix(
        src, original_timeout_ms=10000, suggested_timeout_ms=30000, dry_run=True,
    )
    assert src.read_text() == original  # 未改动
    assert not src.with_suffix(".py.bak").exists()


# ============ missing_iframe_switch: 加 frame_locator ============

def test_iframe_switch_wraps_page_locator_with_frame_locator(tmp_path):
    """page.locator(X) → page.frame_locator(...).locator(X)."""
    src = _write(tmp_path, "login_page.py", """
        from playwright.sync_api import Page

        class LoginPage:
            def __init__(self, page):
                self._captcha_input = page.locator("input[name='captcha']")
    """)
    result = apply_iframe_switch_fix(
        src,
        target_var="_captcha_input",
        iframe_css="iframe[src='/captcha']",
    )
    assert result.modified is True
    assert 'frame_locator("iframe[src=\'/captcha\']")' in result.new_source


def test_iframe_switch_skips_when_var_not_found(tmp_path):
    src = _write(tmp_path, "login_page.py", """
        class LoginPage:
            def __init__(self, page):
                self._other = page.locator("x")
    """)
    result = apply_iframe_switch_fix(
        src, target_var="_captcha_input", iframe_css="iframe[src='/captcha']",
    )
    assert result.modified is False


def test_iframe_switch_skips_already_has_frame_locator(tmp_path):
    """如果目标变量已经是 frame_locator，不重复包裹."""
    src = _write(tmp_path, "login_page.py", """
        class LoginPage:
            def __init__(self, page):
                self._captcha = page.frame_locator("iframe").locator("input")
    """)
    result = apply_iframe_switch_fix(
        src, target_var="_captcha", iframe_css="iframe",
    )
    assert result.modified is False


# ============ patch 生成 ============

def test_generate_patch_returns_unified_diff(tmp_path):
    old = "def f(timeout=10000): pass\n"
    new = "def f(timeout=30000): pass\n"
    src_path = tmp_path / "base_page.py"
    src_path.write_text(new)

    patch = generate_patch(
        source_path=src_path,
        old_source=old,
        new_source=new,
    )
    assert "---" in patch
    assert "+++" in patch
    # unified diff 是整行比对，不是子串
    assert any(line.startswith("-") and "timeout=10000" in line for line in patch.splitlines())
    assert any(line.startswith("+") and "timeout=30000" in line for line in patch.splitlines())
    assert str(src_path) in patch


def test_fix_result_dataclass_has_required_fields():
    r = FixResult(modified=True, new_source="x", backup_path=None, patch="diff")
    assert r.modified is True
    assert r.new_source == "x"
    assert r.backup_path is None
    assert r.patch == "diff"


# ============ method_typo: .clcik( → .click( ============

def test_suggest_method_correction_finds_close_match():
    """clcik → click."""
    assert suggest_method_correction("clcik") == "click"


def test_suggest_method_correction_finds_fill():
    """fille → fill."""
    assert suggest_method_correction("fille") == "fill"


def test_suggest_method_correction_returns_none_for_garbage():
    """完全无关的字符串不返回猜测."""
    assert suggest_method_correction("xyzabc123") is None


def test_suggest_method_correction_with_custom_candidates():
    """允许传入自定义候选集."""
    result = suggest_method_correction("lgin", known_methods={"login", "logout"})
    assert result == "login"


def test_method_typo_fix_replaces_typo_call(tmp_path):
    """源码中 .clcik( → .click(，所有匹配都替换."""
    src = _write(tmp_path, "login_page.py", """
        class LoginPage:
            def submit(self):
                self._username.clcik()
                self._password.clcik()
    """)
    result = apply_method_typo_fix(src, typo_name="clcik", correct_name="click")
    assert result.modified is True
    assert ".click(" in result.new_source
    assert ".clcik(" not in result.new_source
    # 两处都替换
    assert result.new_source.count(".click(") == 2


def test_method_typo_fix_only_matches_method_calls(tmp_path):
    """点号 + 标识符 + ( 才匹配；不误伤字符串字面量 / 变量名."""
    src = _write(tmp_path, "page.py", """
        def f(self):
            # clcik 作为变量名 - 不应替换
            clcik = "clcik"
            # 字符串字面量中的 .clcik( - 不应替换
            msg = "user did .clcik( on btn"
            # 真实方法调用 - 应替换
            self._btn.clcik()
    """)
    result = apply_method_typo_fix(src, typo_name="clcik", correct_name="click")
    assert result.modified is True
    assert 'clcik = "clcik"' in result.new_source  # 变量名保留
    assert '"user did .clcik( on btn"' in result.new_source  # 字符串保留
    assert "self._btn.click()" in result.new_source  # 方法调用已替换


def test_method_typo_fix_skips_when_no_match(tmp_path):
    src = _write(tmp_path, "page.py", """
        class P:
            def f(self): self._btn.click()
    """)
    result = apply_method_typo_fix(src, typo_name="clcik", correct_name="click")
    assert result.modified is False


def test_method_typo_fix_dry_run_does_not_write(tmp_path):
    src = _write(tmp_path, "page.py", """
        class P:
            def f(self): self._btn.clcik()
    """)
    original = src.read_text()
    apply_method_typo_fix(src, typo_name="clcik", correct_name="click", dry_run=True)
    assert src.read_text() == original


def test_method_typo_fix_same_name_returns_not_modified(tmp_path):
    src = _write(tmp_path, "page.py", "class P: pass\n")
    result = apply_method_typo_fix(src, typo_name="click", correct_name="click")
    assert result.modified is False


def test_method_typo_fix_creates_bak(tmp_path):
    src = _write(tmp_path, "page.py", """
        class P:
            def f(self): self._btn.clcik()
    """)
    apply_method_typo_fix(src, typo_name="clcik", correct_name="click", backup=True)
    assert src.with_suffix(".py.bak").exists()


# ============ deprecated_api: .query_selector( → .locator( ============

def test_deprecated_api_mapping_has_known_entries():
    """Playwright 常见弃用映射存在."""
    assert DEPRECATED_API_MAPPING["query_selector"] == "locator"
    assert DEPRECATED_API_MAPPING["query_selector_all"] == "locator"


def test_deprecated_api_fix_replaces_query_selector(tmp_path):
    """page.query_selector(X) → page.locator(X)."""
    src = _write(tmp_path, "page.py", """
        class P:
            def get_input(self):
                return self.page.query_selector("input[name='user']")
    """)
    result = apply_deprecated_api_fix(
        src, old_method="query_selector", new_method="locator",
    )
    assert result.modified is True
    assert ".locator(" in result.new_source
    assert ".query_selector(" not in result.new_source


def test_deprecated_api_fix_replaces_all_occurrences(tmp_path):
    """多个调用点都替换."""
    src = _write(tmp_path, "page.py", """
        class P:
            def f(self):
                a = self.page.query_selector("a")
                b = self.page.query_selector("b")
    """)
    result = apply_deprecated_api_fix(
        src, old_method="query_selector", new_method="locator",
    )
    assert result.modified is True
    assert result.new_source.count(".locator(") == 2


def test_deprecated_api_fix_skips_when_no_match(tmp_path):
    src = _write(tmp_path, "page.py", """
        class P:
            def f(self): return self.page.locator("input")
    """)
    result = apply_deprecated_api_fix(
        src, old_method="query_selector", new_method="locator",
    )
    assert result.modified is False


def test_deprecated_api_fix_dry_run_does_not_write(tmp_path):
    src = _write(tmp_path, "page.py", """
        class P:
            def f(self): return self.page.query_selector("input")
    """)
    original = src.read_text()
    apply_deprecated_api_fix(
        src, old_method="query_selector", new_method="locator", dry_run=True,
    )
    assert src.read_text() == original


def test_deprecated_api_fix_same_name_returns_not_modified(tmp_path):
    src = _write(tmp_path, "page.py", "class P: pass\n")
    result = apply_deprecated_api_fix(
        src, old_method="locator", new_method="locator",
    )
    assert result.modified is False


# ============ apply_async_wait_fix: 异步列表加载等待 ============

def test_async_wait_inserts_call_in_get_product_count(tmp_path):
    """get_product_count 方法体首行插入 self._wait_for_product_list_loaded() 调用."""
    src = _write(tmp_path, "search_result_page.py", """
        from pages.base_page import BasePage
        class SearchResultPage(BasePage):
            def get_product_count(self) -> int:
                return self._product_cards.count()
    """)
    base = _write(tmp_path, "base_page.py", """
        class BasePage:
            def __init__(self, page):
                self.page = page
    """)
    result = apply_async_wait_fix(
        source_path=src, base_page_path=base, dry_run=False,
    )
    assert result.modified is True
    # source 文件：在 return 之前插入了 wait 调用
    assert "self._wait_for_product_list_loaded()" in result.new_source
    assert result.new_source.index("self._wait_for_product_list_loaded()") < \
           result.new_source.index("self._product_cards.count()")
    # base_page：追加了 helper 方法定义
    base_new = base.read_text()
    assert "def _wait_for_product_list_loaded(self" in base_new
    assert "wait_for_load_state" in base_new


def test_async_wait_idempotent_when_already_inserted(tmp_path):
    """幂等：方法首行已是 self._wait_for_* 时跳过."""
    src = _write(tmp_path, "search_result_page.py", """
        from pages.base_page import BasePage
        class SearchResultPage(BasePage):
            def get_product_count(self) -> int:
                self._wait_for_product_list_loaded()
                return self._product_cards.count()
    """)
    base = _write(tmp_path, "base_page.py", """
        class BasePage:
            def _wait_for_product_list_loaded(self):
                pass
    """)
    result = apply_async_wait_fix(
        source_path=src, base_page_path=base, dry_run=False,
    )
    assert result.modified is False


def test_async_wait_creates_bak(tmp_path):
    """backup=True 时 source 文件写 .bak（base_page 不写 .bak）."""
    src = _write(tmp_path, "search_result_page.py", """
        from pages.base_page import BasePage
        class SearchResultPage(BasePage):
            def get_product_count(self) -> int:
                return self._product_cards.count()
    """)
    base = _write(tmp_path, "base_page.py", "class BasePage: pass\n")
    apply_async_wait_fix(
        source_path=src, base_page_path=base, backup=True,
    )
    assert src.with_suffix(".py.bak").exists()
    assert "return self._product_cards.count()" in \
           src.with_suffix(".py.bak").read_text()
