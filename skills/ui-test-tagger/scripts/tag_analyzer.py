#!/usr/bin/env python3
"""
UI 测试脚本智能标签分析器
功能：解析 Playwright/POM UI 测试脚本 → 读取 pages.yaml → 六维智能标签推荐 → 冲突检测 → 标签写入 → 统计报告

六维标签体系：
1. 优先级 (P0/P1/P2/P3)
2. 模块 (module:xxx)
3. 场景 (scene:xxx) — 含 full_flow, visual_regress
4. 页面类型 (page:xxx) — home/list/detail/form/dialog
5. 执行策略 (run:xxx)
6. 浏览器/平台 (browser:xxx, platform:xxx)
"""

import argparse
import ast
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse


# ============================================================
# 标签规范定义
# ============================================================

TAG_SPEC = {
    "priority": {
        "values": ["P0", "P1", "P2", "P3"],
    },
    "module": {
        "values": [
            "module:login", "module:product", "module:cart", "module:order",
            "module:checkout", "module:user", "module:address", "module:payment",
            "module:admin",
        ],
        "path_patterns": {
            "module:login": ["/login", "/signin", "/auth/login", "/logout"],
            "module:product": ["/product", "/products", "/category", "/categories", "/search", "/goods", "/item"],
            "module:cart": ["/cart", "/basket", "/shopping-cart"],
            "module:order": ["/order", "/orders", "/my-orders", "/order-list"],
            "module:checkout": ["/checkout", "/settle", "/place-order"],
            "module:user": ["/user", "/profile", "/account", "/member"],
            "module:address": ["/address", "/addresses", "/shipping"],
            "module:payment": ["/payment", "/pay", "/refund", "/transaction"],
            "module:admin": ["/admin", "/manage", "/dashboard", "/config", "/stats", "/statistics"],
        },
    },
    "scene": {
        "values": ["scene:positive", "scene:negative", "scene:boundary", "scene:full_flow", "scene:visual_regress"],
        "method_patterns": {
            "scene:full_flow": [
                r"(?i)(full_flow|end_to_end|e2e|complete_flow|full_shopping|whole_flow|business_flow|entire_flow|shopping_flow|order_flow|checkout_flow)",
            ],
            "scene:visual_regress": [
                r"(?i)(visual|screenshot|regress|snapshot|pixel_diff|layout_check|responsive|viewport)",
            ],
            "scene:boundary": [
                r"(?i)(boundary|limit|min|max|edge|overflow|underflow|extreme|threshold|too_long|too_short|max_length|min_length|oversized)",
            ],
            "scene:negative": [
                r"(?i)(error|invalid|fail|exception|not_found|unauthorized|forbidden|missing|empty|null|wrong|deny|reject|nonexistent|disabled|expired)",
            ],
            "scene:positive": [
                r"(?i)(success|valid|normal|correct|happy|ok|pass|complete|duplicate|consistent)",
            ],
        },
    },
    "page": {
        "values": ["page:home", "page:list", "page:detail", "page:form", "page:dialog"],
    },
    "run": {
        "values": ["run:smoke", "run:regression", "run:full"],
    },
    "browser": {
        "values": ["browser:chrome", "browser:firefox", "browser:edge", "browser:safari", "browser:headless"],
    },
    "platform": {
        "values": ["platform:windows", "platform:linux", "platform:mac"],
    },
}

# 标准标签到装饰器名的映射（含冒号 → 下划线）
TAG_TO_MARK = {
    "P0": "P0", "P1": "P1", "P2": "P2", "P3": "P3",
    "module:login": "module_login",
    "module:product": "module_product",
    "module:cart": "module_cart",
    "module:order": "module_order",
    "module:checkout": "module_checkout",
    "module:user": "module_user",
    "module:address": "module_address",
    "module:payment": "module_payment",
    "module:admin": "module_admin",
    "scene:positive": "scene_positive",
    "scene:negative": "scene_negative",
    "scene:boundary": "scene_boundary",
    "scene:full_flow": "scene_full_flow",
    "scene:visual_regress": "scene_visual_regress",
    "page:home": "page_home",
    "page:list": "page_list",
    "page:detail": "page_detail",
    "page:form": "page_form",
    "page:dialog": "page_dialog",
    "run:smoke": "run_smoke",
    "run:regression": "run_regression",
    "run:full": "run_full",
    "browser:chrome": "browser_chrome",
    "browser:firefox": "browser_firefox",
    "browser:edge": "browser_edge",
    "browser:safari": "browser_safari",
    "browser:headless": "browser_headless",
    "platform:windows": "platform_windows",
    "platform:linux": "platform_linux",
    "platform:mac": "platform_mac",
}

# 装饰器名反向映射到标准标签
MARK_TO_TAG = {v: k for k, v in TAG_TO_MARK.items()}

# 旧标记到标准标签的映射
LEGACY_MARK_MAP = {
    "p0": "P0", "p1": "P1", "p2": "P2", "p3": "P3",
    "smoke": "run:smoke",
    "regression": "run:regression",
    "full": "run:full",
}

# 类名/路径关键词到模块的映射
MODULE_KEYWORDS = {
    "module:login": ["login", "signin", "auth", "logout", "log_in", "sign_in",
                     "register", "signup", "sign_up"],
    "module:product": ["product", "goods", "item", "catalog", "search", "category", "banner"],
    "module:cart": ["cart", "basket", "shopping"],
    "module:order": ["order"],
    "module:checkout": ["checkout", "settle", "placeorder"],
    "module:user": ["user", "profile", "account", "member"],
    "module:address": ["address", "location", "shipping"],
    "module:payment": ["payment", "pay", "refund", "transaction"],
    "module:admin": ["admin", "manage", "config", "dashboard", "stats"],
}

# 路径段到模块的映射（目录/文件名识别）
DIR_MODULE_MAP = {
    "login": "module:login", "signin": "module:login", "auth": "module:login",
    "register": "module:login", "signup": "module:login",
    "product": "module:product", "products": "module:product",
    "category": "module:product", "goods": "module:product",
    "cart": "module:cart", "basket": "module:cart",
    "order": "module:order", "orders": "module:order",
    "checkout": "module:checkout", "settle": "module:checkout",
    "user": "module:user", "profile": "module:user", "account": "module:user",
    "address": "module:address", "addresses": "module:address",
    "payment": "module:payment", "pay": "module:payment",
    "admin": "module:admin", "dashboard": "module:admin",
}

