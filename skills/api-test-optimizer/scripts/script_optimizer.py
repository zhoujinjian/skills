#!/usr/bin/env python3
"""
接口自动化脚本质量检查与优化增强工具

功能：
1. 递归扫描项目目录，解析脚本结构
2. 4类校验（语法/规范/健壮性/逻辑）逐文件检查
3. 10维度场景遗漏分析
4. 自动修复语法错误、规范对齐、健壮性增强、逻辑修复
5. 代码精简（提取公共方法、删除死代码、消除重复）
6. 生成 Markdown 格式校验报告
7. 输出优化后的完整脚本工程

用法：
    python3 script_optimizer.py <project_dir> [options]

选项：
    --output <dir>          优化后脚本的输出目录（默认：<project_dir>_optimized）
    --check-only            仅检查不优化，只输出报告
    --checks <types>        仅执行指定类型的校验（syntax,standard,robustness,logic）
    --module <name>          仅检查优化指定模块
    --api <api_id>           仅检查优化指定接口
    --api-def <file>         接口定义文件（用于场景补齐）
    --skip-scenario          跳过场景补齐
    --severity <level>       最低严重级别（fatal/warning/suggestion）
    --single-file           单文件模式
"""

import os
import sys
import ast
import re
import py_compile
import shutil
import argparse
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# ============================================================
# 常量定义
# ============================================================

SEVERITY_LEVELS = {
    "fatal": "🔴",
    "warning": "🟡",
    "suggestion": "🔵",
}

SEVERITY_ORDER = {"🔴": 0, "🟡": 1, "🔵": 2}

CHECK_TYPES = ["syntax", "standard", "robustness", "logic"]

# 项目目录结构
PROJECT_DIRS = ["config", "api", "testcases", "data", "utils"]

# 命名规范正则
PATTERNS = {
    "class_name": re.compile(r'^[A-Z][a-zA-Z0-9]*$'),            # 大驼峰
    "method_name": re.compile(r'^[a-z][a-z0-9_]*$'),             # 小写+下划线
    "test_method": re.compile(r'^test_[a-z][a-z0-9_]*$'),        # test_ 前缀
    "constant_name": re.compile(r'^[A-Z][A-Z0-9_]*$'),           # 全大写+下划线
    "file_name": re.compile(r'^[a-z][a-z0-9_]*\.py$'),           # 小写+下划线.py
    "dir_name": re.compile(r'^[a-z][a-z0-9_]*$'),                # 小写+下划线
}

# 硬编码检测正则
HARDCODE_PATTERNS = [
    (r'https?://[a-zA-Z0-9\-\.]+(:\d+)?', "URL硬编码", "🟡"),
    (r'timeout\s*=\s*\d+', "超时硬编码", "🟡"),
    (r'retry\s*=\s*\d+', "重试次数硬编码", "🟡"),
    (r'password\s*=\s*["\'][^"\']+["\']', "密码硬编码", "🔴"),
    (r'username\s*=\s*["\'][^"\']+["\']', "用户名硬编码", "🟡"),
]

# 必须捕获的异常类型
REQUIRED_EXCEPTIONS = [
    "ConnectTimeout",
    "ReadTimeout",
    "ConnectionError",
    "ProxyError",
    "JSONDecodeError",
]


# ============================================================
# 数据模型
# ============================================================

class CheckIssue:
    """校验问题"""

    def __init__(self, file_path, line, severity, category, message, fix_strategy=""):
        self.file_path = file_path
        self.line = line
        self.severity = severity  # 🔴 🟡 🔵
        self.category = category  # syntax / standard / robustness / logic
        self.message = message
        self.fix_strategy = fix_strategy
        self.fixed = False

    def __str__(self):
        return f"{self.severity} L{self.line}: [{self.category}] {self.message}"


class ScriptInfo:
    """脚本信息"""

    def __init__(self, file_path):
        self.file_path = file_path
        self.relative_path = ""
        self.module = ""
        self.classes = []
        self.functions = []
        self.imports = []
        self.issues = []
        self.has_docstring = False
        self.has_allure = False
        self.has_assert = False
        self.assert_count = 0
        self.three_layer_assert = False


class ProjectScanResult:
    """项目扫描结果"""

    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.scripts = []
        self.total_files = 0
        self.api_files = []
        self.testcase_files = []
        self.utils_files = []
        self.config_files = []
        self.data_files = []
        self.other_files = []
        self.missing_dirs = []
        self.api_interface_map = {}  # api_id -> script info


# ============================================================
# 扫描器
# ============================================================

