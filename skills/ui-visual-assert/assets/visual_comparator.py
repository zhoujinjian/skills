"""
视觉比对引擎 — 基于 pixelmatch + Pillow 的像素级截图比对

提供两种比对模式：
  1. pixelmatch 模式（推荐）：使用 pixelmatch 库做逐像素比对
  2. Pillow + numpy 降级模式：pixelmatch 不可用时自动降级

基线管理：
  - 首次运行自动创建基线
  - UPDATE_SNAPSHOTS=true 环境变量可更新基线
  - 比对失败自动保存差异图

用法：
  comparator = VisualComparator(threshold=0.1, max_diff_ratio=0.01)
  result = comparator.compare(
      baseline_path="baselines/login_chromium_1920x1080.png",
      actual_path="actual/login_chromium_1920x1080.png",
      diff_path="diff/login_chromium_1920x1080_diff.png",
  )
  assert result.passed, f"Visual mismatch: {result.mismatch_percentage:.2%}"
"""

import os
import logging
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    raise ImportError("Pillow 未安装，请运行: pip install Pillow")

try:
    from pixelmatch import pixelmatch as _pixelmatch
    USE_PIXELMATCH = True
except ImportError:
    USE_PIXELMATCH = False
    logging.getLogger(__name__).info(
        "pixelmatch 未安装，使用 Pillow + numpy 降级比对模式。"
        "安装 pixelmatch 可获得更精确的比对: pip install pixelmatch"
    )

try:
    import numpy as np
    USE_NUMPY = True
except ImportError:
    USE_NUMPY = False


logger = logging.getLogger(__name__)


@dataclass
class VisualResult:
    """视觉比对结果"""
    passed: bool
    mismatch_percentage: float
    diff_path: str
    mismatched_pixels: int
    total_pixels: int

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[Visual {status}] "
            f"{self.mismatched_pixels}/{self.total_pixels} pixels differ "
            f"({self.mismatch_percentage:.2%})"
        )