# 中文 module 名（ui-page-parser 输出）→ 英文标准标签映射
CN_MODULE_MAP = {
    "登录": "login", "登录注册": "login", "认证": "login", "鉴权": "login",
    "注册": "login", "登录/注册": "login",
    "商品浏览": "product", "商品": "product", "商品模块": "product",
    "购物车": "cart",
    "订单": "order", "订单管理": "order",
    "购物流程": "checkout", "结算": "checkout", "下单": "checkout",
    "用户中心": "user", "用户": "user", "会员": "user", "个人中心": "user",
    "地址": "address", "收货地址": "address", "地址管理": "address",
    "支付": "payment", "支付管理": "payment",
    "后台": "admin", "管理": "admin", "管理员": "admin", "后台管理": "admin",
}

# ui-page-parser 输出的自由 page_type → 标准 page 标签映射
CN_PAGE_TYPE_MAP = {
    "dashboard": "home", "门户": "home", "首页": "home",
    "list": "list", "列表": "list", "列表页": "list",
    "detail": "detail", "详情": "detail", "详情页": "detail",
    "form": "form", "表单": "form", "表单页": "form",
    "dialog": "dialog", "弹窗": "dialog", "模态框": "dialog",
}

# POM 类名前缀 → (module, page_type) 启发式映射
# 当测试方法中没有 page.goto() URL 时，POM 类名是最可靠的页面/模块推断来源
POM_CLASS_HINTS = {
    "login": ("module:login", "page:form"),
    "register": ("module:login", "page:form"),
    "signin": ("module:login", "page:form"),
    "signup": ("module:login", "page:form"),
    "home": ("module:product", "page:home"),
    "index": ("module:product", "page:home"),
    "productlist": ("module:product", "page:list"),
    "productdetail": ("module:product", "page:detail"),
    "product": ("module:product", "page:list"),
    "goods": ("module:product", "page:list"),
    "search": ("module:product", "page:list"),
    "cart": ("module:cart", "page:list"),
    "basket": ("module:cart", "page:list"),
    "orderlist": ("module:order", "page:list"),
    "orderdetail": ("module:order", "page:detail"),
    "order": ("module:order", "page:list"),
    "checkout": ("module:checkout", "page:form"),
    "settle": ("module:checkout", "page:form"),
    "payment": ("module:payment", "page:form"),
    "pay": ("module:payment", "page:form"),
    "addresslist": ("module:address", "page:list"),
    "addressedit": ("module:address", "page:form"),
    "address": ("module:address", "page:list"),
    "user": ("module:user", "page:home"),
    "profile": ("module:user", "page:home"),
    "account": ("module:user", "page:home"),
    "member": ("module:user", "page:home"),
    "admin": ("module:admin", "page:home"),
    "dashboard": ("module:admin", "page:home"),
}

# 核心链路路径模式（用于 P0 判断）
CORE_PATH_PATTERNS = [
    r"/login", r"/signin", r"/auth/login",
    r"/register", r"/signup",
    r"/order/create", r"/order/submit", r"/order/place",
    r"/checkout", r"/settle",
    r"/payment/pay", r"/payment/checkout",
    r"/cart/checkout", r"/place-order",
]

# 页面类型模式顺序（按优先级匹配，form > detail > list > home）
PAGE_TYPE_PATTERNS = [
    ("page:form", [
        r"/login", r"/signin", r"/register", r"/signup",
        r"/create", r"/edit", r"/add", r"/new",
        r"/checkout", r"/settle",
        r"/address/(edit|new|add)",
    ]),
    ("page:detail", [
        r"/detail", r"/info", r"/view",
        r"/\d+(?:/|$)",  # 数字 ID
        r"/[a-z0-9_-]{8,}(?:/|$)",  # 长 slug
    ]),
    ("page:list", [
        r"/list", r"/search", r"/products",
        r"/category", r"/categories", r"/orders", r"/goods",
    ]),
    ("page:home", [
        r"^/$", r"^/home", r"^/index",
    ]),
]

# 冲突检测规则
CONFLICT_RULES = [
    ("P0", "P3", "优先级冲突：同一方法不应同时标记为最高优先级(P0)和最低优先级(P3)"),
    ("P0", "P2", "优先级冲突：P0核心链路与P2一般功能标记冲突"),
    ("P1", "P3", "优先级冲突：P1重要功能与P3边缘场景标记冲突"),
    ("scene:positive", "scene:negative", "场景冲突：同一方法不应同时为正向和异常场景"),
    ("scene:positive", "scene:boundary", "场景冲突：正向和边界场景不应共存"),
    ("scene:positive", "scene:visual_regress", "场景冲突：正向功能与视觉回归目的不同"),
    ("run:smoke", "P3", "执行策略冲突：冒烟用例不应标记为P3边缘场景"),
    ("run:smoke", "scene:negative", "执行策略冲突：冒烟用例通常不包含异常场景"),
    # 页面类型互斥
    ("page:home", "page:list", "页面类型冲突：同一方法不应跨多种页面类型"),
    ("page:home", "page:detail", "页面类型冲突：同一方法不应跨多种页面类型"),
    ("page:home", "page:form", "页面类型冲突：同一方法不应跨多种页面类型"),
    ("page:list", "page:detail", "页面类型冲突：同一方法不应跨多种页面类型"),
    ("page:list", "page:form", "页面类型冲突：同一方法不应跨多种页面类型"),
    ("page:detail", "page:form", "页面类型冲突：同一方法不应跨多种页面类型"),
]


