"""apply_fix.py — AST rewrite 确定性修复

仅对 pages/**/*.py（page 对象层）做修改，不动 tests/**.**。

修复策略:
    insufficient_wait      timeout=N → timeout=max(N*3, 30000)
    missing_iframe_switch  page.locator(X) → page.frame_locator(...).locator(X)
    method_typo            .clcik( → .click(（基于 AttributeError 智能提示）
    deprecated_api         .query_selector( → .locator(（Playwright 已弃用 API）
    async_wait             在 list-getter 方法首行插入 _wait_for_product_list_loaded()
                           + base_page.py 注入 helper（修复异步加载导致 count=0 误报）

安全保证:
    - 默认 backup=True，原文件写 .bak
    - dry_run=True 时不写文件、不写 .bak
    - AST 级修改，保留代码格式（不重新格式化整个文件）
"""
from __future__ import annotations

import ast
import difflib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FixResult:
    """修复结果。"""
    modified: bool
    new_source: str
    backup_path: Path | None = None
    patch: str = ""


# ============ insufficient_wait 修复 ============

def apply_insufficient_wait_fix(
    source_path: Path,
    original_timeout_ms: int,
    suggested_timeout_ms: int,
    backup: bool = True,
    dry_run: bool = False,
) -> FixResult:
    """把 source_path 里所有 timeout=original 的字面量改为 suggested。

    策略：源码级正则替换（不改 AST 节点），保留原始格式。
    匹配 timeout=<原值> 的字面量（关键字参数、位置参数、独立赋值都覆盖）。
    """
    old_source = source_path.read_text(encoding="utf-8")

    # 已经 >= suggested，不修改
    if original_timeout_ms >= suggested_timeout_ms:
        return FixResult(modified=False, new_source=old_source)

    # 字面量替换：`timeout=10000` → `timeout=30000`
    old_pattern = f"timeout={original_timeout_ms}"
    new_pattern = f"timeout={suggested_timeout_ms}"
    if old_pattern not in old_source:
        return FixResult(modified=False, new_source=old_source)

    new_source = old_source.replace(old_pattern, new_pattern)
    patch = generate_patch(source_path, old_source, new_source)

    backup_path: Path | None = None
    if not dry_run:
        if backup:
            backup_path = source_path.with_suffix(source_path.suffix + ".bak")
            shutil.copy2(source_path, backup_path)
        source_path.write_text(new_source, encoding="utf-8")

    return FixResult(modified=True, new_source=new_source, backup_path=backup_path, patch=patch)


# ============ missing_iframe_switch 修复 ============

def apply_iframe_switch_fix(
    source_path: Path,
    target_var: str,
    iframe_css: str,
    backup: bool = True,
    dry_run: bool = False,
) -> FixResult:
    """把 self.<target_var> = page.locator(X) 改为
    self.<target_var> = page.frame_locator("<iframe_css>").locator(X)。

    使用 AST 解析定位，源码级替换（保留 X 的原始字符串）。
    """
    old_source = source_path.read_text(encoding="utf-8")

    # 已经包了 frame_locator → 不改
    if "frame_locator(" in old_source:
        return FixResult(modified=False, new_source=old_source)

    # AST 找到目标 assignment
    tree = ast.parse(old_source)
    target_assignment: ast.AnnAssign | ast.Assign | None = None
    target_locator_arg: ast.expr | None = None

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        var_name = _get_assign_target_name(node)
        if var_name != target_var:
            continue
        # RHS 应该是 page.locator(X) 形式
        rhs = node.value
        if isinstance(rhs, ast.Call) and _is_page_locator_call(rhs):
            target_assignment = node
            target_locator_arg = rhs.args[0] if rhs.args else None
            break

    if target_assignment is None or target_locator_arg is None:
        return FixResult(modified=False, new_source=old_source)

    # 提取原始 locator 参数字符串（保留引号）
    lines = old_source.splitlines(keepends=True)
    # 找到 target_assignment 所在行的 `page.locator(X)` 子串
    # 用源码级正则替换最稳妥（保留 X 原始格式）
    import re
    pattern = re.compile(
        rf'(self\.{re.escape(target_var)}\s*(?::\s*[^=]+)?\s*=\s*)page\.locator\('
    )
    new_source, n = pattern.subn(
        lambda m: f'{m.group(1)}page.frame_locator("{iframe_css}").locator(',
        old_source,
    )
    if n == 0:
        return FixResult(modified=False, new_source=old_source)

    patch = generate_patch(source_path, old_source, new_source)

    backup_path: Path | None = None
    if not dry_run:
        if backup:
            backup_path = source_path.with_suffix(source_path.suffix + ".bak")
            shutil.copy2(source_path, backup_path)
        source_path.write_text(new_source, encoding="utf-8")

    return FixResult(modified=True, new_source=new_source, backup_path=backup_path, patch=patch)


