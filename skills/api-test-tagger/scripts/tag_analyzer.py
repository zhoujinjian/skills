#!/usr/bin/env python3
"""
API测试脚本智能标签分析器 v2
功能：解析测试脚本 → 智能标签推荐 → 冲突检测 → 标签写入 → 统计报告

v2 修复：
- 装饰器标签使用下划线格式（module:auth → module_auth）
- 识别已有的小写标记（p0→P0, p1→P1, p2→P2, smoke→run_smoke）
- 扩展模块映射（captcha→auth, search→product, banner→product, payment→order）
- 支持替换旧标记为标准化标记
- 优化业务流测试优先级判定
"""

import ast
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ============================================================
# 标签规范定义
# ============================================================

TAG_SPEC = {
    "priority": {
        "prefix": "",
        "values": ["P0", "P1", "P2", "P3"],
        "description": {
            "P0": "核心链路（登录、下单、支付等关键路径）",
            "P1": "重要功能（主要业务流程的非核心分支）",
            "P2": "一般功能（辅助功能、配置管理）",
            "P3": "边缘场景（罕见操作、极端异常）",
        },
    },
    "module": {
        "prefix": "module:",
        "values": [
            "module:auth", "module:order", "module:product",
            "module:cart", "module:user", "module:address",
            "module:payment", "module:admin",
        ],
        "path_patterns": {
            "module:auth": ["/api/auth", "/api/login", "/api/register", "/api/token", "/api/logout", "/api/captcha"],
            "module:order": ["/api/order", "/api/orders", "/api/payment", "/api/pay"],
            "module:product": ["/api/product", "/api/products", "/api/category", "/api/categories", "/api/search", "/api/banner"],
            "module:cart": ["/api/cart"],
            "module:user": ["/api/user", "/api/users", "/api/profile", "/api/account"],
            "module:address": ["/api/address", "/api/addresses"],
            "module:payment": ["/api/payment", "/api/pay", "/api/refund"],
            "module:admin": ["/api/admin", "/api/dashboard", "/api/config", "/api/stats", "/api/statistics"],
        },
    },
    "scene": {
        "prefix": "scene:",
        "values": ["scene:positive", "scene:negative", "scene:boundary", "scene:security"],
        "method_patterns": {
            "scene:positive": [
                r"(?i)(success|valid|normal|correct|happy|ok|pass|duplicate|consistent|with_captcha|with_slider|image_type)",
            ],
            "scene:negative": [
                r"(?i)(error|invalid|fail|exception|not_found|unauthorized|forbidden|conflict|bad_request|reject|denied|missing|empty|null|none|wrong|nonexistent|no_param|no_auth|no_cart|no_address|empty_)",
            ],
            "scene:boundary": [
                r"(?i)(boundary|limit|min|max|edge|overflow|underflow|extreme|threshold|zero|empty_string|too_long|too_short|max_length|min_length|oversized|already_|expired|unshipped|not_shipped|cancelled|paid_order)",
            ],
            "scene:security": [
                r"(?i)(sql|xss|inject|attack|csrf|auth_bypass|privilege|escalat|malicious|sanitiz|escape|hijack|token_exp|expired_token|forged|special_chars|no_auth|no_token|buffer)",
            ],
        },
    },
    "run": {
        "prefix": "run:",
        "values": ["run:smoke", "run:regression", "run:full"],
        "rules": {
            "run:smoke": "P0 + scene:positive → run:smoke",
            "run:regression": "P0 or P1 → run:regression",
            "run:full": "所有用例默认 run:full",
        },
    },
    "env": {
        "prefix": "env:",
        "values": ["env:dev", "env:test", "env:pre", "env:prod"],
    },
}

# 已有标记到标准标签的映射
LEGACY_MARK_MAP = {
    "p0": "P0",
    "p1": "P1",
    "p2": "P2",
    "p3": "P3",
    "smoke": "run:smoke",
    "regression": "run:regression",
}