@dataclass
class TagResult:
    """单个测试方法的标签分析结果"""
    file_path: str
    class_name: str
    method_name: str
    docstring: str = ""
    existing_tags: Set[str] = field(default_factory=set)
    existing_raw_marks: Set[str] = field(default_factory=set)
    recommended_tags: Set[str] = field(default_factory=set)
    conflicts: List[str] = field(default_factory=list)
    missing_tags: List[str] = field(default_factory=list)
    goto_urls: List[str] = field(default_factory=list)
    pom_class_names: Set[str] = field(default_factory=set)
    dir_module: str = ""
    yaml_module: str = ""
    yaml_page_type: str = ""
    yaml_priority: str = ""
    has_dialog: bool = False


@dataclass
class TagStatistics:
    """标签统计"""
    total_methods: int = 0
    total_classes: int = 0
    total_files: int = 0
    tag_distribution: Dict[str, Dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    conflict_count: int = 0
    missing_tag_methods: List[Dict] = field(default_factory=list)
    coverage_gaps: List[str] = field(default_factory=list)
    replaced_marks: int = 0
    added_marks: int = 0


# ============================================================
# pages.yaml 加载
# ============================================================

class PagesYamlLoader:
    """加载 pages.yaml，建立 url → (module, page_type, priority) 的索引。

    兼容 ui-page-parser 输出格式：
    - 字段名兼容 page_name / name
    - 中文 module（如 "商品浏览"）通过 CN_MODULE_MAP 映射到英文标签
    - 自由 page_type（如 "dashboard"）通过 CN_PAGE_TYPE_MAP 映射到标准值
    - 当 YAML 整体解析失败时降级到正则提取，避免阻塞标签化流程
    """

    def __init__(self):
        self.url_index: Dict[str, Dict] = {}
        self.name_index: Dict[str, Dict] = {}

    def load(self, path: str) -> bool:
        try:
            import yaml
        except ImportError:
            print("[WARN] 未安装 PyYAML，跳过 pages.yaml 加载")
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_text = f.read()
        except Exception as e:
            print(f"[WARN] 读取 pages.yaml 失败: {e}")
            return False

        # 尝试标准 YAML 解析
        try:
            data = yaml.safe_load(raw_text)
            if isinstance(data, dict) and data.get("pages"):
                self._index_pages(data["pages"])
                print(f"[INFO] pages.yaml 加载成功: {len(self.url_index)} 个 URL, {len(self.name_index)} 个页面")
                return True
        except Exception as e:
            print(f"[WARN] pages.yaml 标准解析失败 ({e.__class__.__name__})，降级到正则提取")

        # 降级：从原始文本逐块提取 page 信息
        # pages.yaml 由 ui-page-parser 生成，pages 数组下每项以 `  - page_name:` 起始
        try:
            self._index_from_raw(raw_text)
            if self.url_index:
                print(f"[INFO] pages.yaml 降级提取成功: {len(self.url_index)} 个 URL, {len(self.name_index)} 个页面")
                return True
        except Exception as e:
            print(f"[WARN] pages.yaml 降级提取失败: {e}")
        return False

    def _index_pages(self, pages: list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            url = str(page.get("url", "")).strip()
            name = str(page.get("page_name") or page.get("name") or "").strip()
            module = self._normalize_module(str(page.get("module", "")).strip())
            page_type = self._normalize_page_type(str(page.get("page_type", "")).strip())
            priority = str(page.get("priority", "")).strip().upper()
            if priority and not priority.startswith("P"):
                priority = ""

            info = {
                "module": module,
                "page_type": page_type,
                "priority": priority,
                "url": url,
                "name": name,
            }
            if url:
                self.url_index[self._normalize_url(url)] = info
            if name:
                self.name_index[name] = info

    def _index_from_raw(self, raw_text: str):
        """降级提取：从原始文本识别每个 `- page_name:` 起始的块"""
        # 按行扫描，遇到 `  - page_name:` 起一个新块，块内提取 url/module/page_type
        lines = raw_text.splitlines()
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]
            stripped = line.strip()
            # 块起始：`- page_name: "..."` 或 `- name: "..."`
            if stripped.startswith("- ") and ("page_name:" in stripped or "name:" in stripped):
                block_lines = [stripped]
                # 收集块内同缩进或更深的字段，直到下一个块起始或顶级 key
                block_indent = len(line) - len(line.lstrip())
                j = i + 1
                while j < n:
                    nl = lines[j]
                    ns = nl.strip()
                    if ns == "":
                        j += 1
                        continue
                    cur_indent = len(nl) - len(nl.lstrip())
                    if cur_indent < block_indent and (ns.startswith("- ") or not ns.startswith("-")):
                        # 离开当前块
                        break
                    if ns.startswith("- ") and cur_indent == block_indent:
                        # 同级新块
                        break
                    block_lines.append(ns)
                    j += 1
                self._parse_block(block_lines)
                i = j
            else:
                i += 1

    def _parse_block(self, block_lines: List[str]):
        name = ""
        url = ""
        module = ""
        page_type = ""
        for ln in block_lines:
            if ln.startswith("- page_name:") or ln.startswith("- name:"):
                name = self._strip_yaml_str(ln.split(":", 1)[1])
            elif ln.startswith("page_name:") or ln.startswith("name:"):
                name = self._strip_yaml_str(ln.split(":", 1)[1])
            elif ln.startswith("url:"):
                url = self._strip_yaml_str(ln.split(":", 1)[1])
            elif ln.startswith("module:"):
                module = self._normalize_module(self._strip_yaml_str(ln.split(":", 1)[1]))
            elif ln.startswith("page_type:"):
                page_type = self._normalize_page_type(self._strip_yaml_str(ln.split(":", 1)[1]))

        if not url:
            return
        info = {
            "module": module,
            "page_type": page_type,
            "priority": "",
            "url": url,
            "name": name,
        }
        self.url_index[self._normalize_url(url)] = info
        if name:
            self.name_index[name] = info

    @staticmethod
    def _strip_yaml_str(s: str) -> str:
        s = s.strip()
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1]
        return s.strip()

    @staticmethod
    def _normalize_module(value: str) -> str:
        if not value:
            return ""
        if value.startswith("module:"):
            return value
        # 中文 → 英文
        if value in CN_MODULE_MAP:
            return f"module:{CN_MODULE_MAP[value]}"
        # 已经是英文小写
        if value.isascii() and value.islower():
            return f"module:{value}"
        # 默认返回原值（让上层做 URL fallback）
        return ""

    @staticmethod
    def _normalize_page_type(value: str) -> str:
        if not value:
            return ""
        if value.startswith("page:"):
            return value
        # 中文/自由值 → 标准 page:xxx
        mapped = CN_PAGE_TYPE_MAP.get(value.lower(), "")
        if mapped:
            return f"page:{mapped}"
        return ""

    def lookup_url(self, url: str) -> Optional[Dict]:
        if not url:
            return None
        # 精确匹配
        normalized = self._normalize_url(url)
        if normalized in self.url_index:
            return self.url_index[normalized]
        # 模糊匹配：URL 中含动态参数（如 :id）时，尝试用前缀匹配
        # 例如 page.goto("/product/12345") 匹配 pages.yaml 中的 /product/:id
        best_match = None
        best_score = -1
        for pattern, info in self.url_index.items():
            if ":id" in pattern or ":orderNo" in pattern or ":" in pattern:
                # 将 :xxx 转为正则
                regex = re.sub(r":[a-zA-Z_]+", r"[^/]+", pattern)
                regex = "^" + regex + "(?:/.*)?$"
                if re.match(regex, normalized):
                    # 优先选择更长的固定前缀
                    score = len(pattern)
                    if score > best_score:
                        best_score = score
                        best_match = info
        return best_match

    @staticmethod
    def _normalize_url(url: str) -> str:
        url = url.strip()
        if url.startswith(("http://", "https://")):
            parsed = urlparse(url)
            return parsed.path or "/"
        return url