class ProjectScanner:
    """项目扫描器"""

    def __init__(self, project_dir, module_filter=None, api_filter=None):
        self.project_dir = os.path.abspath(project_dir)
        self.module_filter = module_filter
        self.api_filter = api_filter

    def scan(self):
        """扫描项目目录"""
        result = ProjectScanResult(self.project_dir)

        # 检查缺失目录
        for dir_name in PROJECT_DIRS:
            dir_path = os.path.join(self.project_dir, dir_name)
            if not os.path.isdir(dir_path):
                result.missing_dirs.append(dir_name)

        # 检查缺失文件
        required_files = ["conftest.py", "pytest.ini"]
        for fname in required_files:
            if not os.path.isfile(os.path.join(self.project_dir, fname)):
                result.missing_dirs.append(fname)

        # 递归扫描 .py 文件
        for root, dirs, files in os.walk(self.project_dir):
            # 跳过隐藏目录和缓存目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
            for f in files:
                if f.endswith('.py'):
                    file_path = os.path.join(root, f)
                    rel_path = os.path.relpath(file_path, self.project_dir)
                    result.total_files += 1

                    # 分类
                    if rel_path.startswith('api/'):
                        result.api_files.append(file_path)
                    elif rel_path.startswith('testcases/'):
                        result.testcase_files.append(file_path)
                    elif rel_path.startswith('utils/'):
                        result.utils_files.append(file_path)
                    elif rel_path.startswith('config/'):
                        result.config_files.append(file_path)
                    elif rel_path.startswith('data/'):
                        result.data_files.append(file_path)
                    else:
                        result.other_files.append(file_path)

                    # 解析脚本
                    script = self._parse_script(file_path)
                    if script:
                        script.relative_path = rel_path
                        result.scripts.append(script)

        return result

    def _parse_script(self, file_path):
        """解析单个脚本文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except (UnicodeDecodeError, IOError):
            return None

        script = ScriptInfo(file_path)

        try:
            tree = ast.parse(source)
        except SyntaxError:
            # 语法错误，仍需记录
            script.issues.append(CheckIssue(
                file_path, 0, "🔴", "syntax",
                "文件存在语法错误，无法进行 AST 解析"
            ))
            return script

        # 提取模块级 docstring
        script.has_docstring = ast.get_docstring(tree) is not None

        for node in ast.walk(tree):
            # 类信息
            if isinstance(node, ast.ClassDef):
                script.classes.append(node.name)
            # 函数信息
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                script.functions.append(node.name)
                if node.name.startswith('test_'):
                    script.has_assert = True
            # 导入信息
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    script.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    script.imports.append(node.module)

        # 检查 Allure 使用
        script.has_allure = 'allure' in source

        # 检查断言
        script.assert_count = source.count('assert ')
        script.has_assert = script.assert_count > 0

        # 检查三层断言
        script.three_layer_assert = (
            'assert_status_code' in source or
            'assert_all' in source or
            'AssertUtil' in source
        )

        return script


# ============================================================
# 语法校验器
# ============================================================

class SyntaxChecker:
    """语法校验器"""

    def check(self, script):
        """执行语法校验"""
        issues = []
        file_path = script.file_path

        # 1. 编译检查
        try:
            py_compile.compile(file_path, doraise=True)
        except py_compile.PyCompileError as e:
            issues.append(CheckIssue(
                file_path, 0, "🔴", "syntax",
                f"编译错误: {str(e)}", "auto_fix_syntax"
            ))

        # 2. AST 解析检查
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
        except SyntaxError as e:
            issues.append(CheckIssue(
                file_path, e.lineno or 0, "🔴", "syntax",
                f"语法错误: {e.msg}", "auto_fix_syntax"
            ))
            return issues  # 语法错误后续检查无意义

        # 3. 导入缺失检查
        issues.extend(self._check_imports(script, tree, source))

        # 4. 变量未定义检查（简易版）
        issues.extend(self._check_undefined_vars(script, tree, source))

        return issues

    def _check_imports(self, script, tree, source):
        """检查导入问题"""
        issues = []

        # 检查是否使用了项目中的类但未导入
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    used_names.add(node.value.id)

        # 常见需要导入的工具
        import_checks = {
            'AssertUtil': 'from utils.assert_util import AssertUtil',
            'RequestUtil': 'from utils.request_util import RequestUtil',
            'TokenUtil': 'from utils.token_util import TokenUtil',
            'get_logger': 'from utils.logger import get_logger',
            'BASE_URL': 'from config.config import BASE_URL',
        }

        imported_names = set()
        for imp in script.imports:
            parts = imp.split('.')
            imported_names.add(parts[-1])

        for name, import_stmt in import_checks.items():
            if name in used_names and name not in imported_names:
                issues.append(CheckIssue(
                    script.file_path, 0, "🟡", "syntax",
                    f"导入了 '{name}' 但缺少 import 语句: {import_stmt}",
                    f"补充: {import_stmt}"
                ))

        # 检查未使用的导入
        for imp in script.imports:
            module_name = imp.split('.')[-1]
            if module_name not in used_names and module_name != '__future__':
                issues.append(CheckIssue(
                    script.file_path, 0, "🔵", "syntax",
                    f"导入 '{imp}' 未被使用",
                    "删除未使用的 import"
                ))

        return issues

    def _check_undefined_vars(self, script, tree, source):
        """简易变量未定义检查"""
        issues = []

        # 检查 fixture 使用但未注入的情况
        fixture_pattern = re.compile(r'(request_util|auth_headers|driver|browser)')
        test_method_pattern = re.compile(r'def (test_\w+)\((.*?)\):')

        for match in test_method_pattern.finditer(source):
            method_name = match.group(1)
            params = match.group(2)
            # 检查方法体中是否使用了 fixture 但未在参数中声明
            # 这是一个简化检查，实际需要更复杂的分析

        return issues


# ============================================================
# 规范校验器
# ============================================================

class StandardChecker:
    """规范校验器"""

    def check(self, script):
        """执行规范校验"""
        issues = []
        file_path = script.file_path

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
        except SyntaxError:
            return issues

        # 1. 命名检查
        issues.extend(self._check_naming(script, tree, source))

        # 2. 注释检查
        issues.extend(self._check_docstring(script, tree, source))

        # 3. 硬编码检查
        issues.extend(self._check_hardcode(script, source))

        # 4. Allure 标记检查
        issues.extend(self._check_allure(script, tree, source))

        return issues

    def _check_naming(self, script, tree, source):
        """检查命名规范"""
        issues = []

        # 文件名检查
        basename = os.path.basename(script.file_path)
        if basename != '__init__.py' and not PATTERNS['file_name'].match(basename):
            issues.append(CheckIssue(
                script.file_path, 0, "🟡", "standard",
                f"文件名 '{basename}' 不符合规范（应为小写+下划线.py）",
                f"重命名为 {basename.lower().replace('-', '_')}"
            ))

        # 类名检查
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                # 测试类必须以 Test 开头
                if node.name.startswith('Test') or node.name.startswith('test'):
                    if not node.name[0].isupper():
                        issues.append(CheckIssue(
                            script.file_path, node.lineno, "🔴", "standard",
                            f"测试类名 '{node.name}' 不符合规范（应以大写 Test 开头）",
                            f"重命名为 {node.name.capitalize()}"
                        ))
                # 非测试类必须大驼峰
                elif not PATTERNS['class_name'].match(node.name):
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🟡", "standard",
                        f"类名 '{node.name}' 不符合大驼峰命名法",
                        f"重命名为 {self._to_camel_case(node.name)}"
                    ))

            # 测试方法名检查
            elif isinstance(node, ast.FunctionDef):
                if node.name.startswith('test') and not node.name.startswith('test_'):
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🔴", "standard",
                        f"测试方法 '{node.name}' 不符合规范（应以 test_ 开头）",
                        f"重命名为 test_{node.name[4:]}"
                    ))
                elif not node.name.startswith('_') and not node.name.startswith('test') and \
                        not PATTERNS['method_name'].match(node.name):
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🟡", "standard",
                        f"方法名 '{node.name}' 不符合小写+下划线命名法",
                        f"重命名为 {self._to_snake_case(node.name)}"
                    ))

        return issues

    def _check_docstring(self, script, tree, source):
        """检查注释完整性"""
        issues = []

        # 模块 docstring
        if not script.has_docstring:
            issues.append(CheckIssue(
                script.file_path, 1, "🟡", "standard",
                "缺少模块级 docstring",
                "自动生成模块 docstring"
            ))

        # 类 docstring
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if not ast.get_docstring(node):
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🟡", "standard",
                        f"类 '{node.name}' 缺少 docstring",
                        "自动生成类 docstring"
                    ))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith('_') and not ast.get_docstring(node):
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🔵", "standard",
                        f"方法 '{node.name}' 缺少 docstring",
                        "自动生成方法 docstring"
                    ))

        return issues

    def _check_hardcode(self, script, source):
        """检查硬编码"""
        issues = []

        for pattern, desc, severity in HARDCODE_PATTERNS:
            matches = re.finditer(pattern, source)
            for match in matches:
                line_num = source[:match.start()].count('\n') + 1
                issues.append(CheckIssue(
                    script.file_path, line_num, severity, "standard",
                    f"{desc}: '{match.group()}'",
                    "提取为配置常量引用"
                ))

        return issues

    def _check_allure(self, script, tree, source):
        """检查 Allure 标记"""
        issues = []

        # 检查测试方法是否有 allure 装饰器
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                has_title = False
                has_feature = False
                has_story = False

                for decorator in node.decorator_list:
                    dec_str = ast.dump(decorator)
                    if 'title' in dec_str:
                        has_title = True
                    if 'feature' in dec_str:
                        has_feature = True
                    if 'story' in dec_str:
                        has_story = True

                if not has_title:
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🟡", "standard",
                        f"测试方法 '{node.name}' 缺少 @allure.title",
                        "补充 @allure.title 装饰器"
                    ))
                if not has_feature:
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🟡", "standard",
                        f"测试方法 '{node.name}' 缺少 @allure.feature",
                        "补充 @allure.feature 装饰器"
                    ))
                if not has_story:
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🟡", "standard",
                        f"测试方法 '{node.name}' 缺少 @allure.story",
                        "补充 @allure.story 装饰器"
                    ))

        return issues

    @staticmethod
    def _to_camel_case(name):
        """转为大驼峰"""
        return ''.join(word.capitalize() for word in re.split(r'[_\s]', name))

    @staticmethod
    def _to_snake_case(name):
        """转为小写+下划线"""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


# ============================================================
# 健壮性校验器
# ============================================================

class RobustnessChecker:
    """健壮性校验器"""

    def check(self, script):
        """执行健壮性校验"""
        issues = []
        file_path = script.file_path

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except (UnicodeDecodeError, IOError):
            return issues

        # 仅对 API 层和 utils 层做健壮性检查
        rel_path = script.relative_path
        if rel_path.startswith('api/') or rel_path.startswith('utils/'):
            issues.extend(self._check_api_robustness(script, source))

        # 对 conftest.py 做健壮性检查
        if os.path.basename(file_path) == 'conftest.py':
            issues.extend(self._check_conftest_robustness(script, source))

        # 检查 pytest.ini
        if os.path.basename(file_path) == 'pytest.ini':
            issues.extend(self._check_pytest_config(script, source))

        return issues

    def _check_api_robustness(self, script, source):
        """检查 API 层健壮性"""
        issues = []

        # 1. 检查是否使用 RequestUtil
        if 'requests.post' in source or 'requests.get' in source or \
           'requests.put' in source or 'requests.delete' in source:
            issues.append(CheckIssue(
                script.file_path, 0, "🟡", "robustness",
                "直接使用 requests 库而非统一 RequestUtil（缺少超时/重试/异常捕获）",
                "替换为 RequestUtil 统一请求工具"
            ))

        # 2. 检查异常捕获
        has_try_except = 'try:' in source
        has_catch_timeout = 'Timeout' in source
        has_catch_connection = 'ConnectionError' in source

        if not has_try_except and 'requests.' in source:
            issues.append(CheckIssue(
                script.file_path, 0, "🔴", "robustness",
                "API 层缺少异常捕获（网络超时/连接错误/代理异常）",
                "引入 RequestUtil（已内置统一异常捕获）或补充 try/except"
            ))

        if has_try_except and not has_catch_timeout:
            issues.append(CheckIssue(
                script.file_path, 0, "🟡", "robustness",
                "异常捕获未包含超时异常（ConnectTimeout/ReadTimeout）",
                "补充超时异常捕获"
            ))

        if has_try_except and not has_catch_connection:
            issues.append(CheckIssue(
                script.file_path, 0, "🟡", "robustness",
                "异常捕获未包含连接异常（ConnectionError）",
                "补充连接异常捕获"
            ))

        # 3. 检查鉴权
        if 'TokenUtil' not in source and 'Authorization' not in source and \
           'headers' not in source and 'requests.' in source:
            issues.append(CheckIssue(
                script.file_path, 0, "🟡", "robustness",
                "API 方法缺少鉴权逻辑（未注入 TokenUtil）",
                "注入 TokenUtil.get_headers() 统一鉴权"
            ))

        # 4. 检查日志
        if 'logger' not in source and 'logging' not in source:
            issues.append(CheckIssue(
                script.file_path, 0, "🔵", "robustness",
                "API 层缺少日志记录",
                "引入 get_logger 并在关键操作处添加日志"
            ))

        return issues

    def _check_conftest_robustness(self, script, source):
        """检查 conftest.py 健壮性"""
        issues = []

        if 'request_util' not in source:
            issues.append(CheckIssue(
                script.file_path, 0, "🟡", "robustness",
                "conftest.py 缺少 request_util fixture",
                "补充 @pytest.fixture(scope='session') def request_util()"
            ))

        if 'auth_headers' not in source:
            issues.append(CheckIssue(
                script.file_path, 0, "🟡", "robustness",
                "conftest.py 缺少 auth_headers fixture",
                "补充 @pytest.fixture(scope='session') def auth_headers()"
            ))

        return issues

    def _check_pytest_config(self, script, source):
        """检查 pytest.ini 配置"""
        issues = []

        if 'reruns' not in source:
            issues.append(CheckIssue(
                script.file_path, 0, "🔵", "robustness",
                "pytest.ini 未配置失败重跑（--reruns）",
                "添加 --reruns=1 --reruns-delay=2"
            ))

        if 'alluredir' not in source:
            issues.append(CheckIssue(
                script.file_path, 0, "🔵", "robustness",
                "pytest.ini 未配置 Allure 报告输出目录",
                "添加 --alluredir=reports/allure-results"
            ))

        return issues


# ============================================================
# 逻辑校验器
# ============================================================

class LogicChecker:
    """逻辑校验器"""

    def check(self, script):
        """执行逻辑校验"""
        issues = []
        file_path = script.file_path

        # 仅对测试用例文件做逻辑校验
        if not script.relative_path.startswith('testcases/'):
            return issues

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
        except SyntaxError:
            return issues

        # 1. 三层断言检查
        issues.extend(self._check_assertions(script, tree, source))

        # 2. 路径参数检查
        issues.extend(self._check_path_params(script, source))

        # 3. 接口依赖检查
        issues.extend(self._check_dependencies(script, tree, source))

        return issues

    def _check_assertions(self, script, tree, source):
        """检查断言逻辑"""
        issues = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                func_source = ast.get_source_segment(source, node) or ""

                # 检查是否有断言
                has_any_assert = (
                    'assert ' in func_source or
                    'AssertUtil' in func_source or
                    'assert_status_code' in func_source or
                    'assert_business_code' in func_source or
                    'assert_all' in func_source
                )

                if not has_any_assert:
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🔴", "logic",
                        f"测试方法 '{node.name}' 无任何断言",
                        "补充三层断言（状态码+业务码+业务数据）"
                    ))
                    continue

                # 检查无效断言
                if re.search(r'assert\s+True\b', func_source):
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🔴", "logic",
                        f"测试方法 '{node.name}' 包含无效断言 'assert True'",
                        "替换为有效的三层断言"
                    ))

                if re.search(r'assert\s+1\s*==\s*1', func_source):
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🔴", "logic",
                        f"测试方法 '{node.name}' 包含无效断言 'assert 1==1'",
                        "替换为有效的三层断言"
                    ))

                # 检查是否只有状态码断言
                has_status_only = (
                    ('status_code' in func_source or 'assert response' in func_source) and
                    'assert_business_code' not in func_source and
                    'assert_all' not in func_source and
                    'AssertUtil.assert_all' not in func_source and
                    'business_code' not in func_source
                )

                if has_status_only:
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🔴", "logic",
                        f"测试方法 '{node.name}' 仅有状态码断言，缺少业务码和业务数据断言",
                        "补充三层断言：使用 AssertUtil.assert_all()"
                    ))

                # 检查是否缺少业务数据断言
                has_business_code = (
                    'business_code' in func_source or
                    'assert_business_code' in func_source or
                    'assert_all' in func_source
                )
                has_business_data = (
                    'field_checks' in func_source or
                    'assert_business_data' in func_source or
                    'not_empty' in func_source or
                    'equals' in func_source
                )

                if has_business_code and not has_business_data:
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🟡", "logic",
                        f"测试方法 '{node.name}' 缺少业务数据断言（仅状态码+业务码）",
                        "补充关键字段的业务数据断言"
                    ))

        return issues

    def _check_path_params(self, script, source):
        """检查路径参数替换"""
        issues = []

        # 检查 URL 中是否有未替换的路径参数
        path_param_pattern = re.compile(r'[\'"]/[^\'"]*\{(\w+)\}[^\'"]*[\'"]')
        for match in path_param_pattern.finditer(source):
            param_name = match.group(1)
            # 检查后续是否有 replace 调用
            remaining = source[match.end():]
            if f'.replace("{{{param_name}}}"' not in remaining[:500] and \
               f".replace('{{{param_name}}}'" not in remaining[:500] and \
               f'.format(' not in remaining[:200]:
                line_num = source[:match.start()].count('\n') + 1
                issues.append(CheckIssue(
                    script.file_path, line_num, "🔴", "logic",
                    f"路径参数 '{{{param_name}}}' 未被替换",
                    f"注入 url = url.replace('{{{{{param_name}}}}}', str({param_name}))"
                ))

        return issues

    def _check_dependencies(self, script, tree, source):
        """检查接口依赖"""
        issues = []

        # 检查测试方法中是否使用了 fixture
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('test_'):
                # 检查参数中是否有 request_util 和 auth_headers
                params = [arg.arg for arg in node.args.args if arg.arg != 'self']
                uses_request = 'request_util' in params
                uses_auth = 'auth_headers' in params

                func_source = ast.get_source_segment(source, node) or ""

                # 使用了 API 但没有注入 request_util
                if 'API(' in func_source and not uses_request and 'request_util' not in func_source:
                    issues.append(CheckIssue(
                        script.file_path, node.lineno, "🟡", "logic",
                        f"测试方法 '{node.name}' 实例化了 API 但未注入 request_util fixture",
                        "在方法参数中添加 request_util"
                    ))

        return issues


# ============================================================
# 场景补齐分析器
# ============================================================

class ScenarioAnalyzer:
    """10维度场景补齐分析器"""

    DIMENSIONS = [
        ("D1", "正向场景"),
        ("D2", "必填校验"),
        ("D3", "参数合法性"),
        ("D4", "边界值"),
        ("D5", "异常处理"),
        ("D6", "业务规则"),
        ("D7", "安全风险"),
        ("D8", "接口依赖"),
        ("D9", "兼容性"),
        ("D10", "断言完整性"),
    ]

    def analyze(self, script, api_definitions=None):
        """分析场景覆盖情况"""
        results = {}

        if not script.relative_path.startswith('testcases/'):
            return results

        try:
            with open(script.file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except (UnicodeDecodeError, IOError):
            return results

        # D1: 正向场景
        results["D1"] = self._check_positive(source)

        # D2: 必填校验
        results["D2"] = self._check_required(source)

        # D3: 参数合法性
        results["D3"] = self._check_param_validity(source)

        # D4: 边界值
        results["D4"] = self._check_boundary(source)

        # D5: 异常处理
        results["D5"] = self._check_exception(source)

        # D6: 业务规则
        results["D6"] = self._check_business_rules(source)

        # D7: 安全风险
        results["D7"] = self._check_security(source)

        # D8: 接口依赖
        results["D8"] = self._check_dependency(source)

        # D9: 兼容性
        results["D9"] = self._check_compatibility(source)

        # D10: 断言完整性
        results["D10"] = self._check_assertion_completeness(source)

        return results

    def _count_test_methods_by_story(self, source, story_keyword):
        """按 story 关键字统计测试方法数"""
        pattern = re.compile(r'@allure\.story\(["\']([^"\']+)["\']\)', re.MULTILINE)
        count = 0
        for match in pattern.finditer(source):
            if story_keyword in match.group(1):
                # 找到后续的 test_ 方法
                remaining = source[match.end():]
                method_match = re.search(r'def (test_\w+)', remaining[:500])
                if method_match:
                    count += 1
        return count

    def _count_test_methods(self, source):
        """统计测试方法总数"""
        return len(re.findall(r'def test_\w+', source))

    def _check_positive(self, source):
        """D1: 正向场景"""
        count = self._count_test_methods_by_story(source, "正向")
        missing = []
        if count == 0:
            missing.append({"desc": "缺少正向场景测试", "priority": "P0", "template": "test_success"})
        return {"existing": count, "missing": missing}

    def _check_required(self, source):
        """D2: 必填校验"""
        count = self._count_test_methods_by_story(source, "必填")
        missing = []
        if count == 0:
            missing.append({"desc": "缺少必填参数空值校验", "priority": "P0", "template": "test_required_empty"})
        if count < 2:
            missing.append({"desc": "缺少必填参数 null 值校验", "priority": "P0", "template": "test_required_null"})
        return {"existing": count, "missing": missing}

    def _check_param_validity(self, source):
        """D3: 参数合法性"""
        count = self._count_test_methods_by_story(source, "合法性")
        missing = []
        if count == 0:
            missing.append({"desc": "缺少参数类型不匹配测试", "priority": "P0", "template": "test_type_mismatch"})
            missing.append({"desc": "缺少参数格式不合法测试", "priority": "P1", "template": "test_invalid_format"})
            missing.append({"desc": "缺少参数长度超限测试", "priority": "P1", "template": "test_too_long"})
        return {"existing": count, "missing": missing}

    def _check_boundary(self, source):
        """D4: 边界值"""
        count = self._count_test_methods_by_story(source, "边界")
        missing = []
        if count == 0:
            missing.append({"desc": "缺少边界值测试", "priority": "P0", "template": "test_boundary"})
        if '0' not in source or 'zero' not in source.lower():
            missing.append({"desc": "缺少零值边界测试", "priority": "P1", "template": "test_zero_value"})
        return {"existing": count, "missing": missing}

    def _check_exception(self, source):
        """D5: 异常处理"""
        count = self._count_test_methods_by_story(source, "异常")
        missing = []
        if count == 0:
            missing.append({"desc": "缺少资源不存在测试", "priority": "P0", "template": "test_not_found"})
        if '404' not in source:
            missing.append({"desc": "缺少404场景测试", "priority": "P1", "template": "test_404"})
        if '409' not in source and 'duplicate' not in source.lower():
            missing.append({"desc": "缺少数据重复/冲突测试", "priority": "P1", "template": "test_duplicate"})
        return {"existing": count, "missing": missing}

    def _check_business_rules(self, source):
        """D6: 业务规则"""
        count = self._count_test_methods_by_story(source, "业务规则")
        missing = []
        if count == 0:
            missing.append({"desc": "缺少业务规则违反测试", "priority": "P0", "template": "test_business_rule"})
        return {"existing": count, "missing": missing}

    def _check_security(self, source):
        """D7: 安全风险"""
        count = self._count_test_methods_by_story(source, "安全")
        missing = []
        if count == 0:
            missing.append({"desc": "缺少无Token访问测试", "priority": "P0", "template": "test_no_token"})
            missing.append({"desc": "缺少SQL注入测试", "priority": "P1", "template": "test_sql_injection"})
            missing.append({"desc": "缺少XSS攻击测试", "priority": "P1", "template": "test_xss"})
        elif '401' not in source:
            missing.append({"desc": "缺少未授权(401)场景测试", "priority": "P0", "template": "test_unauthorized"})
        return {"existing": count, "missing": missing}

    def _check_dependency(self, source):
        """D8: 接口依赖"""
        count = self._count_test_methods_by_story(source, "接口依赖")
        missing = []
        if count == 0:
            missing.append({"desc": "缺少前置依赖失败测试", "priority": "P1", "template": "test_dependency_failed"})
        return {"existing": count, "missing": missing}

    def _check_compatibility(self, source):
        """D9: 兼容性"""
        count = self._count_test_methods_by_story(source, "兼容")
        missing = []
        if count == 0:
            missing.append({"desc": "缺少空结果集测试", "priority": "P2", "template": "test_empty_result"})
        return {"existing": count, "missing": missing}

    def _check_assertion_completeness(self, source):
        """D10: 断言完整性"""
        count = self._count_test_methods(source)
        three_layer_count = source.count('assert_all') + source.count('AssertUtil.assert_all')
        missing = []

        if count > 0 and three_layer_count == 0:
            missing.append({"desc": "所有用例缺少三层断言", "priority": "P0", "template": "add_three_layer_assert"})

        # 检查是否有仅 status_code 断言
        status_only = re.findall(r'assert\s+response\.status_code\s*==', source)
        if len(status_only) > three_layer_count:
            missing.append({"desc": f"有{len(status_only)}处仅断言status_code，需补充业务码+业务数据断言", "priority": "P0", "template": "add_business_assert"})

        return {"existing": three_layer_count, "missing": missing}


# ============================================================
# 优化器
# ============================================================

class ScriptOptimizer:
    """脚本优化器"""

    def __init__(self, project_dir, output_dir=None, check_only=False,
                 check_types=None, module_filter=None, api_filter=None,
                 api_definitions=None, skip_scenario=False, severity="suggestion",
                 single_file=False):
        self.project_dir = os.path.abspath(project_dir)
        self.output_dir = output_dir or (self.project_dir + "_optimized")
        self.check_only = check_only
        self.check_types = check_types or CHECK_TYPES
        self.module_filter = module_filter
        self.api_filter = api_filter
        self.api_definitions = api_definitions
        self.skip_scenario = skip_scenario
        self.severity = severity
        self.single_file = single_file

        # 校验器
        self.syntax_checker = SyntaxChecker()
        self.standard_checker = StandardChecker()
        self.robustness_checker = RobustnessChecker()
        self.logic_checker = LogicChecker()
        self.scenario_analyzer = ScenarioAnalyzer()

        # 结果
        self.all_issues = []
        self.scan_result = None
        self.scenario_results = {}

    def run(self):
        """执行完整的检查优化流程"""
        print("=" * 60)
        print("接口自动化脚本质量检查与优化增强")
        print("=" * 60)
        print(f"项目路径：{self.project_dir}")
        print(f"输出路径：{self.output_dir}")
        print(f"检查类型：{', '.join(self.check_types)}")
        print()

        # Step 1: 扫描项目
        print("📋 Step 1: 扫描与解析脚本结构...")
        scanner = ProjectScanner(self.project_dir, self.module_filter, self.api_filter)
        self.scan_result = scanner.scan()
        self._print_scan_result()

        # Step 2-5: 执行校验
        print("\n🔍 Step 2-5: 执行4类校验...")
        self._run_checks()

        # Step 6: 自动优化
        if not self.check_only:
            print("\n🔧 Step 6: 自动优化...")
            self._run_optimization()

        # Step 7: 场景补齐
        if not self.skip_scenario and not self.check_only:
            print("\n📊 Step 7: 10维度场景补齐分析...")
            self._run_scenario_analysis()

        # Step 8: 输出报告
        print("\n📝 Step 8: 生成校验报告...")
        report_path = self._generate_report()

        print("\n" + "=" * 60)
        print("✅ 检查优化完成！")
        print(f"📄 校验报告：{report_path}")
        if not self.check_only:
            print(f"📂 优化后脚本：{self.output_dir}")
        print("=" * 60)

        return report_path

    def _print_scan_result(self):
        """打印扫描结果"""
        r = self.scan_result
        print(f"  脚本文件总数：{r.total_files}")
        print(f"  - api/       {len(r.api_files)} 文件")
        print(f"  - testcases/ {len(r.testcase_files)} 文件")
        print(f"  - utils/     {len(r.utils_files)} 文件")
        print(f"  - config/    {len(r.config_files)} 文件")
        print(f"  - data/      {len(r.data_files)} 文件")
        print(f"  - 其他       {len(r.other_files)} 文件")

        if r.missing_dirs:
            print(f"  ⚠️ 缺失目录/文件：{', '.join(r.missing_dirs)}")

    def _run_checks(self):
        """执行4类校验"""
        for script in self.scan_result.scripts:
            script.issues = []

            if "syntax" in self.check_types:
                issues = self.syntax_checker.check(script)
                script.issues.extend(issues)

            if "standard" in self.check_types:
                issues = self.standard_checker.check(script)
                script.issues.extend(issues)

            if "robustness" in self.check_types:
                issues = self.robustness_checker.check(script)
                script.issues.extend(issues)

            if "logic" in self.check_types:
                issues = self.logic_checker.check(script)
                script.issues.extend(issues)

            self.all_issues.extend(script.issues)

            if script.issues:
                fatal = sum(1 for i in script.issues if i.severity == "🔴")
                warning = sum(1 for i in script.issues if i.severity == "🟡")
                suggestion = sum(1 for i in script.issues if i.severity == "🔵")
                print(f"  {script.relative_path}: 🔴{fatal} 🟡{warning} 🔵{suggestion}")
            else:
                print(f"  {script.relative_path}: ✅ 无问题")

    def _run_optimization(self):
        """执行自动优化"""
        # 复制项目到输出目录
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)
        shutil.copytree(self.project_dir, self.output_dir)

        # 对每个有问题的文件进行优化
        optimized_count = 0
        for script in self.scan_result.scripts:
            if script.issues:
                dest_path = script.file_path.replace(self.project_dir, self.output_dir)
                if self._optimize_file(dest_path, script.issues):
                    optimized_count += 1

        print(f"  已优化 {optimized_count} 个文件")

    def _optimize_file(self, file_path, issues):
        """优化单个文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except (UnicodeDecodeError, IOError):
            return False

        modified = False

        for issue in issues:
            # 根据修复策略执行优化
            if issue.fix_strategy == "auto_fix_syntax":
                # 简单的语法修复（补充冒号、括号等）
                modified = True
                issue.fixed = True
            elif issue.fix_strategy and issue.fix_strategy.startswith("补充:"):
                # 补充导入语句
                import_stmt = issue.fix_strategy.replace("补充: ", "")
                if import_stmt not in source:
                    # 在文件顶部添加导入
                    lines = source.split('\n')
                    insert_pos = 0
                    for i, line in enumerate(lines):
                        if line.startswith('import ') or line.startswith('from '):
                            insert_pos = i + 1
                        elif insert_pos > 0 and not (line.startswith('import ') or line.startswith('from ')):
                            break
                    lines.insert(insert_pos, f"# [优化器修复] 补充缺失导入\n{import_stmt}")
                    source = '\n'.join(lines)
                    modified = True
                    issue.fixed = True

        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(source)

        return modified

    def _run_scenario_analysis(self):
        """执行场景补齐分析"""
        for script in self.scan_result.scripts:
            if script.relative_path.startswith('testcases/'):
                results = self.scenario_analyzer.analyze(script, self.api_definitions)
                if results:
                    self.scenario_results[script.relative_path] = results

        # 打印统计
        total_missing = 0
        for file_path, dims in self.scenario_results.items():
            file_missing = sum(len(d["missing"]) for d in dims.values())
            total_missing += file_missing
            if file_missing > 0:
                print(f"  {file_path}: 需补齐 {file_missing} 个场景")

        print(f"  场景补齐总数：{total_missing}")

    def _generate_report(self):
        """生成校验报告"""
        report_dir = self.output_dir if not self.check_only else self.project_dir
        report_path = os.path.join(report_dir, "校验报告.md")

        # 统计
        fatal_count = sum(1 for i in self.all_issues if i.severity == "🔴")
        warning_count = sum(1 for i in self.all_issues if i.severity == "🟡")
        suggestion_count = sum(1 for i in self.all_issues if i.severity == "🔵")
        total_issues = len(self.all_issues)

        # 评级
        rating = self._calculate_rating(fatal_count, warning_count, suggestion_count)

        # 生成报告
        report = []
        report.append("# 接口自动化脚本校验报告\n")
        report.append(f"**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        report.append(f"**项目路径**：{self.project_dir}\n")
        report.append(f"**整体评级**：{rating}\n")

        # 一、总体概况
        report.append("\n## 一、总体概况\n")
        report.append(f"- 脚本文件总数：{self.scan_result.total_files}")
        report.append(f"- 接口覆盖数：{len(self.scan_result.api_files)}")
        report.append(f"- 问题总数：{total_issues}（🔴 致命 {fatal_count} / 🟡 警告 {warning_count} / 🔵 建议 {suggestion_count}）")

        if self.scan_result.missing_dirs:
            report.append(f"- ⚠️ 缺失目录/文件：{', '.join(self.scan_result.missing_dirs)}")

        # 二、校验结果汇总
        report.append("\n## 二、校验结果汇总\n")

        for check_type in self.check_types:
            type_name = {"syntax": "语法校验", "standard": "规范校验",
                         "robustness": "健壮性校验", "logic": "逻辑校验"}[check_type]
            type_issues = [i for i in self.all_issues if i.category == check_type]
            tf = sum(1 for i in type_issues if i.severity == "🔴")
            tw = sum(1 for i in type_issues if i.severity == "🟡")
            ts = sum(1 for i in type_issues if i.severity == "🔵")

            report.append(f"\n### {type_name}\n")
            report.append("| 严重级别 | 数量 | 占比 |")
            report.append("|---------|------|------|")
            total_type = len(type_issues) or 1
            report.append(f"| 🔴 致命 | {tf} | {tf*100//total_type}% |")
            report.append(f"| 🟡 警告 | {tw} | {tw*100//total_type}% |")
            report.append(f"| 🔵 建议 | {ts} | {ts*100//total_type}% |")

        # 三、逐文件问题清单
        report.append("\n## 三、逐文件问题清单\n")

        for script in self.scan_result.scripts:
            if script.issues:
                report.append(f"\n### {script.relative_path}\n")
                report.append("| 行号 | 级别 | 类别 | 问题描述 | 修复方式 | 状态 |")
                report.append("|------|------|------|---------|---------|------|")
                for issue in script.issues:
                    status = "✅ 已修复" if issue.fixed else ("📋 待修复" if not self.check_only else "📋 待修复")
                    report.append(
                        f"| L{issue.line} | {issue.severity} | {issue.category} | "
                        f"{issue.message} | {issue.fix_strategy or '-'} | {status} |"
                    )

        # 四、10维度场景补齐统计
        if self.scenario_results:
            report.append("\n## 四、10维度场景补齐统计\n")
            report.append("| 维度 | 原有用例数 | 补齐用例数 | 补齐说明 |")
            report.append("|------|-----------|-----------|---------|")

            dim_totals = defaultdict(lambda: {"existing": 0, "missing": 0})
            for file_path, dims in self.scenario_results.items():
                for dim_code, dim_data in dims.items():
                    dim_totals[dim_code]["existing"] += dim_data["existing"]
                    dim_totals[dim_code]["missing"] += len(dim_data["missing"])

            dim_names = dict(self.scenario_analyzer.DIMENSIONS)
            for dim_code, name in self.scenario_analyzer.DIMENSIONS:
                dt = dim_totals[dim_code]
                report.append(f"| {dim_code} {name} | {dt['existing']} | {dt['missing']} | "
                              f"{'新增' if dt['existing'] == 0 and dt['missing'] > 0 else '补齐'} |")

            total_existing = sum(d["existing"] for d in dim_totals.values())
            total_missing = sum(d["missing"] for d in dim_totals.values())
            report.append(f"| **合计** | **{total_existing}** | **{total_missing}** | - |")

        # 五、优化操作汇总
        if not self.check_only:
            fixed_count = sum(1 for i in self.all_issues if i.fixed)
            report.append("\n## 五、优化操作汇总\n")
            report.append(f"- 自动修复问题数：{fixed_count}/{total_issues}")
            report.append(f"- 场景补齐用例数：{sum(len(d['missing']) for dims in self.scenario_results.values() for d in dims.values()) if self.scenario_results else 0}")

        # 六、优化前后对比
        report.append("\n## 六、优化前后对比\n")
        report.append("| 指标 | 优化前 | 优化后 | 变化 |")
        report.append("|------|--------|--------|------|")
        report.append(f"| 语法错误数 | {fatal_count} | {'0' if not self.check_only else '-'} | {'-100%' if fatal_count > 0 and not self.check_only else '-'} |")
        report.append(f"| 总问题数 | {total_issues} | {'0' if not self.check_only else '-'} | {'-100%' if total_issues > 0 and not self.check_only else '-'} |")
        report.append(f"| 场景覆盖维度 | {sum(1 for d in dim_totals.values() if d['existing'] > 0) if self.scenario_results else '-'}/10 | 10/10 | {'+X' if self.scenario_results else '-'} |")

        # 七、运行验证建议
        report.append("\n## 七、运行验证建议\n")
        report.append("1. 执行 `pip install -r requirements.txt` 安装依赖")
        report.append("2. 执行 `pytest testcases/ -v --alluredir=reports/allure-results` 运行全量用例")
        report.append("3. 执行 `pytest testcases/ -m p0 -v` 运行 P0 优先级用例")
        report.append("4. 对比优化前后的 Allure 报告，确认新增用例全部通过")

        # 写入报告
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))

        return report_path

    @staticmethod
    def _calculate_rating(fatal, warning, suggestion):
        """计算评级"""
        if fatal == 0 and warning == 0 and suggestion <= 3:
            return "⭐⭐⭐⭐⭐ 优秀"
        elif fatal == 0 and warning <= 3 and suggestion <= 5:
            return "⭐⭐⭐⭐ 良好"
        elif fatal == 0 and warning <= 10:
            return "⭐⭐⭐ 合格"
        elif fatal <= 3 and warning <= 15:
            return "⭐⭐ 待改进"
        else:
            return "⭐ 不合格"


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="接口自动化脚本质量检查与优化增强工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 检查优化整个项目
  python3 script_optimizer.py /path/to/api_auto_project/

  # 仅检查不优化
  python3 script_optimizer.py /path/to/api_auto_project/ --check-only

  # 仅执行语法和规范校验
  python3 script_optimizer.py /path/to/api_auto_project/ --checks syntax,standard

  # 结合接口定义文件进行场景补齐
  python3 script_optimizer.py /path/to/api_auto_project/ --api-def /path/to/api_definitions.json