class VisualComparator:
    """像素级截图比对引擎"""

    def __init__(
        self,
        threshold: float = 0.1,
        max_diff_ratio: float = 0.01,
        diff_color: tuple = (255, 0, 0),
    ):
        """
        Args:
            threshold: 逐像素颜色距离容差（0.0-1.0），值越大允许的色差越大
            max_diff_ratio: 最大允许差异像素占总像素比例（0.01 = 1%）
            diff_color: 差异像素高亮颜色（RGB）
        """
        self.threshold = threshold
        self.max_diff_ratio = max_diff_ratio
        self.diff_color = diff_color

    def compare(
        self,
        baseline_path: str,
        actual_path: str,
        diff_path: str,
        mask_regions: list[tuple[int, int, int, int]] | None = None,
    ) -> VisualResult:
        """
        像素级比对两张截图

        Args:
            baseline_path: 基线图路径
            actual_path: 实际截图路径
            diff_path: 差异图输出路径
            mask_regions: 遮罩区域列表 [(x, y, width, height), ...]

        Returns:
            VisualResult 比对结果
        """
        baseline_img = Image.open(baseline_path).convert("RGB")
        actual_img = Image.open(actual_path).convert("RGB")

        # 尺寸对齐
        if baseline_img.size != actual_img.size:
            logger.warning(
                f"尺寸不一致: baseline={baseline_img.size}, "
                f"actual={actual_img.size}，自动缩放实际图"
            )
            actual_img = actual_img.resize(baseline_img.size, Image.LANCZOS)

        width, height = baseline_img.size
        total_pixels = width * height

        # 应用遮罩区域（将遮罩区域设为相同颜色，排除比对）
        if mask_regions:
            baseline_img = self._apply_mask(baseline_img, mask_regions)
            actual_img = self._apply_mask(actual_img, mask_regions)

        # 执行比对
        if USE_PIXELMATCH:
            mismatched = self._compare_pixelmatch(
                baseline_img, actual_img, diff_path, width, height
            )
        else:
            mismatched = self._compare_pillow(
                baseline_img, actual_img, diff_path, width, height
            )

        mismatch_percentage = mismatched / total_pixels
        passed = mismatch_percentage <= self.max_diff_ratio

        result = VisualResult(
            passed=passed,
            mismatch_percentage=mismatch_percentage,
            diff_path=diff_path if not passed else "",
            mismatched_pixels=mismatched,
            total_pixels=total_pixels,
        )

        if not passed:
            logger.warning(result.summary())
        else:
            logger.info(result.summary())

        return result

    def _compare_pixelmatch(
        self, baseline_img, actual_img, diff_path, width, height
    ) -> int:
        """使用 pixelmatch 库做逐像素比对"""
        diff_img = Image.new("RGB", (width, height))

        mismatched = _pixelmatch(
            baseline_img,
            actual_img,
            diff_img,
            width,
            height,
            threshold=self.threshold,
            includeAA=False,
        )

        if mismatched > 0:
            Path(diff_path).parent.mkdir(parents=True, exist_ok=True)
            diff_img.save(diff_path)

        return mismatched

    def _compare_pillow(
        self, baseline_img, actual_img, diff_path, width, height
    ) -> int:
        """降级模式：使用 Pillow（+ numpy）做像素比对"""
        if USE_NUMPY:
            return self._compare_numpy(
                baseline_img, actual_img, diff_path, width, height
            )

        # 纯 Pillow 逐像素比对
        baseline_px = list(baseline_img.getdata())
        actual_px = list(actual_img.getdata())

        threshold_int = int(self.threshold * 255)
        mismatched = 0
        diff_pixels = []

        for i, (bp, ap) in enumerate(zip(baseline_px, actual_px)):
            color_diff = max(
                abs(bp[0] - ap[0]),
                abs(bp[1] - ap[1]),
                abs(bp[2] - ap[2]),
            )
            if color_diff > threshold_int:
                mismatched += 1
                diff_pixels.append(self.diff_color)
            else:
                diff_pixels.append(ap)

        if mismatched > 0:
            diff_img = Image.new("RGB", (width, height))
            diff_img.putdata(diff_pixels)
            Path(diff_path).parent.mkdir(parents=True, exist_ok=True)
            diff_img.save(diff_path)

        return mismatched

    def _compare_numpy(
        self, baseline_img, actual_img, diff_path, width, height
    ) -> int:
        """使用 numpy 加速的像素比对"""
        arr1 = np.array(baseline_img, dtype=np.int16)
        arr2 = np.array(actual_img, dtype=np.int16)

        diff = np.abs(arr1 - arr2)
        threshold_int = int(self.threshold * 255)
        mismatch_mask = np.max(diff, axis=2) > threshold_int

        mismatched = int(np.sum(mismatch_mask))

        if mismatched > 0:
            diff_arr = np.array(actual_img)
            diff_arr[mismatch_mask] = self.diff_color
            diff_img = Image.fromarray(diff_arr)
            Path(diff_path).parent.mkdir(parents=True, exist_ok=True)
            diff_img.save(diff_path)

        return mismatched

    def _apply_mask(
        self, img: Image.Image, regions: list[tuple[int, int, int, int]]
    ) -> Image.Image:
        """在图像上绘制黑色遮罩区域"""
        img = img.copy()
        draw = ImageDraw.Draw(img)
        for x, y, w, h in regions:
            draw.rectangle([x, y, x + w, y + h], fill=(0, 0, 0))
        return img

    @staticmethod
    def create_baseline(screenshot_path: str, baseline_path: str):
        """将截图复制为基线"""
        Path(baseline_path).parent.mkdir(parents=True, exist_ok=True)
        img = Image.open(screenshot_path)
        img.save(baseline_path, "PNG")
        logger.info(f"[Visual] Created baseline: {baseline_path}")

    @staticmethod
    def update_baseline(screenshot_path: str, baseline_path: str):
        """更新已有基线"""
        Path(baseline_path).parent.mkdir(parents=True, exist_ok=True)
        img = Image.open(screenshot_path)
        img.save(baseline_path, "PNG")
        logger.info(f"[Visual] Updated baseline: {baseline_path}")