# ============================================================
# 脚本语义解析
# ============================================================

class UITestScriptParser:
    """解析 Playwright/POM UI 测试脚本"""

    def __init__(self, script_dir: str, pages_loader: Optional[PagesYamlLoader] = None):
        self.script_dir = Path(script_dir)
        self.pages_loader = pages_loader
        self.results: List[TagResult] = []
        self.file_set: Set[str] = set()

    def parse_all(self) -> List[TagResult]:
        test_files = list(self.script_dir.rglob("test_*.py")) + list(self.script_dir.rglob("*_test.py"))
        for tf in test_files:
            self._parse_file(tf)
        return self.results

    def _parse_file(self, file_path: Path):
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception as e:
            print(f"[ERROR] 解析文件失败 {file_path}: {e}")
            return

        rel_path = str(file_path.relative_to(self.script_dir))
        self.file_set.add(rel_path)

        dir_module = self._infer_module_from_path(rel_path)
        file_docstring = ast.get_docstring(tree) or ""

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                class_docstring = ast.get_docstring(node) or ""
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
                        result = self._extract_method_info(
                            rel_path, node.name, item, class_docstring, file_docstring, dir_module
                        )
                        self.results.append(result)

    def _infer_module_from_path(self, rel_path: str) -> str:
        parts = Path(rel_path).parts
        for part in parts:
            lower_part = part.lower()
            for key, module in DIR_MODULE_MAP.items():
                if key in lower_part:
                    return module
        return ""

    def _extract_method_info(self, file_path: str, class_name: str,
                             method_node: ast.FunctionDef, class_docstring: str,
                             file_docstring: str, dir_module: str) -> TagResult:
        method_docstring = ast.get_docstring(method_node) or ""
        existing_tags, existing_raw_marks = self._extract_existing_tags(method_node)
        goto_urls = self._extract_goto_urls(method_node)
        pom_class_names = self._extract_pom_class_names(method_node)
        has_dialog = self._detect_dialog(method_node, method_docstring)

        combined_docstring = f"{class_docstring}\n{method_docstring}"

        # 从 pages.yaml 查找辅助信息（基于 goto URL）
        yaml_module, yaml_page_type, yaml_priority = "", "", ""
        for url in goto_urls:
            info = self.pages_loader.lookup_url(url) if self.pages_loader else None
            if info:
                yaml_module = yaml_module or info.get("module", "")
                yaml_page_type = yaml_page_type or info.get("page_type", "")
                yaml_priority = yaml_priority or info.get("priority", "")

        return TagResult(
            file_path=file_path,
            class_name=class_name,
            method_name=method_node.name,
            docstring=combined_docstring,
            existing_tags=existing_tags,
            existing_raw_marks=existing_raw_marks,
            goto_urls=goto_urls,
            pom_class_names=pom_class_names,
            dir_module=dir_module,
            yaml_module=yaml_module,
            yaml_page_type=yaml_page_type,
            yaml_priority=yaml_priority,
            has_dialog=has_dialog,
        )

    def _extract_existing_tags(self, method_node: ast.FunctionDef) -> Tuple[Set[str], Set[str]]:
        tags = set()
        raw_marks = set()

        for decorator in method_node.decorator_list:
            tag, raw = self._parse_decorator_tag(decorator)
            if tag:
                tags.add(tag)
            if raw:
                raw_marks.add(raw)

        docstring = ast.get_docstring(method_node) or ""
        tags_match = re.search(r"Tags:\s*(.+)", docstring)
        if tags_match:
            for t in tags_match.group(1).split(","):
                t = t.strip()
                if t:
                    std_tag = LEGACY_MARK_MAP.get(t, t)
                    tags.add(std_tag)

        return tags, raw_marks

    def _parse_decorator_tag(self, decorator) -> Tuple[Optional[str], Optional[str]]:
        raw = None
        attr_name = None

        if isinstance(decorator, ast.Attribute):
            if (isinstance(decorator.value, ast.Attribute) and
                decorator.value.attr == "mark" and
                isinstance(decorator.value.value, ast.Name) and
                decorator.value.value.id == "pytest"):
                attr_name = decorator.attr
                raw = f"pytest.mark.{attr_name}"
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                tag, r = self._parse_decorator_tag(decorator.func)
                return tag, r
        elif isinstance(decorator, ast.Name):
            attr_name = decorator.id
            raw = attr_name

        if attr_name:
            std_tag = MARK_TO_TAG.get(attr_name)
            if not std_tag:
                std_tag = LEGACY_MARK_MAP.get(attr_name, attr_name)
            return std_tag, raw

        return None, None

    def _extract_goto_urls(self, method_node: ast.FunctionDef) -> List[str]:
        urls = []
        for node in ast.walk(method_node):
            if isinstance(node, ast.Call):
                url = self._parse_goto_call(node)
                if url and url not in urls:
                    urls.append(url)
        return urls

    def _extract_pom_class_names(self, method_node: ast.FunctionDef) -> Set[str]:
        """提取方法体内引用的 POM 类名（形如 XxxPage(...)）。

        Playwright POM 模式常见写法：
            login_page = LoginPage(page).navigate()
            RegisterPage(page).fill_form(...)

        识别 Call 节点的 func 是 Name/Class 实例化，类名以 Page 结尾。
        """
        pom_names = set()
        for node in ast.walk(method_node):
            if isinstance(node, ast.Call):
                name = ""
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    # self.page_obj.method() 不算 POM 类
                    continue
                if name and (name.endswith("Page") or name.endswith("PageObject")):
                    if name not in {"Page", "BasePage"}:
                        pom_names.add(name)
        return pom_names

    def _parse_goto_call(self, call_node: ast.Call) -> str:
        if isinstance(call_node.func, ast.Attribute):
            if call_node.func.attr == "goto":
                if call_node.args:
                    url = self._extract_string_value(call_node.args[0])
                    if url:
                        return url
                for kw in call_node.keywords:
                    if kw.arg == "url":
                        return self._extract_string_value(kw.value)
        return ""

    def _detect_dialog(self, method_node: ast.FunctionDef, docstring: str) -> bool:
        try:
            source_segment = ast.dump(method_node)
        except Exception:
            source_segment = ""
        keywords = ["dialog", "modal", "popup", "page.on", "expect_dialog", "page.expect_event"]
        for kw in keywords:
            if kw in source_segment:
                return True
        doc_lower = docstring.lower()
        if any(kw in doc_lower for kw in ["弹窗", "对话框", "模态框", "dialog", "modal", "popup"]):
            return True
        return False

    def _extract_string_value(self, node) -> str:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts = []
            for val in node.values:
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    parts.append(val.value)
            return "".join(parts)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left = self._extract_string_value(node.left)
            right = self._extract_string_value(node.right)
            return f"{left}{right}"
        return ""


