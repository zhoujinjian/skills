"""
视觉测试 Fixtures — 合并到项目 tests/conftest.py

将以下内容追加到 conftest.py 中（在现有 fixtures 之后），
为视觉测试提供响应式视口、跨浏览器容差、基线管理等能力。

所需导入（追加到 conftest.py 文件顶部）：
  import os
  from pathlib import Path

运行方式：
  pytest tests/visual/ -m visual                          # 默认 Chromium
  UPDATE_SNAPSHOTS=true pytest tests/visual/ -m visual    # 更新基线
  pytest tests/visual/ -m visual --browser firefox         # Firefox
  pytest tests/visual/ -m visual --browser chromium --browser firefox --browser webkit
"""

import os
from pathlib import Path
import pytest
from playwright.sync_api import Browser


# ============ 视口预设 ============

VIEWPORT_PRESETS = {
    "desktop": {"width": 1920, "height": 1080},
    "tablet":  {"width": 768,  "height": 1024},
    "mobile":  {"width": 375,  "height": 812},
}

# ============ 跨浏览器容差配置 ============

BROWSER_TOLERANCE = {
    "chromium": 0.10,
    "firefox":  0.15,
    "webkit":   0.12,
}


# ============ 以下 fixtures 追加到 conftest.py ============


@pytest.fixture
def viewport_preset(request):
    """参数化视口选择 — 配合 @pytest.mark.parametrize 使用

    用法:
        @pytest.mark.parametrize("viewport_preset", ["desktop", "tablet", "mobile"], indirect=True)
        def test_responsive(responsive_context, viewport_preset):
            ...
    """
    preset_name = request.param
    return VIEWPORT_PRESETS.get(preset_name, VIEWPORT_PRESETS["desktop"])


@pytest.fixture
def responsive_context(browser: Browser, viewport_preset):
    """创建指定视口的浏览器上下文（禁用动画，统一渲染）

    自动注入 CSS 禁用动画，确保截图一致性。
    测试结束后自动关闭上下文。
    """
    viewport = viewport_preset
    context = browser.new_context(
        viewport=viewport,
        locale="zh-CN",
        device_scale_factor=1,
    )

    # 在每个新页面中禁用动画
    context.add_init_script("""
        const style = document.createElement('style');
        style.textContent = `
            *, *::before, *::after {
                animation-duration: 0s !important;
                animation-delay: 0s !important;
                transition-duration: 0s !important;
                transition-delay: 0s !important;
            }
        `;
        document.head.appendChild(style);
    """)

    yield context
    context.close()


@pytest.fixture
def visual_baseline_dir():
    """确保视觉基线目录存在，返回路径"""
    baseline_dir = Path("tests/visual/baselines")
    baseline_dir.mkdir(parents=True, exist_ok=True)
    return str(baseline_dir)


@pytest.fixture
def update_snapshots():
    """读取 UPDATE_SNAPSHOTS 环境变量

    设置 UPDATE_SNAPSHOTS=true 可覆盖已有基线：
      UPDATE_SNAPSHOTS=true pytest tests/visual/ -m visual
    """
    return os.getenv("UPDATE_SNAPSHOTS", "false").lower() == "true"


@pytest.fixture
def cross_browser_tolerance(browser: Browser):
    """根据当前浏览器返回像素差异容差阈值

    不同浏览器渲染引擎存在固有差异，需要不同的容差：
      chromium: 0.10 (10%) — 基准浏览器
      firefox:  0.15 (15%) — 字体渲染、滚动条宽度差异
      webkit:   0.12 (12%) — Safari 字体平滑差异
    """
    browser_name = browser.browser_type.name
    return BROWSER_TOLERANCE.get(browser_name, 0.10)