# 标准标签到装饰器名的映射（含冒号→下划线）
TAG_TO_MARK = {
    "P0": "P0",
    "P1": "P1",
    "P2": "P2",
    "P3": "P3",
    "module:auth": "module_auth",
    "module:order": "module_order",
    "module:product": "module_product",
    "module:cart": "module_cart",
    "module:user": "module_user",
    "module:address": "module_address",
    "module:payment": "module_payment",
    "module:admin": "module_admin",
    "scene:positive": "scene_positive",
    "scene:negative": "scene_negative",
    "scene:boundary": "scene_boundary",
    "scene:security": "scene_security",
    "run:smoke": "run_smoke",
    "run:regression": "run_regression",
    "run:full": "run_full",
    "env:dev": "env_dev",
    "env:test": "env_test",
    "env:pre": "env_pre",
    "env:prod": "env_prod",
}

# 目录到模块的映射（扩展）
DIR_MODULE_MAP = {
    "auth": "module:auth",
    "order": "module:order",
    "product": "module:product",
    "cart": "module:cart",
    "user": "module:user",
    "address": "module:address",
    "payment": "module:payment",
    "admin": "module:admin",
    "captcha": "module:auth",
    "search": "module:product",
    "banner": "module:product",
}

# 冲突检测规则
CONFLICT_RULES = [
    ("P0", "P3", "优先级冲突：同一方法不应同时标记为最高优先级(P0)和最低优先级(P3)"),
    ("P0", "P2", "优先级冲突：P0核心链路与P2一般功能标记冲突"),
    ("P1", "P3", "优先级冲突：P1重要功能与P3边缘场景标记冲突"),
    ("scene:positive", "scene:negative", "场景冲突：同一方法不应同时为正向和异常场景"),
    ("scene:positive", "scene:boundary", "场景冲突：正向和边界场景不应共存于同一方法"),
    ("run:smoke", "P3", "执行策略冲突：冒烟用例不应标记为P3边缘场景"),
    ("run:smoke", "scene:negative", "执行策略冲突：冒烟用例通常不包含异常场景"),
]

# 核心链路路径模式（用于P0判断）
CORE_PATH_PATTERNS = [
    r"/api/auth/login",
    r"/api/auth/register",
    r"/api/order",
    r"/api/order/create",
    r"/api/order/submit",
    r"/api/payment/pay",
    r"/api/payment/checkout",
    r"/api/cart/add",
    r"/api/cart/checkout",
]


@dataclass
class TagResult:
    """单个测试方法的标签分析结果"""
    file_path: str
    class_name: str
    method_name: str
    docstring: str = ""
    existing_tags: Set[str] = field(default_factory=set)
    existing_raw_marks: Set[str] = field(default_factory=set)  # 原始装饰器名
    recommended_tags: Set[str] = field(default_factory=set)
    conflicts: List[str] = field(default_factory=list)
    missing_tags: List[str] = field(default_factory=list)
    request_url: str = ""
    request_method: str = ""
    dir_module: str = ""  # 目录推断的模块


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
    replaced_marks: int = 0  # 替换的旧标记数
    added_marks: int = 0  # 新增的标记数


# ============================================================
# 脚本语义解析
# ============================================================

