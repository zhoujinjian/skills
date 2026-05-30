"""
视觉测试文件生成模板

本文件展示视觉测试脚本的生成模式。
实际生成时，将根据扫描到的页面和元素替换模板中的占位符。

模板变量说明（生成时替换）：
  {PageName}       — POM 类名（如 LoginPage）
  {page_name}      — 页面标识（如 login）
  {page_module}    — POM 模块路径（如 auth.login_page）
  {dynamic_masks}  — 动态区域遮罩选择器列表
  {elements}       — 需要元素级截图断言的元素信息
"""

# ============================================================
# 模板 — 以下是生成时的代码模式（含占位符，不直接执行）
# ============================================================

# --- 生成模板 START ---
# import pytest
# from playwright.sync_api import Page
# from pages.{page_module} import {PageName}Page
#
#
# @pytest.mark.visual
# class TestVisual{PageName}:
#     """{PageName} 视觉回归测试"""
#
#     def test_{page_name}_full_visual(self, page: Page, cross_browser_tolerance):
#         """{PageName} 初始状态全页截图比对"""
#         page_obj = {PageName}Page(page).navigate()
#         page_obj.mask_dynamic_regions([
#             {dynamic_masks}
#         ])
#         page_obj.assert_visual_match(
#             "{page_name}_initial",
#             threshold=cross_browser_tolerance,
#         )
#
#     def test_{page_name}_form_element_visual(self, page: Page, cross_browser_tolerance):
#         """{PageName} 表单区域元素级截图比对"""
#         page_obj = {PageName}Page(page).navigate()
#         form_locator = page.locator("form")
#         page_obj.assert_element_visual(
#             form_locator,
#             "{page_name}_form",
#             threshold=cross_browser_tolerance,
#         )
#
#     @pytest.mark.parametrize(
#         "viewport_preset",
#         ["desktop", "tablet", "mobile"],
#         indirect=True,
#     )
#     def test_{page_name}_responsive(
#         self, responsive_context, viewport_preset, cross_browser_tolerance
#     ):
#         """{PageName} 响应式布局视觉测试"""
#         page = responsive_context.new_page()
#         page_obj = {PageName}Page(page).navigate()
#         page_obj.mask_dynamic_regions([
#             {dynamic_masks}
#         ])
#         page_obj.assert_visual_match(
#             "{page_name}_responsive",
#             threshold=cross_browser_tolerance,
#         )
# --- 生成模板 END ---


# ============================================================
# 具体页面生成示例 — 登录页 test_visual_login.py
# ============================================================

# import pytest
# from playwright.sync_api import Page
# from pages.auth.login_page import LoginPage
#
#
# @pytest.mark.visual
# class TestVisualLogin:
#     """登录页视觉回归测试"""
#
#     def test_login_full_visual(self, page: Page, cross_browser_tolerance):
#         """登录页初始状态全页截图比对"""
#         login_page = LoginPage(page).navigate()
#         login_page.mask_dynamic_regions([
#             "img[src*='captcha']",
#             "img[src*='verify']",
#             "img[alt*='验证码']",
#         ])
#         login_page.assert_visual_match(
#             "login_page_initial",
#             threshold=cross_browser_tolerance,
#         )
#
#     def test_login_form_element_visual(self, page: Page, cross_browser_tolerance):
#         """登录表单元素级截图比对"""
#         login_page = LoginPage(page).navigate()
#         form_locator = page.locator("form")
#         login_page.assert_element_visual(
#             form_locator,
#             "login_form",
#             threshold=cross_browser_tolerance,
#         )
#
#     @pytest.mark.parametrize(
#         "viewport_preset",
#         ["desktop", "tablet", "mobile"],
#         indirect=True,
#     )
#     def test_login_responsive(
#         self, responsive_context, viewport_preset, cross_browser_tolerance
#     ):
#         """登录页响应式布局视觉测试"""
#         page = responsive_context.new_page()
#         login_page = LoginPage(page).navigate()
#         login_page.mask_dynamic_regions([
#             "img[src*='captcha']",
#         ])
#         login_page.assert_visual_match(
#             "login_page_responsive",
#             threshold=cross_browser_tolerance,
#         )


# ============================================================
# 具体页面生成示例 — 首页 test_visual_home.py
# ============================================================

# import pytest
# from playwright.sync_api import Page
# from pages.home.home_page import HomePage
#
#
# @pytest.mark.visual
# class TestVisualHome:
#     """首页视觉回归测试"""
#
#     def test_home_full_visual_guest(self, page: Page, cross_browser_tolerance):
#         """首页未登录状态全页截图比对"""
#         home_page = HomePage(page).navigate()
#         home_page.assert_visual_match(
#             "home_page_guest",
#             threshold=cross_browser_tolerance,
#         )
#
#     def test_home_full_visual_logged_in(self, auth_page, cross_browser_tolerance):
#         """首页已登录状态全页截图比对"""
#         home_page = HomePage(auth_page)
#         home_page.assert_visual_match(
#             "home_page_logged_in",
#             threshold=cross_browser_tolerance,
#         )
#
#     @pytest.mark.parametrize(
#         "viewport_preset",
#         ["desktop", "tablet", "mobile"],
#         indirect=True,
#     )
#     def test_home_responsive(
#         self, responsive_context, viewport_preset, cross_browser_tolerance
#     ):
#         """首页响应式布局视觉测试"""
#         page = responsive_context.new_page()
#         home_page = HomePage(page).navigate()
#         home_page.assert_visual_match(
#             "home_page_responsive",
#             threshold=cross_browser_tolerance,
#         )
