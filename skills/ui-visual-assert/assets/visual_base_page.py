"""
视觉断言方法 — 合并到项目 pages/base_page.py 中的 BasePage 类

将以下方法添加到 BasePage 类中，为所有页面对象提供视觉断言能力。
不修改任何已有方法，只新增以下内容。

所需导入（添加到 base_page.py 文件顶部）：
  import os
  from pathlib import Path
  from utils.visual_comparator import VisualComparator, VisualResult

使用示例：
  login_page.assert_visual_match("login_page_initial", threshold=0.10)
  login_page.mask_dynamic_regions(["img[src*='captcha']"])
  login_page.assert_element_visual(form_locator, "login_form")
"""

import os
import logging
from pathlib import Path
from playwright.sync_api import Locator, Page

from utils.visual_comparator import VisualComparator

logger = logging.getLogger(__name__)


# ============ 以下方法合并到 BasePage 类中 ============


def assert_visual_match(
    self,
    snapshot_name: str,
    threshold: float | None = None,
    mask_regions: list[tuple[int, int, int, int]] | None = None,
    full_page: bool = True,
) -> "BasePage":
    """
    全页截图视觉断言

    Args:
        snapshot_name: 快照名称（用于基线文件命名）
        threshold: 差异容差（None 则使用 cross_browser_tolerance）
        mask_regions: 遮罩区域 [(x, y, w, h), ...]
        full_page: 是否截取整页（True）或仅视口（False）

    Returns:
        self（支持链式调用）
    """
    # 禁用动画，确保截图稳定
    self._disable_animations()

    # 等待页面稳定
    self.page.wait_for_load_state("networkidle", timeout=5000)
    try:
        self.page.evaluate("document.fonts.ready")
    except Exception:
        pass

    # 构建路径
    baseline_path = self._build_baseline_path(snapshot_name)
    actual_path = self._build_actual_path(snapshot_name)
    diff_path = self._build_diff_path(snapshot_name)

    # 确保目录存在
    Path(actual_path).parent.mkdir(parents=True, exist_ok=True)

    # 截取实际图
    self.page.screenshot(path=actual_path, full_page=full_page, type="png")

    # 基线不存在 → 创建基线
    if not Path(baseline_path).exists():
        VisualComparator.create_baseline(actual_path, baseline_path)
        logger.info(f"[Visual] First run, created baseline: {baseline_path}")
        return self

    # 更新模式 → 覆盖基线
    if os.getenv("UPDATE_SNAPSHOTS", "false").lower() == "true":
        VisualComparator.update_baseline(actual_path, baseline_path)
        return self

    # 比对
    comparator = VisualComparator(
        threshold=threshold or 0.1,
        max_diff_ratio=threshold or 0.01,
    )
    result = comparator.compare(
        baseline_path=baseline_path,
        actual_path=actual_path,
        diff_path=diff_path,
        mask_regions=mask_regions,
    )

    assert result.passed, (
        f"Visual mismatch for '{snapshot_name}': "
        f"{result.mismatched_pixels}/{result.total_pixels} pixels differ "
        f"({result.mismatch_percentage:.2%}). "
        f"Diff saved to: {diff_path}"
    )

    return self


def assert_element_visual(
    self,
    locator: Locator,
    snapshot_name: str,
    threshold: float | None = None,
    mask_regions: list[tuple[int, int, int, int]] | None = None,
) -> "BasePage":
    """
    元素级截图视觉断言

    Args:
        locator: 要截图的元素定位器
        snapshot_name: 快照名称
        threshold: 差异容差
        mask_regions: 遮罩区域

    Returns:
        self（支持链式调用）
    """
    self._disable_animations()

    baseline_path = self._build_baseline_path(snapshot_name)
    actual_path = self._build_actual_path(snapshot_name)
    diff_path = self._build_diff_path(snapshot_name)

    Path(actual_path).parent.mkdir(parents=True, exist_ok=True)

    # 元素截图
    locator.screenshot(path=actual_path, type="png")

    if not Path(baseline_path).exists():
        VisualComparator.create_baseline(actual_path, baseline_path)
        logger.info(f"[Visual] First run, created baseline: {baseline_path}")
        return self

    if os.getenv("UPDATE_SNAPSHOTS", "false").lower() == "true":
        VisualComparator.update_baseline(actual_path, baseline_path)
        return self

    comparator = VisualComparator(
        threshold=threshold or 0.1,
        max_diff_ratio=threshold or 0.01,
    )
    result = comparator.compare(
        baseline_path=baseline_path,
        actual_path=actual_path,
        diff_path=diff_path,
        mask_regions=mask_regions,
    )

    assert result.passed, (
        f"Element visual mismatch for '{snapshot_name}': "
        f"{result.mismatched_pixels}/{result.total_pixels} pixels differ "
        f"({result.mismatch_percentage:.2%}). "
        f"Diff saved to: {diff_path}"
    )

    return self


def mask_dynamic_regions(self, css_selectors: list[str]) -> "BasePage":
    """
    注入 CSS 隐藏动态内容（保留布局空间）

    隐藏元素的可见内容但保留其占据的布局空间，
    避免验证码、时间戳等动态内容干扰截图比对。

    Args:
        css_selectors: 要隐藏的 CSS 选择器列表

    Returns:
        self（支持链式调用）
    """
    js = """
    (selectors) => {
        selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                el.style.visibility = 'hidden';
            });
        });
    }
    """
    self.page.evaluate(js, css_selectors)
    return self


def _disable_animations(self) -> None:
    """禁用 CSS 动画和过渡，确保截图状态一致"""
    self.page.add_style_tag(content="""
        *, *::before, *::after {
            animation-duration: 0s !important;
            animation-delay: 0s !important;
            transition-duration: 0s !important;
            transition-delay: 0s !important;
        }
    """)


def _get_visual_meta(self) -> tuple[str, int, int]:
    """获取当前浏览器名和视口尺寸"""
    try:
        browser_name = self.page.context.browser.browser_type.name
    except Exception:
        browser_name = "chromium"
    viewport = self.page.viewport_size or {"width": 1920, "height": 1080}
    return browser_name, viewport["width"], viewport["height"]


def _build_baseline_path(self, snapshot_name: str) -> str:
    """构建基线路径: tests/visual/baselines/{name}_{browser}_{w}x{h}.png"""
    browser, w, h = self._get_visual_meta()
    return f"tests/visual/baselines/{snapshot_name}_{browser}_{w}x{h}.png"


def _build_actual_path(self, snapshot_name: str) -> str:
    """构建实际截图路径: tests/visual/actual/{name}_{browser}_{w}x{h}.png"""
    browser, w, h = self._get_visual_meta()
    return f"tests/visual/actual/{snapshot_name}_{browser}_{w}x{h}.png"


def _build_diff_path(self, snapshot_name: str) -> str:
    """构建差异图路径: tests/visual/diff/{name}_{browser}_{w}x{h}_diff.png"""
    browser, w, h = self._get_visual_meta()
    return f"tests/visual/diff/{snapshot_name}_{browser}_{w}x{h}_diff.png"