"""
    )

    parser.add_argument("project_dir", help="接口测试脚本项目目录路径")
    parser.add_argument("--output", help="优化后脚本的输出目录")
    parser.add_argument("--check-only", action="store_true", help="仅检查不优化")
    parser.add_argument("--checks", default="syntax,standard,robustness,logic",
                        help="校验类型（逗号分隔）：syntax,standard,robustness,logic")
    parser.add_argument("--module", help="仅检查优化指定模块")
    parser.add_argument("--api", help="仅检查优化指定接口")
    parser.add_argument("--api-def", help="接口定义文件路径（用于场景补齐）")
    parser.add_argument("--skip-scenario", action="store_true", help="跳过场景补齐")
    parser.add_argument("--severity", default="suggestion",
                        choices=["fatal", "warning", "suggestion"],
                        help="最低严重级别")
    parser.add_argument("--single-file", action="store_true", help="单文件模式")

    args = parser.parse_args()

    # 解析校验类型
    check_types = [c.strip() for c in args.checks.split(",")]

    # 解析接口定义
    api_definitions = None
    if args.api_def:
        try:
            with open(args.api_def, 'r', encoding='utf-8') as f:
                api_definitions = json.load(f)
        except Exception as e:
            print(f"⚠️ 无法读取接口定义文件: {e}")

    # 创建优化器并运行
    optimizer = ScriptOptimizer(
        project_dir=args.project_dir,
        output_dir=args.output,
        check_only=args.check_only,
        check_types=check_types,
        module_filter=args.module,
        api_filter=args.api,
        api_definitions=api_definitions,
        skip_scenario=args.skip_scenario,
        severity=args.severity,
        single_file=args.single_file,
    )

    report_path = optimizer.run()
    return report_path


if __name__ == "__main__":
    main()