class TestScriptParser:
    """解析Python测试脚本，提取测试类和测试方法信息"""

    def __init__(self, script_dir: str, api_definitions_path: str = None):
        self.script_dir = Path(script_dir)
        self.api_definitions = self._load_api_definitions(api_definitions_path) if api_definitions_path else {}
        self.results: List[TagResult] = []
        self.file_set: Set[str] = set()

    def _load_api_definitions(self, path: str) -> Dict:
        """加载API定义文件"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] 加载API定义文件失败: {e}")
            return {}

    def parse_all(self) -> List[TagResult]:
        """解析目录下所有测试脚本"""
        test_files = list(self.script_dir.rglob("test_*.py")) + list(self.script_dir.rglob("*_test.py"))
        for tf in test_files:
            self._parse_file(tf)
        return self.results

    def _parse_file(self, file_path: Path):
        """解析单个测试文件"""
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception as e:
            print(f"[ERROR] 解析文件失败 {file_path}: {e}")
            return

        rel_path = str(file_path.relative_to(self.script_dir))
        self.file_set.add(rel_path)

        # 从文件路径推断模块
        dir_module = self._infer_module_from_path(rel_path)

        # 提取文件级docstring中的接口路径
        file_docstring = ast.get_docstring(tree) or ""

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                class_docstring = ast.get_docstring(node) or ""
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_"):
                        result = self._extract_method_info(rel_path, node.name, item, class_docstring, file_docstring, dir_module)
                        self.results.append(result)

    def _infer_module_from_path(self, rel_path: str) -> str:
        """从文件路径推断模块"""
        parts = Path(rel_path).parts
        for part in parts:
            if part in DIR_MODULE_MAP:
                return DIR_MODULE_MAP[part]
        return ""

    def _extract_method_info(self, file_path: str, class_name: str,
                              method_node: ast.FunctionDef, class_docstring: str,
                              file_docstring: str, dir_module: str) -> TagResult:
        """提取测试方法信息"""
        method_docstring = ast.get_docstring(method_node) or ""
        existing_tags, existing_raw_marks = self._extract_existing_tags(method_node)
        request_url, request_method = self._extract_request_info(method_node)
        # 场景判断只用类+方法docstring，不用文件docstring（避免"安全风险"等通用描述污染）
        combined_docstring = f"{class_docstring}\n{method_docstring}"
        # 优先级判断可以用文件docstring（含接口路径信息）
        priority_docstring = f"{file_docstring}\n{class_docstring}\n{method_docstring}"

        return TagResult(
            file_path=file_path,
            class_name=class_name,
            method_name=method_node.name,
            docstring=combined_docstring,
            existing_tags=existing_tags,
            existing_raw_marks=existing_raw_marks,
            request_url=request_url,
            request_method=request_method,
            dir_module=dir_module,
        )

    def _extract_existing_tags(self, method_node: ast.FunctionDef) -> Tuple[Set[str], Set[str]]:
        """提取已有的pytest标记和docstring标签，返回（标准化标签，原始装饰器名）"""
        tags = set()
        raw_marks = set()

        # 提取 @pytest.mark.xxx 装饰器
        for decorator in method_node.decorator_list:
            tag, raw = self._parse_decorator_tag(decorator)
            if tag:
                tags.add(tag)
            if raw:
                raw_marks.add(raw)

        # 提取 docstring 中的 Tags: 行
        docstring = ast.get_docstring(method_node) or ""
        tags_match = re.search(r"Tags:\s*(.+)", docstring)
        if tags_match:
            for t in tags_match.group(1).split(","):
                t = t.strip()
                if t:
                    # 标准化
                    std_tag = LEGACY_MARK_MAP.get(t, t)
                    tags.add(std_tag)

        return tags, raw_marks

    def _parse_decorator_tag(self, decorator) -> Tuple[Optional[str], Optional[str]]:
        """解析装饰器标签，返回（标准化标签，原始标记名）"""
        raw = None
        attr_name = None

        if isinstance(decorator, ast.Attribute):
            # pytest.mark.xxx
            if (isinstance(decorator.value, ast.Attribute) and
                decorator.value.attr == "mark" and
                isinstance(decorator.value.value, ast.Name) and
                decorator.value.value.id == "pytest"):
                attr_name = decorator.attr
                raw = f"pytest.mark.{attr_name}"
        elif isinstance(decorator, ast.Call):
            # @pytest.mark.xxx(...)
            if isinstance(decorator.func, ast.Attribute):
                tag, r = self._parse_decorator_tag(decorator.func)
                return tag, r
        elif isinstance(decorator, ast.Name):
            attr_name = decorator.id
            raw = attr_name

        if attr_name:
            # 标准化：将小写标记映射为标准标签
            std_tag = LEGACY_MARK_MAP.get(attr_name, attr_name)
            return std_tag, raw

        return None, None

    def _extract_request_info(self, method_node: ast.FunctionDef) -> Tuple[str, str]:
        """从方法体和文件docstring中提取请求URL和HTTP方法"""
        request_url = ""
        request_method = ""

        # 从方法体中提取
        for node in ast.walk(method_node):
            if isinstance(node, ast.Call):
                url, method = self._parse_request_call(node)
                if url:
                    request_url = url
                    request_method = method

        return request_url, request_method

    def _parse_request_call(self, call_node: ast.Call) -> Tuple[str, str]:
        """解析requests调用"""
        http_methods = {"get", "post", "put", "delete", "patch", "head", "options"}
        method = ""

        if isinstance(call_node.func, ast.Attribute):
            attr = call_node.func.attr
            if attr in http_methods:
                method = attr.upper()
            elif attr == "request":
                if call_node.args and isinstance(call_node.args[0], ast.Constant):
                    method = call_node.args[0].value.upper()

            url = ""
            args = call_node.args
            if attr in http_methods and len(args) >= 1:
                url = self._extract_string_value(args[0])
            elif attr == "request" and len(args) >= 2:
                url = self._extract_string_value(args[1])
            else:
                for kw in call_node.keywords:
                    if kw.arg == "url":
                        url = self._extract_string_value(kw.value)
                        break

            return url, method

        return "", ""

    def _extract_string_value(self, node) -> str:
        """从AST节点提取字符串值"""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts = []
            for val in node.values:
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    parts.append(val.value)
            return "".join(parts)
        return ""


# ============================================================
# 智能标签推荐
# ============================================================

class TagRecommender:
    """基于脚本语义和接口定义，自动推荐标准化标签"""

    def __init__(self, api_definitions: Dict = None):
        self.api_definitions = api_definitions or {}

    def recommend(self, result: TagResult) -> TagResult:
        """为单个测试方法推荐标签"""
        # 优先级标签
        priority_tag = self._recommend_priority(result)
        if priority_tag:
            result.recommended_tags.add(priority_tag)

        # 模块标签
        module_tag = self._recommend_module(result)
        if module_tag:
            result.recommended_tags.add(module_tag)

        # 场景标签
        scene_tag = self._recommend_scene(result)
        if scene_tag:
            result.recommended_tags.add(scene_tag)

        # 执行策略标签
        run_tag = self._recommend_run_strategy(result, priority_tag, scene_tag)
        if run_tag:
            result.recommended_tags.add(run_tag)

        # 冲突检测（基于合并后的所有标签）
        all_tags = result.existing_tags | result.recommended_tags
        result.conflicts = self._detect_conflicts(all_tags)

        # 缺失标签检测
        result.missing_tags = self._detect_missing_tags(all_tags)

        return result

    def _recommend_priority(self, result: TagResult) -> Optional[str]:
        """推荐优先级标签"""
        # 先检查已有优先级（包括标准化后的）
        for p in ["P0", "P1", "P2", "P3"]:
            if p in result.existing_tags:
                return None  # 已有优先级，不覆盖

        # 基于文件docstring中的接口路径判断
        docstring_lower = result.docstring.lower()
        for pattern in CORE_PATH_PATTERNS:
            if re.search(pattern, docstring_lower):
                return "P0"

        # 基于API路径判断
        url = result.request_url.lower()
        for pattern in CORE_PATH_PATTERNS:
            if re.search(pattern, url):
                return "P0"

        # 基于API定义文件中的标记
        api_key = f"{result.request_method} {result.request_url}"
        if api_key in self.api_definitions:
            api_info = self.api_definitions[api_key]
            if isinstance(api_info, dict):
                priority = api_info.get("priority", api_info.get("level", ""))
                if priority in ["P0", "P1", "P2", "P3"]:
                    return priority

        # 基于方法名和docstring推断
        combined = f"{result.method_name} {result.docstring}".lower()
        if any(kw in combined for kw in ["login", "register", "create_order", "pay", "checkout", "full_shopping_flow", "order_cancel_flow"]):
            return "P0"
        if any(kw in combined for kw in ["update", "modify", "change", "search", "list"]):
            return "P1"
        if any(kw in combined for kw in ["admin", "config", "stats", "statistics", "dashboard"]):
            return "P2"

        # 默认P1
        return "P1"

    def _recommend_module(self, result: TagResult) -> Optional[str]:
        """推荐模块标签"""
        # 先检查已有模块标签
        if any(t.startswith("module:") for t in result.existing_tags):
            return None

        # 基于目录推断（最可靠）
        if result.dir_module:
            return result.dir_module

        # 基于URL路径匹配
        url = result.request_url.lower()
        for module_tag, patterns in TAG_SPEC["module"]["path_patterns"].items():
            for pattern in patterns:
                if pattern in url:
                    return module_tag

        # 基于类名推断
        class_lower = result.class_name.lower()
        module_keywords = {
            "module:auth": ["auth", "login", "register", "token", "captcha"],
            "module:order": ["order"],
            "module:product": ["product", "goods", "item", "catalog", "search", "banner"],
            "module:cart": ["cart", "basket", "shopping"],
            "module:user": ["user", "profile", "account"],
            "module:address": ["address", "location", "shipping"],
            "module:payment": ["payment", "pay", "checkout", "refund", "transaction"],
            "module:admin": ["admin", "manage", "config", "dashboard"],
        }
        for module_tag, keywords in module_keywords.items():
            if any(kw in class_lower for kw in keywords):
                return module_tag

        return None

    def _recommend_scene(self, result: TagResult) -> Optional[str]:
        """推荐场景标签"""
        # 先检查已有场景标签
        if any(t.startswith("scene:") for t in result.existing_tags):
            return None

        # 按优先级检查：security > boundary > negative > positive
        # 先检查更高优先级的场景类型，避免 positive 的子串误匹配

        # 1. 基于方法名模式匹配（security 优先）
        for scene_tag in ["scene:security", "scene:boundary", "scene:negative"]:
            for pattern in TAG_SPEC["scene"]["method_patterns"][scene_tag]:
                if re.search(pattern, result.method_name):
                    return scene_tag

        # 2. 基于类名推断场景（negative/boundary/security 优先）
        class_lower = result.class_name.lower()
        if any(kw in class_lower for kw in ["security", "inject", "xss"]):
            return "scene:security"
        if any(kw in class_lower for kw in ["boundary", "limit"]):
            return "scene:boundary"
        if any(kw in class_lower for kw in ["required", "exception", "error", "negative", "param_validity", "validity"]):
            return "scene:negative"

        # 3. 基于docstring推断（negative/boundary/security 优先）
        doc_lower = result.docstring.lower()
        if any(kw in doc_lower for kw in ["注入", "攻击", "安全风险", "sql", "xss", "inject", "attack", "security"]):
            return "scene:security"
        if any(kw in doc_lower for kw in ["边界值", "边界", "极限", "最大", "最小", "boundary", "limit", "max", "min"]):
            return "scene:boundary"
        if any(kw in doc_lower for kw in ["异常", "错误", "失败", "必填校验", "invalid", "error", "fail", "exception"]):
            return "scene:negative"

        # 4. 最后匹配 positive（使用词边界避免子串误匹配）
        positive_patterns = [
            r"(?i)\b(success|valid|normal|correct|happy|ok|pass|duplicate|consistent|with_captcha|with_slider|image_type)\b",
        ]
        for pattern in positive_patterns:
            if re.search(pattern, result.method_name):
                return "scene:positive"

        # 5. 基于类名推断 positive
        if any(kw in class_lower for kw in ["positive", "normal"]):
            return "scene:positive"

        # 默认正向场景
        return "scene:positive"

    def _recommend_run_strategy(self, result: TagResult,
                                 priority: Optional[str], scene: Optional[str]) -> Optional[str]:
        """推荐执行策略标签"""
        # 先检查已有执行策略标签（包括标准化后的）
        if any(t.startswith("run:") for t in result.existing_tags):
            return None

        # 如果已有优先级标签，基于优先级判断
        if not priority:
            # 使用已有优先级
            for p in ["P0", "P1", "P2", "P3"]:
                if p in result.existing_tags:
                    priority = p
                    break

        if not scene:
            scene = "scene:positive"  # 默认

        # P0 + 正向 → smoke
        if priority == "P0" and scene == "scene:positive":
            return "run:smoke"
        # P0/P1 → regression
        if priority in ["P0", "P1"]:
            return "run:regression"
        # 其余 → full
        return "run:full"

    def _detect_conflicts(self, all_tags: Set[str]) -> List[str]:
        """检测标签冲突"""
        conflicts = []
        for tag1, tag2, message in CONFLICT_RULES:
            if tag1 in all_tags and tag2 in all_tags:
                conflicts.append(message)
        return conflicts

    def _detect_missing_tags(self, all_tags: Set[str]) -> List[str]:
        """检测缺失的关键标签"""
        missing = []
        if not any(t in all_tags for t in ["P0", "P1", "P2", "P3"]):
            missing.append("优先级标签（P0/P1/P2/P3）")
        if not any(t.startswith("module:") for t in all_tags):
            missing.append("模块标签（module:xxx）")
        if not any(t.startswith("scene:") for t in all_tags):
            missing.append("场景标签（scene:xxx）")
        if not any(t.startswith("run:") for t in all_tags):
            missing.append("执行策略标签（run:xxx）")
        return missing


# ============================================================
# 标签写入
# ============================================================

class TagWriter:
    """将推荐标签写入测试脚本，支持替换旧标记"""

    def __init__(self, script_dir: str, dry_run: bool = False):
        self.script_dir = Path(script_dir)
        self.dry_run = dry_run
        self.replaced_marks = 0
        self.added_marks = 0

    def write_tags(self, results: List[TagResult]) -> int:
        """批量写入标签，返回修改的文件数"""
        # 按文件分组
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
        """为单个文件写入标签"""
        try:
            source = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[ERROR] 读取文件失败 {file_path}: {e}")
            return False

        lines = source.split("\n")
        modified = False

        # 从后往前处理，避免行号偏移
        for result in reversed(method_results):
            new_tags = result.recommended_tags - result.existing_tags
            tags_to_replace = self._find_tags_to_replace(result)

            if not new_tags and not tags_to_replace:
                continue

            # 找到方法定义行
            method_line_idx = self._find_method_line(lines, result.method_name)
            if method_line_idx is None:
                continue

            # 先替换旧标记
            if tags_to_replace:
                self._replace_legacy_marks(lines, method_line_idx, tags_to_replace)
                modified = True
                self.replaced_marks += len(tags_to_replace)

            # 计算真正需要新增的标签（排除已替换的旧标记等效标签）
            truly_new_tags = set()
            for tag in new_tags:
                mark_name = TAG_TO_MARK.get(tag, tag)
                # 检查是否已有等效标记
                if not self._has_equivalent_mark(lines, method_line_idx, tag):
                    truly_new_tags.add(tag)

            if truly_new_tags:
                # 生成标签装饰器（带正确缩进）
                indent = self._get_method_indent(lines, method_line_idx)
                tag_decorators = self._generate_tag_decorators(truly_new_tags, indent)

                # 找到插入位置（在现有装饰器之后）
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
        """找到需要替换的旧标记，返回 [(旧标记, 新标记), ...]"""
        replacements = []
        for raw_mark in result.existing_raw_marks:
            # 检查是否是需要标准化的旧标记
            if raw_mark in LEGACY_MARK_MAP:
                std_tag = LEGACY_MARK_MAP[raw_mark]
                std_mark = TAG_TO_MARK.get(std_tag, std_tag)
                if raw_mark != std_mark:
                    replacements.append((raw_mark, std_mark))
        return replacements

    def _replace_legacy_marks(self, lines: List[str], method_line_idx: int,
                               replacements: List[Tuple[str, str]]):
        """替换方法前的旧标记装饰器"""
        # 找到该方法的所有装饰器行
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

        # 替换旧标记
        for line_idx, line_content in dec_lines:
            for old_mark, new_mark in replacements:
                # 替换 @pytest.mark.p0 → @pytest.mark.P0
                old_pattern = f"@pytest.mark.{old_mark}"
                new_pattern = f"@pytest.mark.{new_mark}"
                if old_pattern in line_content:
                    lines[line_idx] = line_content.replace(old_pattern, new_pattern)

    def _has_equivalent_mark(self, lines: List[str], method_line_idx: int, tag: str) -> bool:
        """检查方法是否已有等效标记"""
        mark_name = TAG_TO_MARK.get(tag, tag)
        # 检查标准标记
        std_pattern = f"@pytest.mark.{mark_name}"
        # 检查旧标记
        for raw, std in LEGACY_MARK_MAP.items():
            if std == tag:
                legacy_pattern = f"@pytest.mark.{raw}"
                # 搜索方法前的装饰器
                idx = method_line_idx - 1
                while idx >= 0:
                    stripped = lines[idx].strip()
                    if stripped.startswith("@"):
                        if std_pattern in stripped or legacy_pattern in stripped:
                            return True
                        idx -= 1
                    elif stripped == "":
                        idx -= 1
                    else:
                        break
                break
        return False

    def _find_method_line(self, lines: List[str], method_name: str) -> Optional[int]:
        """找到方法定义行号"""
        for i, line in enumerate(lines):
            if re.match(rf"\s*(async\s+)?def\s+{re.escape(method_name)}\s*\(", line):
                return i
        return None

    def _find_decorator_insert_point(self, lines: List[str], method_line_idx: int) -> int:
        """找到装饰器插入位置（在现有装饰器之后、方法定义之前）"""
        idx = method_line_idx
        while idx > 0:
            prev_line = lines[idx - 1].strip()
            if prev_line.startswith("@"):
                idx -= 1
            elif prev_line == "":
                # 检查是否是装饰器之间的空行
                if idx >= 2 and lines[idx - 2].strip().startswith("@"):
                    idx -= 1
                else:
                    break
            else:
                break
        return idx

    def _generate_tag_decorators(self, tags: Set[str], indent: str = "") -> List[str]:
        """生成pytest.mark装饰器，使用下划线格式"""
        decorators = []
        # 按类别排序：优先级 > 模块 > 场景 > 执行策略 > 环境
        order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
        sorted_tags = sorted(tags, key=lambda t: (
            order.get(t, 5) if not ":" in t else
            {"module:": 6, "scene:": 7, "run:": 8, "env:": 9}.get(t.split(":")[0] + ":", 10)
        ))

        for tag in sorted_tags:
            mark_name = TAG_TO_MARK.get(tag, tag.replace(":", "_"))
            decorators.append(f"{indent}@pytest.mark.{mark_name}")

        return decorators

    def _get_method_indent(self, lines: List[str], method_line_idx: int) -> str:
        """获取方法定义行的缩进字符串"""
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
    """生成标签分布统计报告"""

    def __init__(self, results: List[TagResult]):
        self.results = results
        self.stats = TagStatistics()

    def generate(self) -> TagStatistics:
        """生成统计"""
        self._count_distribution()
        self._find_missing()
        self._find_coverage_gaps()
        return self.stats

    def _count_distribution(self):
        """统计标签分布"""
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
                elif tag.startswith("run:"):
                    self.stats.tag_distribution["run"][tag] += 1
                elif tag.startswith("env:"):
                    self.stats.tag_distribution["env"][tag] += 1

            if r.conflicts:
                self.stats.conflict_count += 1

        self.stats.total_classes = len(classes_seen)

    def _find_missing(self):
        """查找缺失标签的方法"""
        for r in self.results:
            if r.missing_tags:
                self.stats.missing_tag_methods.append({
                    "file": r.file_path,
                    "class": r.class_name,
                    "method": r.method_name,
                    "missing": r.missing_tags,
                })

    def _find_coverage_gaps(self):
        """查找标签覆盖缺口"""
        for category, distribution in self.stats.tag_distribution.items():
            spec_values = TAG_SPEC.get(category, {}).get("values", [])
            for val in spec_values:
                if distribution.get(val, 0) == 0:
                    self.stats.coverage_gaps.append(f"{category}维度缺失: {val}")

    def format_report(self) -> str:
        """格式化统计报告"""
        lines = []
        lines.append("# 标签分布统计报告")
        lines.append("")
        lines.append("## 概览")
        lines.append(f"- 测试类总数: {self.stats.total_classes}")
        lines.append(f"- 测试方法总数: {self.stats.total_methods}")
        lines.append(f"- 标签冲突数: {self.stats.conflict_count}")
        lines.append(f"- 缺失标签方法数: {len(self.stats.missing_tag_methods)}")
        lines.append("")

        # 各维度分布
        for category in ["priority", "module", "scene", "run", "env"]:
            dist = self.stats.tag_distribution.get(category, {})
            if not dist:
                continue
            lines.append(f"## {self._category_name(category)}")
            lines.append("")
            lines.append("| 标签 | 数量 | 占比 |")
            lines.append("|------|------|------|")
            total = sum(dist.values())
            for tag in sorted(dist.keys()):
                count = dist[tag]
                pct = f"{count / total * 100:.1f}%" if total > 0 else "0%"
                lines.append(f"| {tag} | {count} | {pct} |")
            lines.append("")

        # 冲突列表
        if self.stats.conflict_count > 0:
            lines.append("## 标签冲突")
            lines.append("")
            for r in self.results:
                if r.conflicts:
                    lines.append(f"### {r.file_path}::{r.class_name}::{r.method_name}")
                    for c in r.conflicts:
                        lines.append(f"- {c}")
                    lines.append("")

        # 缺失标签
        if self.stats.missing_tag_methods:
            lines.append("## 标签补全建议")
            lines.append("")
            lines.append("| 文件 | 类 | 方法 | 缺失标签 |")
            lines.append("|------|-----|------|----------|")
            for m in self.stats.missing_tag_methods:
                lines.append(f"| {m['file']} | {m['class']} | {m['method']} | {'; '.join(m['missing'])} |")
            lines.append("")

        # 覆盖缺口
        if self.stats.coverage_gaps:
            lines.append("## 标签覆盖缺口")
            lines.append("")
            for gap in self.stats.coverage_gaps:
                lines.append(f"- {gap}")
            lines.append("")

        # 标签使用示例
        lines.append("## 标签使用示例")
        lines.append("")
        lines.append("```bash")
        lines.append("# 冒烟测试（P0 + 正向场景）")
        lines.append("pytest -m 'P0 and scene_positive'")
        lines.append("")
        lines.append("# 回归测试（P0/P1 级别）")
        lines.append("pytest -m 'P0 or P1'")
        lines.append("")
        lines.append("# 订单模块测试")
        lines.append("pytest -m 'module_order'")
        lines.append("")
        lines.append("# 异常场景测试")
        lines.append("pytest -m 'scene_negative'")
        lines.append("")
        lines.append("# 安全测试")
        lines.append("pytest -m 'scene_security'")
        lines.append("```")

        return "\n".join(lines)

    def _category_name(self, category: str) -> str:
        names = {
            "priority": "优先级分布",
            "module": "模块分布",
            "scene": "场景分布",
            "run": "执行策略分布",
            "env": "环境分布",
        }
        return names.get(category, category)


# ============================================================
# 主流程
# ============================================================

def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="API测试脚本智能标签分析器 v2")
    parser.add_argument("script_dir", help="测试脚本目录")
    parser.add_argument("--api-definitions", help="API定义文件路径 (api_definitions.json)")
    parser.add_argument("--dry-run", action="store_true", help="仅分析不写入")
    parser.add_argument("--output", default="tag_statistics.md", help="统计报告输出路径")
    parser.add_argument("--no-write", action="store_true", help="不写入标签到脚本")

    args = parser.parse_args()

    if not os.path.isdir(args.script_dir):
        print(f"[ERROR] 目录不存在: {args.script_dir}")
        sys.exit(1)

    print(f"[INFO] 解析目录: {args.script_dir}")

    # 1. 解析
    parser_instance = TestScriptParser(args.script_dir, args.api_definitions)
    results = parser_instance.parse_all()
    print(f"[INFO] 解析完成: {len(results)} 个测试方法, {len(parser_instance.file_set)} 个文件")

    if not results:
        print("[WARN] 未发现测试方法")
        sys.exit(0)

    # 2. 推荐标签
    recommender = TagRecommender(parser_instance.api_definitions)
    for r in results:
        recommender.recommend(r)

    # 3. 冲突检测
    conflict_count = sum(1 for r in results if r.conflicts)
    print(f"[INFO] 标签冲突: {conflict_count} 个方法")

    # 4. 写入标签
    if not args.no_write and not args.dry_run:
        writer = TagWriter(args.script_dir, dry_run=args.dry_run)
        modified = writer.write_tags(results)
        print(f"[INFO] 修改文件: {modified} 个")
        print(f"[INFO] 替换旧标记: {writer.replaced_marks} 个, 新增标记: {writer.added_marks} 个")
    elif args.dry_run:
        writer = TagWriter(args.script_dir, dry_run=True)
        writer.write_tags(results)
        print("[INFO] dry-run 模式，未实际写入")

    # 5. 生成统计报告
    reporter = StatisticsReporter(results)
    stats = reporter.generate()
    stats.total_files = len(parser_instance.file_set)
    report = reporter.format_report()

    report_path = args.output
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[INFO] 统计报告已生成: {report_path}")

    # 输出摘要
    print(f"\n{'='*60}")
    print(f"摘要: {stats.total_methods} 方法 | {stats.total_classes} 类 | {stats.total_files} 文件 | {conflict_count} 冲突 | {len(stats.missing_tag_methods)} 缺失标签")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