def _get_assign_target_name(node: ast.Assign | ast.AnnAssign) -> str | None:
    """提取 self._xxx = ... 的目标变量名。"""
    target = node.targets[0] if isinstance(node, ast.Assign) else node.target
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
        if target.value.id == "self":
            return target.attr
    return None


def _is_page_locator_call(call: ast.Call) -> bool:
    """判定 call 是否为 page.locator(...) 形式。"""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "locator":
        # page.locator(...)
        if isinstance(func.value, ast.Name) and func.value.id == "page":
            return True
        # self.page.locator(...) 也算
        if isinstance(func.value, ast.Attribute) and func.value.attr == "page":
            return True
    return False


# ============ method_typo 修复 ============

# Playwright Page / Locator 常用方法白名单（仅用于 typo 推断）
_KNOWN_PLAYWRIGHT_METHODS = {
    "click", "fill", "type", "press", "check", "uncheck", "select_option",
    "hover", "focus", "blur", "tap", "dblclick",
    "wait_for", "wait_for_selector", "wait_for_load_state", "wait_for_url",
    "wait_for_timeout", "wait_for_event",
    "locator", "get_by_role", "get_by_text", "get_by_label", "get_by_placeholder",
    "get_by_test_id", "get_by_alt_text", "get_by_title",
    "frame_locator", "content_frame",
    "is_visible", "is_enabled", "is_disabled", "is_hidden", "is_checked", "is_editable",
    "text_content", "inner_text", "inner_html", "get_attribute", "all_inner_texts",
    "count", "all", "first", "last", "nth",
    "evaluate", "eval_on_selector", "eval_on_selector_all",
    "scroll_into_view_if_needed", "bounding_box",
    "screenshot", "set_input_files", "upload_file",
    "goto", "go_back", "go_forward", "reload", "close",
    "bring_to_front", "set_viewport_size",
    "query_selector", "query_selector_all",
    "expect", "to_have_text", "to_be_visible", "to_have_count",
}


def suggest_method_correction(
    attr_name: str,
    known_methods: set[str] | None = None,
) -> str | None:
    """从 AttributeError 的属性名推断正确的方法名。

    Args:
        attr_name: 错写的属性名（如 'clcik'）
        known_methods: 备选正确方法集合；默认用 _KNOWN_PLAYWRIGHT_METHODS

    Returns:
        最接近的方法名，或 None（无足够接近的匹配）
    """
    if known_methods is None:
        known_methods = _KNOWN_PLAYWRIGHT_METHODS
    candidates = difflib.get_close_matches(
        attr_name, list(known_methods), n=1, cutoff=0.6,
    )
    return candidates[0] if candidates else None


def apply_method_typo_fix(
    source_path: Path,
    typo_name: str,
    correct_name: str,
    backup: bool = True,
    dry_run: bool = False,
) -> FixResult:
    """把源码中所有 .<typo_name>( 替换为 .<correct_name>( 。

    使用 AST 定位方法调用位置，仅替换真实的方法调用，
    不会误伤字符串字面量 / 注释 / 变量名。

    Args:
        source_path: pages/**/*.py 文件
        typo_name: 错写的方法名（如 'clcik'）
        correct_name: 正确的方法名（如 'click'）
    """
    if not typo_name or not correct_name or typo_name == correct_name:
        old_source = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
        return FixResult(modified=False, new_source=old_source)

    old_source = source_path.read_text(encoding="utf-8")
    new_source = _replace_attribute_calls(old_source, typo_name, correct_name)
    if new_source == old_source:
        return FixResult(modified=False, new_source=old_source)

    patch = generate_patch(source_path, old_source, new_source)

    backup_path: Path | None = None
    if not dry_run:
        if backup:
            backup_path = source_path.with_suffix(source_path.suffix + ".bak")
            shutil.copy2(source_path, backup_path)
        source_path.write_text(new_source, encoding="utf-8")

    return FixResult(modified=True, new_source=new_source, backup_path=backup_path, patch=patch)