# ============================================================
# 智能标签推荐
# ============================================================

class TagRecommender:
    """六维智能标签推荐"""

    def __init__(self, pages_loader: Optional[PagesYamlLoader] = None,
                 preset_browser: str = "", preset_platform: str = ""):
        self.pages_loader = pages_loader
        self.preset_browser = preset_browser
        self.preset_platform = preset_platform

    def recommend(self, result: TagResult) -> TagResult:
        priority = self._recommend_priority(result)
        if priority:
            result.recommended_tags.add(priority)

        module = self._recommend_module(result)
        if module:
            result.recommended_tags.add(module)

        scene = self._recommend_scene(result)
        if scene:
            result.recommended_tags.add(scene)

        page_type = self._recommend_page_type(result)
        if page_type:
            result.recommended_tags.add(page_type)

        run = self._recommend_run_strategy(result, priority, scene)
        if run:
            result.recommended_tags.add(run)

        if self.preset_browser:
            result.recommended_tags.add(f"browser:{self.preset_browser}")
        if self.preset_platform:
            result.recommended_tags.add(f"platform:{self.preset_platform}")

        all_tags = result.existing_tags | result.recommended_tags
        result.conflicts = self._detect_conflicts(all_tags)
        result.missing_tags = self._detect_missing_tags(all_tags)
        return result

    def _recommend_priority(self, result: TagResult) -> Optional[str]:
        for p in ["P0", "P1", "P2", "P3"]:
            if p in result.existing_tags:
                return None

        if result.yaml_priority in ["P0", "P1", "P2", "P3"]:
            return result.yaml_priority

        for url in result.goto_urls:
            url_lower = url.lower()
            for pattern in CORE_PATH_PATTERNS:
                if re.search(pattern, url_lower):
                    return "P0"

        combined = f"{result.method_name} {result.docstring}".lower()
        if any(kw in combined for kw in ["login", "signin", "register", "signup",
                                         "checkout", "full_shopping", "place_order",
                                         "complete_order", "submit_order"]):
            return "P0"
        if any(kw in combined for kw in ["update", "modify", "change", "search",
                                         "list", "browse", "view", "filter"]):
            return "P1"
        if any(kw in combined for kw in ["admin", "config", "stats", "statistics",
                                         "dashboard", "setting"]):
            return "P2"
        if any(kw in combined for kw in ["visual", "regress", "responsive", "edge_case"]):
            return "P3"

        return "P1"

    def _recommend_module(self, result: TagResult) -> Optional[str]:
        if any(t.startswith("module:") for t in result.existing_tags):
            return None

        if result.yaml_module:
            tag = result.yaml_module if result.yaml_module.startswith("module:") else f"module:{result.yaml_module}"
            return tag

        if result.dir_module:
            return result.dir_module

        for url in result.goto_urls:
            url_lower = url.lower()
            for module_tag, patterns in TAG_SPEC["module"]["path_patterns"].items():
                for pattern in patterns:
                    if pattern in url_lower:
                        return module_tag

        # POM 类名推断（如 LoginPage → module:login，HomePage → module:product）
        for pom_name in result.pom_class_names:
            hint = self._lookup_pom_hint(pom_name)
            if hint:
                return hint[0]

        class_lower = result.class_name.lower()
        for module_tag, keywords in MODULE_KEYWORDS.items():
            if any(kw in class_lower for kw in keywords):
                return module_tag

        return None

    @staticmethod
    def _lookup_pom_hint(pom_name: str) -> Optional[Tuple[str, str]]:
        """从 POM 类名查找 (module, page_type) 提示。

        匹配规则：去掉 Page 后缀后转小写，最长前缀匹配 POM_CLASS_HINTS。
        例：HomePage → home → ("module:product", "page:home")
            ProductDetailPage → productdetail → ("module:product", "page:detail")
        """
        base = pom_name
        for suffix in ("Page", "PageObject"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        key = base.lower()
        # 最长前缀匹配
        best_match = None
        best_len = 0
        for hint_key, hint_val in POM_CLASS_HINTS.items():
            if key.startswith(hint_key) and len(hint_key) > best_len:
                best_match = hint_val
                best_len = len(hint_key)
        return best_match

    def _recommend_scene(self, result: TagResult) -> Optional[str]:
        if any(t.startswith("scene:") for t in result.existing_tags):
            return None

        # 按优先级顺序：full_flow > visual_regress > boundary > negative > positive
        for scene_tag in ["scene:full_flow", "scene:visual_regress", "scene:boundary", "scene:negative"]:
            for pattern in TAG_SPEC["scene"]["method_patterns"][scene_tag]:
                if re.search(pattern, result.method_name):
                    return scene_tag

        doc_lower = result.docstring.lower()
        if any(kw in doc_lower for kw in ["全流程", "端到端", "e2e", "full_flow",
                                          "end_to_end", "complete_flow", "业务流"]):
            return "scene:full_flow"
        if any(kw in doc_lower for kw in ["视觉回归", "截图对比", "visual", "screenshot",
                                          "regress", "snapshot", "布局"]):
            return "scene:visual_regress"
        if any(kw in doc_lower for kw in ["边界", "极限", "最大", "最小",
                                          "boundary", "limit", "overflow"]):
            return "scene:boundary"
        if any(kw in doc_lower for kw in ["异常", "错误", "失败", "invalid",
                                          "error", "fail", "exception"]):
            return "scene:negative"

        for pattern in TAG_SPEC["scene"]["method_patterns"]["scene:positive"]:
            if re.search(pattern, result.method_name):
                return "scene:positive"

        return "scene:positive"

    def _recommend_page_type(self, result: TagResult) -> Optional[str]:
        if any(t.startswith("page:") for t in result.existing_tags):
            return None

        if result.yaml_page_type:
            tag = result.yaml_page_type if result.yaml_page_type.startswith("page:") else f"page:{result.yaml_page_type}"
            return tag

        # dialog 优先（操作特征最明确）
        if result.has_dialog:
            return "page:dialog"

        for url in result.goto_urls:
            path = self._extract_path(url)
            if not path:
                continue
            for page_type, patterns in PAGE_TYPE_PATTERNS:
                for pattern in patterns:
                    if re.search(pattern, path, re.IGNORECASE):
                        return page_type

        # POM 类名推断（如 LoginPage → page:form，HomePage → page:home）
        for pom_name in result.pom_class_names:
            hint = self._lookup_pom_hint(pom_name)
            if hint:
                return hint[1]

        return "page:list"

    @staticmethod
    def _extract_path(url: str) -> str:
        url = url.strip()
        if url.startswith(("http://", "https://")):
            try:
                return urlparse(url).path or ""
            except Exception:
                return ""
        if url.startswith("/"):
            return url
        return ""

    def _recommend_run_strategy(self, result: TagResult,
                                priority: Optional[str], scene: Optional[str]) -> Optional[str]:
        if any(t.startswith("run:") for t in result.existing_tags):
            return None

        if not priority:
            for p in ["P0", "P1", "P2", "P3"]:
                if p in result.existing_tags:
                    priority = p
                    break

        if not scene:
            scene = "scene:positive"

        if priority == "P0" and scene in ("scene:positive", "scene:full_flow"):
            return "run:smoke"
        if priority in ["P0", "P1"]:
            return "run:regression"
        return "run:full"

    def _detect_conflicts(self, all_tags: Set[str]) -> List[str]:
        conflicts = []
        for tag1, tag2, message in CONFLICT_RULES:
            if tag1 in all_tags and tag2 in all_tags:
                conflicts.append(message)
        return conflicts

    def _detect_missing_tags(self, all_tags: Set[str]) -> List[str]:
        missing = []
        if not any(t in all_tags for t in ["P0", "P1", "P2", "P3"]):
            missing.append("优先级标签（P0/P1/P2/P3）")
        if not any(t.startswith("module:") for t in all_tags):
            missing.append("模块标签（module:xxx）")
        if not any(t.startswith("scene:") for t in all_tags):
            missing.append("场景标签（scene:xxx）")
        if not any(t.startswith("page:") for t in all_tags):
            missing.append("页面类型标签（page:xxx）")
        if not any(t.startswith("run:") for t in all_tags):
            missing.append("执行策略标签（run:xxx）")
        return missing


# ============================================================
# 标签写入
# ============================================================

class TagWriter:
    def __init__(self, script_dir: str, dry_run: bool = False):
        self.script_dir = Path(script_dir)
        self.dry_run = dry_run
        self.replaced_marks = 0
        self.added_marks = 0

    def write_tags(self, results: List[TagResult]) -> int:
        file_results: Dict[str, List[TagResult]] = defaultdict(list)
        for r in results:
            file_results[r.file_path].append(r)

        modified_count = 0
        for rel_path, method_results in file_results.items():
            file_path = self.script_dir / rel_path
            if not file_path.exists():
                continue
            if self._write_file_tags(file_path, method_results):
                modified_count += 1
        return modified_count

    def _write_file_tags(self, file_path: Path, method_results: List[TagResult]) -> bool:
        try:
            source = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[ERROR] 读取文件失败 {file_path}: {e}")
            return False

        lines = source.split("\n")
        modified = False

        for result in reversed(method_results):
            new_tags = result.recommended_tags - result.existing_tags
            tags_to_replace = self._find_tags_to_replace(result)

            if not new_tags and not tags_to_replace:
                continue

            method_line_idx = self._find_method_line(lines, result.method_name)
            if method_line_idx is None:
                continue

            if tags_to_replace:
                self._replace_legacy_marks(lines, method_line_idx, tags_to_replace)
                modified = True
                self.replaced_marks += len(tags_to_replace)

            truly_new_tags = set()
            for tag in new_tags:
                if not self._has_equivalent_mark(lines, method_line_idx, tag):
                    truly_new_tags.add(tag)

            if truly_new_tags:
                indent = self._get_method_indent(lines, method_line_idx)
                tag_decorators = self._generate_tag_decorators(truly_new_tags, indent)
                insert_idx = self._find_decorator_insert_point(lines, method_line_idx)

                if self.dry_run:
                    print(f"[DRY-RUN] {file_path.name}::{result.method_name} +{tag_decorators}")
                else:
                    for i, dec in enumerate(tag_decorators):
                        lines.insert(insert_idx + i, dec)
                    modified = True
                    self.added_marks += len(tag_decorators)
            elif tags_to_replace and self.dry_run:
                replacements = [f"{old}→{new}" for old, new in tags_to_replace]
                print(f"[DRY-RUN] {file_path.name}::{result.method_name} 替换: {replacements}")

        if modified and not self.dry_run:
            file_path.write_text("\n".join(lines), encoding="utf-8")
        return modified

    def _find_tags_to_replace(self, result: TagResult) -> List[Tuple[str, str]]:
        replacements = []
        for raw_mark in result.existing_raw_marks:
            attr_name = raw_mark.split(".")[-1] if "." in raw_mark else raw_mark
            if attr_name in LEGACY_MARK_MAP:
                std_tag = LEGACY_MARK_MAP[attr_name]
                std_mark = TAG_TO_MARK.get(std_tag, std_tag)
                if attr_name != std_mark:
                    replacements.append((attr_name, std_mark))
        return replacements

    def _replace_legacy_marks(self, lines, method_line_idx, replacements):
        dec_lines = []
        idx = method_line_idx - 1
        while idx >= 0:
            stripped = lines[idx].strip()
            if stripped.startswith("@"):
                dec_lines.append((idx, stripped))
                idx -= 1
            elif stripped == "":
                idx -= 1
            else:
                break

        for line_idx, line_content in dec_lines:
            for old_mark, new_mark in replacements:
                old_pattern = f"@pytest.mark.{old_mark}"
                new_pattern = f"@pytest.mark.{new_mark}"
                if old_pattern in line_content:
                    lines[line_idx] = line_content.replace(old_pattern, new_pattern)

    def _has_equivalent_mark(self, lines, method_line_idx, tag) -> bool:
        mark_name = TAG_TO_MARK.get(tag, tag)
        std_pattern = f"@pytest.mark.{mark_name}"
        legacy_patterns = []
        for raw, std in LEGACY_MARK_MAP.items():
            if std == tag:
                legacy_patterns.append(f"@pytest.mark.{raw}")

        idx = method_line_idx - 1
        while idx >= 0:
            stripped = lines[idx].strip()
            if stripped.startswith("@"):
                if std_pattern in stripped:
                    return True
                for lp in legacy_patterns:
                    if lp in stripped:
                        return True
                idx -= 1
            elif stripped == "":
                idx -= 1
            else:
                break
        return False

    def _find_method_line(self, lines, method_name):
        for i, line in enumerate(lines):
            if re.match(rf"\s*(async\s+)?def\s+{re.escape(method_name)}\s*\(", line):
                return i
        return None

    def _find_decorator_insert_point(self, lines, method_line_idx):
        idx = method_line_idx
        while idx > 0:
            prev_line = lines[idx - 1].strip()
            if prev_line.startswith("@"):
                idx -= 1
            elif prev_line == "":
                if idx >= 2 and lines[idx - 2].strip().startswith("@"):
                    idx -= 1
                else:
                    break
            else:
                break
        return idx

    def _generate_tag_decorators(self, tags, indent=""):
        decorators = []
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        category_order = {"module:": 6, "scene:": 7, "page:": 8, "run:": 9,
                          "browser:": 10, "platform:": 11}

        def sort_key(t):
            if ":" not in t:
                return (order.get(t, 5), "")
            prefix = t.split(":")[0] + ":"
            return (category_order.get(prefix, 12), t)

        sorted_tags = sorted(tags, key=sort_key)
        for tag in sorted_tags:
            mark_name = TAG_TO_MARK.get(tag, tag.replace(":", "_"))
            decorators.append(f"{indent}@pytest.mark.{mark_name}")
        return decorators

    def _get_method_indent(self, lines, method_line_idx):
        line = lines[method_line_idx]
        indent = ""
        for ch in line:
            if ch in (" ", "\t"):
                indent += ch
            else:
                break
        return indent


# ============================================================
# 统计报告生成
# ============================================================

class StatisticsReporter:
    def __init__(self, results: List[TagResult]):
        self.results = results
        self.stats = TagStatistics()

    def generate(self) -> TagStatistics:
        self._count_distribution()
        self._find_missing()
        self._find_coverage_gaps()
        return self.stats

    def _count_distribution(self):
        classes_seen = set()
        for r in self.results:
            self.stats.total_methods += 1
            classes_seen.add(f"{r.file_path}::{r.class_name}")
            all_tags = r.existing_tags | r.recommended_tags
            for tag in all_tags:
                if tag in ["P0", "P1", "P2", "P3"]:
                    self.stats.tag_distribution["priority"][tag] += 1
                elif tag.startswith("module:"):
                    self.stats.tag_distribution["module"][tag] += 1
                elif tag.startswith("scene:"):
                    self.stats.tag_distribution["scene"][tag] += 1
                elif tag.startswith("page:"):
                    self.stats.tag_distribution["page"][tag] += 1
                elif tag.startswith("run:"):
                    self.stats.tag_distribution["run"][tag] += 1
                elif tag.startswith("browser:"):
                    self.stats.tag_distribution["browser"][tag] += 1
                elif tag.startswith("platform:"):
                    self.stats.tag_distribution["platform"][tag] += 1
            if r.conflicts:
                self.stats.conflict_count += 1
        self.stats.total_classes = len(classes_seen)

    def _find_missing(self):
        for r in self.results:
            if r.missing_tags:
                self.stats.missing_tag_methods.append({
                    "file": r.file_path,
                    "class": r.class_name,
                    "method": r.method_name,
                    "missing": r.missing_tags,
                })

    def _find_coverage_gaps(self):
        for category, distribution in self.stats.tag_distribution.items():
            spec_values = TAG_SPEC.get(category, {}).get("values", [])
            for val in spec_values:
                if distribution.get(val, 0) == 0:
                    self.stats.coverage_gaps.append(f"{category} 维度缺失: {val}")

    def format_report(self) -> str:
        lines = []
        lines.append("# UI 测试标签分布统计报告")
        lines.append("")
        lines.append("## 概览")
        lines.append(f"- 测试类总数: {self.stats.total_classes}")
        lines.append(f"- 测试方法总数: {self.stats.total_methods}")
        lines.append(f"- 测试文件数: {self.stats.total_files}")
        lines.append(f"- 标签冲突方法数: {self.stats.conflict_count}")
        lines.append(f"- 缺失标签方法数: {len(self.stats.missing_tag_methods)}")
        lines.append("")

        category_names = {
            "priority": "优先级分布",
            "module": "模块分布",
            "scene": "场景分布",
            "page": "页面类型分布",
            "run": "执行策略分布",
            "browser": "浏览器分布",
            "platform": "平台分布",
        }

        for category in ["priority", "module", "scene", "page", "run", "browser", "platform"]:
            dist = self.stats.tag_distribution.get(category, {})
            if not dist:
                continue
            lines.append(f"## {category_names.get(category, category)}")
            lines.append("")
            lines.append("| 标签 | 数量 | 占比 |")
            lines.append("|------|------|------|")
            total = sum(dist.values())
            for tag in sorted(dist.keys()):
                count = dist[tag]
                pct = f"{count / total * 100:.1f}%" if total > 0 else "0%"
                lines.append(f"| {tag} | {count} | {pct} |")
            lines.append("")

        if self.stats.conflict_count > 0:
            lines.append("## 标签冲突")
            lines.append("")
            for r in self.results:
                if r.conflicts:
                    lines.append(f"### {r.file_path}::{r.class_name}::{r.method_name}")
                    for c in r.conflicts:
                        lines.append(f"- {c}")
                    lines.append("")

        if self.stats.missing_tag_methods:
            lines.append("## 标签补全建议")
            lines.append("")
            lines.append("| 文件 | 类 | 方法 | 缺失标签 |")
            lines.append("|------|-----|------|----------|")
            for m in self.stats.missing_tag_methods:
                lines.append(f"| {m['file']} | {m['class']} | {m['method']} | {'; '.join(m['missing'])} |")
            lines.append("")

        if self.stats.coverage_gaps:
            lines.append("## 标签覆盖缺口")
            lines.append("")
            for gap in self.stats.coverage_gaps:
                lines.append(f"- {gap}")
            lines.append("")

        lines.append("## 标签使用示例")
        lines.append("")
        lines.append("```bash")
        lines.append("# 冒烟测试（P0 + 正向场景）")
        lines.append("pytest -m 'P0 and scene_positive'")
        lines.append("")
        lines.append("# 回归测试（P0/P1 级别）")
        lines.append("pytest -m 'P0 or P1'")
        lines.append("")
        lines.append("# 登录模块测试")
        lines.append("pytest -m 'module_login'")
        lines.append("")
        lines.append("# 表单页回归测试")
        lines.append("pytest -m 'page_form and run_regression'")
        lines.append("")
        lines.append("# 端到端全流程测试")
        lines.append("pytest -m 'scene_full_flow'")
        lines.append("")
        lines.append("# 视觉回归测试")
        lines.append("pytest -m 'scene_visual_regress'")
        lines.append("")
        lines.append("# 跨浏览器矩阵（Chrome 专用）")
        lines.append("pytest -m 'browser_chrome'")
        lines.append("")
        lines.append("# 异常场景测试")
        lines.append("pytest -m 'scene_negative'")
        lines.append("```")

        return "\n".join(lines)


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="UI 测试脚本智能标签分析器")
    parser.add_argument("script_dir", help="UI 测试脚本目录")
    parser.add_argument("--pages-yaml", help="pages.yaml 路径（可选）")
    parser.add_argument("--dry-run", action="store_true", help="仅分析不写入")
    parser.add_argument("--output", default="ui_tag_statistics.md", help="统计报告输出路径")
    parser.add_argument("--no-write", action="store_true", help="不写入标签到脚本")
    parser.add_argument("--browser", help="预设浏览器标签（chrome/firefox/edge/safari/headless）")
    parser.add_argument("--platform", help="预设平台标签（windows/linux/mac）")

    args = parser.parse_args()

    if not os.path.isdir(args.script_dir):
        print(f"[ERROR] 目录不存在: {args.script_dir}")
        sys.exit(1)

    print(f"[INFO] 解析目录: {args.script_dir}")

    pages_loader = PagesYamlLoader()
    if args.pages_yaml:
        pages_loader.load(args.pages_yaml)

    parser_instance = UITestScriptParser(args.script_dir, pages_loader)
    results = parser_instance.parse_all()
    print(f"[INFO] 解析完成: {len(results)} 个测试方法, {len(parser_instance.file_set)} 个文件")

    if not results:
        print("[WARN] 未发现测试方法")
        sys.exit(0)

    recommender = TagRecommender(pages_loader, args.browser, args.platform)
    for r in results:
        recommender.recommend(r)

    conflict_count = sum(1 for r in results if r.conflicts)
    print(f"[INFO] 标签冲突: {conflict_count} 个方法")

    if not args.no_write and not args.dry_run:
        writer = TagWriter(args.script_dir, dry_run=False)
        modified = writer.write_tags(results)
        print(f"[INFO] 修改文件: {modified} 个")
        print(f"[INFO] 替换旧标记: {writer.replaced_marks} 个, 新增标记: {writer.added_marks} 个")
    elif args.dry_run:
        writer = TagWriter(args.script_dir, dry_run=True)
        writer.write_tags(results)
        print("[INFO] dry-run 模式，未实际写入")

    reporter = StatisticsReporter(results)
    stats = reporter.generate()
    stats.total_files = len(parser_instance.file_set)
    report = reporter.format_report()

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[INFO] 统计报告已生成: {args.output}")

    print(f"\n{'='*60}")
    print(f"摘要: {stats.total_methods} 方法 | {stats.total_classes} 类 | {stats.total_files} 文件 | {conflict_count} 冲突 | {len(stats.missing_tag_methods)} 缺失标签")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