# ============ deprecated_api 修复 ============

# Playwright Python 已弃用 API → 新 API 映射（仅 1:1 可直接替换的）
DEPRECATED_API_MAPPING = {
    # ElementHandle 路线已不推荐，locator() 是新规范
    "query_selector": "locator",
    "query_selector_all": "locator",
    # dispatch_event / $eval 系列保留给复杂场景，需参数变换，MVP 不处理
}


def apply_deprecated_api_fix(
    source_path: Path,
    old_method: str,
    new_method: str,
    backup: bool = True,
    dry_run: bool = False,
) -> FixResult:
    """把 .<old_method>( 替换为 .<new_method>( 。

    用于 Playwright 已弃用 API 的 1:1 替换。
    例：page.query_selector("input") → page.locator("input")

    使用 AST 定位，避免误伤字符串字面量。

    Args:
        source_path: pages/**/*.py 文件
        old_method: 已弃用方法名（如 'query_selector'）
        new_method: 新方法名（如 'locator'）
    """
    if not old_method or not new_method or old_method == new_method:
        old_source = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
        return FixResult(modified=False, new_source=old_source)

    old_source = source_path.read_text(encoding="utf-8")
    new_source = _replace_attribute_calls(old_source, old_method, new_method)
    if new_source == old_source:
        return FixResult(modified=False, new_source=old_source)

    patch = generate_patch(source_path, old_source, new_source)

    backup_path: Path | None = None
    if not dry_run:
        if backup:
            backup_path = source_path.with_suffix(source_path.suffix + ".bak")
            shutil.copy2(source_path, backup_path)
        source_path.write_text(new_source, encoding="utf-8")

    return FixResult(modified=True, new_source=new_source, backup_path=backup_path, patch=patch)


def _replace_attribute_calls(source: str, old_attr: str, new_attr: str) -> str:
    """AST 定位所有 .<old_attr> 形式的属性访问并替换为 .<new_attr>。

    仅替换真实代码中的属性名，不误伤字符串 / 注释 / 变量名。

    要求：属性名必须是 Call 的 func，即 `<expr>.<old_attr>(...)`。
    这样避免误改 `obj.old_attr`（无括号）这种属性读取。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    # 收集要替换的位置：(lineno, end_col_offset)
    positions: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != old_attr:
            continue
        # func.end_col_offset 指向属性名末尾
        if func.end_lineno is None or func.end_col_offset is None:
            continue
        # 仅当属性名正好在末尾（不是 subattribute 之类）才替换
        # 校验：源码切片应该是 old_attr
        positions.append((func.end_lineno, func.end_col_offset))

    if not positions:
        return source

    # 按位置倒序应用（从文件末尾往前改，避免 offset 失效）
    positions.sort(reverse=True)
    lines = source.splitlines(keepends=True)
    for lineno, end_col in positions:
        line = lines[lineno - 1]
        start = end_col - len(old_attr)
        # 安全校验：确认切片与 old_attr 匹配
        if line[start:end_col] != old_attr:
            continue
        lines[lineno - 1] = line[:start] + new_attr + line[end_col:]

    return "".join(lines)


# ============ patch 生成 ============

def generate_patch(
    source_path: Path,
    old_source: str,
    new_source: str,
) -> str:
    """生成 unified diff 格式的 patch。"""
    diff = difflib.unified_diff(
        old_source.splitlines(keepends=True),
        new_source.splitlines(keepends=True),
        fromfile=str(source_path),
        tofile=str(source_path),
    )
    return "".join(diff)


# ============ rollback ============

def rollback(backup_path: Path, source_path: Path) -> None:
    """验证失败时从 .bak 恢复。"""
    if not backup_path.exists():
        return
    shutil.copy2(backup_path, source_path)
    backup_path.unlink()


# ============ async_wait 修复（missing_async_list_wait）============

_ASYNC_WAIT_HELPER_TEMPLATE = '''
    def _wait_for_product_list_loaded(self, timeout_ms: int = 10000) -> None:
        """等商品列表首屏渲染完成。

        修复异步加载导致 get_product_count() 立即返回 0 的误报。
        策略：先等 networkidle（请求完结），再等常见商品 selector 出现至少 1 个元素。
        失败不抛异常，让后续 count/assert 揭示真实状态。
        """
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout_ms)
        except Exception:
            pass
        try:
            self.page.wait_for_function(
                """() => {
                    const sels = ['.product-card', '.goods-card', '.search-result-item',
                                  '.item-card', '[data-product-id]', '.product-item'];
                    return sels.some(s => document.querySelectorAll(s).length > 0);
                }""",
                timeout=timeout_ms,
            )
        except Exception:
            pass
'''


def apply_async_wait_fix(
    source_path: Path,
    base_page_path: Path,
    method_name: str = "get_product_count",
    helper_name: str = "_wait_for_product_list_loaded",
    backup: bool = True,
    dry_run: bool = False,
) -> FixResult:
    """在 page object 的 list-getter 方法首行插入 self.<helper_name>() 调用，
    并在 base_page.py 追加 helper 方法定义。

    触发：SCRIPT_ERROR + 搜索正向断言 0 结果（missing_async_list_wait）。

    Args:
        source_path: pages/**/*.py，含 `def <method_name>(self)`
        base_page_path: pages/base_page.py，BasePage 类所在
        method_name: 要插入 wait 的方法名（默认 get_product_count）
        helper_name: wait helper 方法名（默认 _wait_for_product_list_loaded）
    """
    old_source = source_path.read_text(encoding="utf-8")

    method_modified, new_source = _insert_wait_call(
        old_source, method_name, helper_name,
    )

    base_old = base_page_path.read_text(encoding="utf-8") if base_page_path.exists() else ""
    base_modified = False
    new_base = base_old
    if f"def {helper_name}(" not in base_old:
        new_base = _append_helper_to_base_page(base_old)
        base_modified = True

    if not method_modified and not base_modified:
        return FixResult(modified=False, new_source=old_source)

    patch = generate_patch(source_path, old_source, new_source)

    backup_path: Path | None = None
    if not dry_run:
        if backup:
            backup_path = source_path.with_suffix(source_path.suffix + ".bak")
            shutil.copy2(source_path, backup_path)
        source_path.write_text(new_source, encoding="utf-8")
        if base_modified:
            base_page_path.write_text(new_base, encoding="utf-8")

    return FixResult(
        modified=True, new_source=new_source,
        backup_path=backup_path, patch=patch,
    )


def _insert_wait_call(
    source: str, method_name: str, helper_name: str,
) -> tuple[bool, str]:
    """在 `def <method_name>(self)` 方法体首行插入 self.<helper_name>() 调用。

    Returns:
        (modified, new_source)
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False, source

    target_method: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            target_method = node
            break

    if target_method is None:
        return False, source

    body = target_method.body
    # 幂等：方法体首行已是 self.<helper_name>() 或 self._wait_for_*() → 跳过
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Call):
        call = body[0].value
        if (isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "self"
                and (call.func.attr == helper_name
                     or call.func.attr.startswith("_wait_for_"))):
            return False, source

    # 插入位置：方法体首条语句之前（同行缩进）
    first_stmt = body[0]
    insert_lineno = first_stmt.lineno
    lines = source.splitlines(keepends=True)
    line = lines[insert_lineno - 1]
    indent = line[:len(line) - len(line.lstrip())]

    wait_line = f"{indent}self.{helper_name}()\n"
    lines.insert(insert_lineno - 1, wait_line)

    return True, "".join(lines)


def _append_helper_to_base_page(source: str) -> str:
    """在 BasePage 类末尾追加 _wait_for_product_list_loaded 方法定义。

    简化策略：AST 找 BasePage 类，在类最后一条语句后插入模板。
    若解析失败 / 无 BasePage 类，追加到文件末尾（best-effort）。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source + "\n" + _ASYNC_WAIT_HELPER_TEMPLATE + "\n"

    base_class: ast.ClassDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "BasePage":
            base_class = node
            break

    if base_class is None:
        return source + "\n" + _ASYNC_WAIT_HELPER_TEMPLATE + "\n"

    last_stmt = base_class.body[-1]
    end_lineno = last_stmt.end_lineno or len(source.splitlines())

    lines = source.splitlines(keepends=True)
    lines.insert(end_lineno, _ASYNC_WAIT_HELPER_TEMPLATE + "\n")

    return "".join(lines)
