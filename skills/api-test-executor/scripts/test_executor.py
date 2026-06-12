#!/usr/bin/env python3
"""
接口自动化测试智能执行调度引擎
核心能力：触发执行 + 范围筛选 + 结果收集
"""

import argparse
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ============================================================
# 常量
# ============================================================

VALID_ENVS = ("dev", "test", "pre")
VALID_SCOPES = ("full", "smoke", "regression")
MAX_PARALLEL = 16
MAX_RETRY = 5
DEFAULT_PARALLEL = 4
DEFAULT_RETRY = 2
DEFAULT_TIMEOUT = 30

CST = timezone(timedelta(hours=8))


# ============================================================
# 自然语言解析器
# ============================================================

NLP_RULES: List[Dict] = [
    # scope
    {"patterns": [r"冒烟", r"smoke", r"核心链路"], "param": "scope", "value": "smoke"},
    {"patterns": [r"回归", r"regression"], "param": "scope", "value": "regression"},
    {"patterns": [r"全量", r"所有用例", r"全部"], "param": "scope", "value": "full"},
    # env
    {"patterns": [r"dev\s*环境", r"开发环境"], "param": "env", "value": "dev"},
    {"patterns": [r"test\s*环境", r"测试环境"], "param": "env", "value": "test"},
    {"patterns": [r"pre\s*环境", r"预发环境", r"预发布"], "param": "env", "value": "pre"},
    # priority
    {"patterns": [r"P0", r"高优先级", r"最高优先级"], "param": "priority", "value": "P0"},
    {"patterns": [r"P1", r"中优先级"], "param": "priority", "value": "P1"},
    {"patterns": [r"P2", r"低优先级"], "param": "priority", "value": "P2"},
    {"patterns": [r"P3"], "param": "priority", "value": "P3"},
    # scene tags
    {"patterns": [r"正向", r"正常流程", r"成功场景"], "param": "tag", "value": "scene:positive"},
    {"patterns": [r"反向", r"异常", r"异常场景"], "param": "tag", "value": "scene:negative"},
    {"patterns": [r"边界", r"边界值"], "param": "tag", "value": "scene:boundary"},
    # exclude tags
    {"patterns": [r"排除.*不稳定", r"跳过.*flaky", r"排除.*flaky", r"不稳定"], "param": "exclude_tag", "value": "flaky"},
    # parallel
    {"patterns": [r"(\d+)\s*个线程", r"(\d+)\s*线程", r"并发\s*(\d+)"], "param": "parallel", "value_group": 1},
    # retry
    {"patterns": [r"重试\s*(\d+)\s*次", r"失败重试\s*(\d+)"], "param": "retry", "value_group": 1},
    # dry-run
    {"patterns": [r"模拟", r"预览", r"dry.?run", r"看看.*哪些"], "param": "dry_run", "value": True},
]

# 模块映射表
MODULE_ALIASES: Dict[str, str] = {
    "登录": "auth", "认证": "auth", "鉴权": "auth", "注册": "auth",
    "订单": "order", "下单": "order",
    "支付": "payment", "付款": "payment",
    "商品": "product", "产品": "product",
    "用户": "user", "会员": "user",
    "购物车": "cart",
    "搜索": "search",
    "评论": "review", "评价": "review",
    "物流": "logistics", "配送": "logistics",
    "退款": "refund", "售后": "refund",
    "地址": "address",
    "收藏": "favorite", "关注": "favorite",
    "通知": "notification", "消息": "notification",
    "优惠券": "coupon",
}


def parse_natural_language(text: str) -> Dict:
    """将自然语言描述解析为执行参数字典"""
    params: Dict = {}
    remaining = text

    for rule in NLP_RULES:
        for pattern in rule["patterns"]:
            m = re.search(pattern, remaining, re.IGNORECASE)
            if m:
                param = rule["param"]
                if "value_group" in rule:
                    value = m.group(int(rule["value_group"]))
                else:
                    value = rule["value"]

                if param in ("module", "tag", "exclude_tag", "priority") and param in params:
                    # 多值追加
                    if isinstance(params[param], list):
                        params[param].append(value)
                    else:
                        params[param] = [params[param], value]
                else:
                    params[param] = value

                remaining = remaining[:m.start()] + remaining[m.end():]
                break

    # 尝试从剩余文本中提取模块名
    for cn_name, en_name in MODULE_ALIASES.items():
        if cn_name in remaining:
            if "module" not in params:
                params["module"] = en_name
            elif isinstance(params["module"], list):
                if en_name not in params["module"]:
                    params["module"].append(en_name)
            elif params["module"] != en_name:
                params["module"] = [params["module"], en_name]

    # 列表参数转逗号分隔字符串
    for key in ("module", "tag", "exclude_tag", "priority"):
        if key in params and isinstance(params[key], list):
            params[key] = ",".join(params[key])

    return params


# ============================================================
# 项目结构验证
# ============================================================

def validate_project(project_dir: str) -> Tuple[bool, List[str]]:
    """轻量级项目结构验证，返回 (是否有效, 警告列表)"""
    warnings = []
    p = Path(project_dir)

    if not p.exists():
        return False, [f"项目目录不存在: {project_dir}"]

    testcases_dir = p / "testcases"
    if not testcases_dir.exists() or not testcases_dir.is_dir():
        return False, [f"缺少 testcases/ 目录: {testcases_dir}"]

    py_files = list(testcases_dir.rglob("test_*.py")) + list(testcases_dir.rglob("*_test.py"))
    if not py_files:
        return False, [f"testcases/ 目录下未发现测试文件 (test_*.py / *_test.py)"]

    return True, warnings


def check_env_config(project_dir: str, env: str) -> Tuple[bool, str]:
    """检查环境配置文件是否存在"""
    config_path = Path(project_dir) / "config" / f"{env}.yaml"
    if config_path.exists():
        return True, str(config_path)
    # 也检查 yml 后缀
    config_path_yml = Path(project_dir) / "config" / f"{env}.yml"
    if config_path_yml.exists():
        return True, str(config_path_yml)
    return False, ""


def check_tag_index(project_dir: str) -> Optional[str]:
    """检查标签索引文件是否存在"""
    tag_index_path = Path(project_dir) / "tag_index.json"
    if tag_index_path.exists():
        return str(tag_index_path)
    return None


# ============================================================
# 执行范围解析
# ============================================================

def load_tag_index(tag_index_path: str) -> Dict:
    """加载标签索引文件"""
    with open(tag_index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_scope_by_tag_index(
    tag_index: Dict,
    scope: str = "full",
    module: str = "all",
    priority: str = "all",
    tag: Optional[str] = None,
    exclude_tag: Optional[str] = None,
) -> List[str]:
    """基于标签索引筛选用例节点 ID 列表"""
    cases = tag_index.get("cases", [])
    filtered = []

    include_tags = set()
    if tag:
        include_tags = set(t.strip() for t in tag.split(","))

    exclude_tags = set()
    if exclude_tag:
        exclude_tags = set(t.strip() for t in exclude_tag.split(","))

    scope_tags_map = {
        "smoke": {"scope:smoke"},
        "regression": {"scope:regression"},
    }

    modules = set()
    if module and module != "all":
        modules = set(m.strip() for m in module.split(","))

    priorities = set()
    if priority and priority != "all":
        priorities = set(p.strip() for p in priority.split(","))

    for case in cases:
        case_id = case.get("case_id", "")
        case_tags = set(case.get("tags", []))

        # scope 过滤
        if scope in scope_tags_map:
            if not case_tags & scope_tags_map[scope]:
                continue

        # module 过滤
        if modules:
            case_modules = {t.split(":")[1] for t in case_tags if t.startswith("module:")}
            if not case_modules & modules:
                continue

        # priority 过滤
        if priorities:
            case_priorities = {t for t in case_tags if t.startswith("priority:")}
            if not case_priorities & {f"priority:{p}" for p in priorities}:
                continue

        # include tag 过滤
        if include_tags:
            if not case_tags & include_tags:
                continue

        # exclude tag 过滤
        if exclude_tags and case_tags & exclude_tags:
            continue

        filtered.append(case_id)

    return filtered


def resolve_scope_by_file_path(
    project_dir: str,
    module: str = "all",
    scope: str = "full",
) -> List[str]:
    """基于文件路径回退筛选用例（无标签索引时使用）"""
    testcases_dir = Path(project_dir) / "testcases"
    matched_files = []

    modules = set()
    if module and module != "all":
        modules = set(m.strip() for m in module.split(","))

    for py_file in sorted(testcases_dir.rglob("test_*.py")):
        if modules:
            file_stem = py_file.stem.lower()  # e.g. test_auth
            file_matched = any(
                f"_{m}" in file_stem or f"{m}" in file_stem.replace("test_", "")
                for m in modules
            )
            if not file_matched:
                continue
        matched_files.append(str(py_file))

    return matched_files


# ============================================================
# pytest 命令构建
# ============================================================

def build_pytest_command(
    project_dir: str,
    filter_ids: Optional[List[str]] = None,
    filter_expression: Optional[str] = None,
    parallel: int = DEFAULT_PARALLEL,
    retry: int = DEFAULT_RETRY,
    timeout: int = DEFAULT_TIMEOUT,
    output_dir: str = "./execution_results",
    env: str = "test",
    dry_run: bool = False,
) -> List[str]:
    """组装 pytest 命令"""
    testcases_dir = str(Path(project_dir) / "testcases")

    cmd = [
        sys.executable, "-m", "pytest",
        testcases_dir,
        "-v",
        f"--env={env}",
    ]

    # 筛选表达式
    if filter_ids:
        cmd.extend(filter_ids)
    elif filter_expression:
        cmd.extend(["-k", filter_expression])

    # 并发
    if parallel > 1:
        cmd.extend(["-n", str(min(parallel, MAX_PARALLEL))])

    # 重试（仅对非断言失败生效 - pytest-rerunfailures 行为）
    if retry > 0:
        cmd.extend(["--reruns", str(min(retry, MAX_RETRY))])
        cmd.extend(["--reruns-delay", "1"])

    # 超时
    cmd.extend(["--timeout", str(timeout)])

    # 报告输出
    allure_dir = str(Path(output_dir) / "allure-results")
    html_dir = str(Path(output_dir) / "html-report")
    html_report = str(Path(html_dir) / "report.html")
    junit_xml = str(Path(output_dir) / "junit.xml")

    cmd.extend(["--alluredir", allure_dir])
    cmd.extend(["--html", html_report])
    cmd.extend(["--junitxml", junit_xml])
    cmd.append("--self-contained-html")

    if dry_run:
        cmd.extend(["--collect-only", "-q"])

    return cmd


# ============================================================
# 结果解析
# ============================================================

def parse_junit_xml(junit_path: str) -> List[Dict]:
    """从 junit.xml 解析用例结果"""
    results = []
    if not os.path.exists(junit_path):
        return results

    tree = ET.parse(junit_path)
    root = tree.getroot()

    for testcase in root.iter("testcase"):
        case_id = testcase.get("classname", "") + "::" + testcase.get("name", "")
        name = testcase.get("name", "")
        time_ms = int(float(testcase.get("time", "0")) * 1000)

        status = "PASS"
        error_message = ""
        error_type = ""
        attempts = 1

        failure = testcase.find("failure")
        error = testcase.find("error")
        skipped = testcase.find("skipped")

        if failure is not None:
            status = "FAIL"
            error_message = (failure.text or "")[:500]
            error_type = failure.get("type", "ASSERTION_ERROR")
        elif error is not None:
            status = "ERROR"
            error_message = (error.text or "")[:500]
            error_type = error.get("type", "RUNTIME_ERROR")
        elif skipped is not None:
            status = "SKIP"
            error_message = (skipped.text or "")[:200]

        results.append({
            "case_id": case_id,
            "name": name,
            "status": status,
            "duration_ms": time_ms,
            "attempts": attempts,
            **({"error_message": error_message} if error_message else {}),
            **({"error_type": error_type} if error_type else {}),
        })

    return results


def parse_pytest_summary(stdout: str) -> Dict:
    """从 pytest 输出提取统计摘要"""
    stats = {
        "total_cases": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    }

    # 匹配 pytest summary 行：X passed, Y failed, Z skipped
    m = re.search(r"(\d+)\s+passed", stdout)
    if m:
        stats["passed"] = int(m.group(1))

    m = re.search(r"(\d+)\s+failed", stdout)
    if m:
        stats["failed"] = int(m.group(1))

    m = re.search(r"(\d+)\s+skipped", stdout)
    if m:
        stats["skipped"] = int(m.group(1))

    m = re.search(r"(\d+)\s+error", stdout)
    if m:
        stats["errors"] = int(m.group(1))

    stats["total_cases"] = stats["passed"] + stats["failed"] + stats["skipped"] + stats["errors"]
    return stats


# ============================================================
# 输出生成
# ============================================================

def generate_execution_results_json(
    project_name: str,
    env: str,
    scope: str,
    filters: Dict,
    start_time: datetime,
    end_time: datetime,
    stats: Dict,
    results: List[Dict],
    output_path: str,
) -> str:
    """生成 execution_results.json"""
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    pass_rate = round(stats["passed"] / stats["total_cases"] * 100, 1) if stats["total_cases"] > 0 else 0

    execution_id = f"exec_{start_time.strftime('%Y%m%d_%H%M%S')}"

    data = {
        "execution_id": execution_id,
        "project": project_name,
        "env": env,
        "scope": scope,
        "filters": filters,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_ms": duration_ms,
        "total_cases": stats["total_cases"],
        "passed": stats["passed"],
        "failed": stats["failed"],
        "skipped": stats["skipped"],
        "pass_rate": pass_rate,
        "results": results,
    }

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return execution_id


def generate_execution_summary_md(
    env: str,
    scope: str,
    filters: Dict,
    stats: Dict,
    results: List[Dict],
    start_time: datetime,
    end_time: datetime,
    output_path: str,
) -> None:
    """生成 execution_summary.md"""
    duration_s = int((end_time - start_time).total_seconds())
    minutes, seconds = divmod(duration_s, 60)
    pass_rate = round(stats["passed"] / stats["total_cases"] * 100, 1) if stats["total_cases"] > 0 else 0

    filter_desc_parts = []
    if filters.get("module"):
        filter_desc_parts.append(f"module={filters['module']}")
    if filters.get("priority"):
        filter_desc_parts.append(f"priority={filters['priority']}")
    if filters.get("tag"):
        filter_desc_parts.append(f"tag={filters['tag']}")
    if filters.get("exclude_tag"):
        filter_desc_parts.append(f"exclude={filters['exclude_tag']}")
    filter_desc = f" ({', '.join(filter_desc_parts)})" if filter_desc_parts else ""

    lines = [
        "# 接口测试执行摘要",
        "",
        "## 执行概览",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 执行环境 | {env} |",
        f"| 执行范围 | {scope}{filter_desc} |",
        f"| 总用例数 | {stats['total_cases']} |",
        f"| 通过 | {stats['passed']} ({pass_rate}%) |",
        f"| 失败 | {stats['failed']} ({100 - pass_rate if stats['total_cases'] > 0 else 0}%) |",
        f"| 执行耗时 | {minutes}m {seconds}s |",
        "",
    ]

    # 失败用例表
    failed_cases = [r for r in results if r["status"] in ("FAIL", "ERROR")]
    if failed_cases:
        lines.append("## 失败用例")
        lines.append("")
        lines.append("| 用例名 | 错误类型 | 错误摘要 |")
        lines.append("|--------|---------|---------|")
        for fc in failed_cases:
            err_msg = fc.get("error_message", "").split("\n")[0][:80]
            lines.append(f"| {fc['name']} | {fc.get('error_type', 'N/A')} | {err_msg} |")
        lines.append("")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ============================================================
# 主流程
# ============================================================

def run_executor(args: argparse.Namespace) -> int:
    """主执行流程"""
    project_dir = os.path.abspath(args.project_dir)
    project_name = Path(project_dir).name

    # --- Step 1: 自然语言解析 ---
    if args.prompt:
        nlp_params = parse_natural_language(args.prompt)
        # 合并 NLP 解析结果到 args（NLP 结果不覆盖显式参数）
        for key, value in nlp_params.items():
            arg_key = key.replace("-", "_")
            current = getattr(args, arg_key, None)
            if current is None or (isinstance(current, str) and current in ("all", "")):
                setattr(args, arg_key, value)

        print(f"[NLP] 自然语言解析结果:")
        for key, value in nlp_params.items():
            print(f"  --{key} = {value}")

    env = args.env
    scope = args.scope
    module = args.module
    priority = args.priority
    tag = args.tag
    exclude_tag = args.exclude_tag
    parallel = int(args.parallel)
    retry = int(args.retry)
    timeout = int(args.timeout)
    output_dir = os.path.abspath(args.output)
    report_format = args.report_format
    dry_run = args.dry_run

    # --- Step 2: 项目结构验证 ---
    print(f"\n[验证] 检查项目结构: {project_dir}")
    valid, warnings = validate_project(project_dir)
    if not valid:
        for w in warnings:
            print(f"  ERROR: {w}")
        return 1
    for w in warnings:
        print(f"  WARNING: {w}")
    print("  项目结构验证通过")

    # --- Step 3: 环境配置检查 ---
    env_config_ok, env_config_path = check_env_config(project_dir, env)
    if env_config_ok:
        print(f"[配置] 环境配置: {env_config_path}")
    else:
        print(f"[WARNING] 未找到 config/{env}.yaml，将依赖 conftest.py 中的默认配置")

    # --- Step 4: 执行范围解析 ---
    print(f"\n[范围] 解析执行范围...")
    filter_ids = None
    filter_expression = None
    tag_index_path = check_tag_index(project_dir)

    if tag_index_path:
        print(f"  使用标签索引模式: {tag_index_path}")
        tag_index = load_tag_index(tag_index_path)
        filter_ids = resolve_scope_by_tag_index(
            tag_index,
            scope=scope,
            module=module,
            priority=priority,
            tag=tag,
            exclude_tag=exclude_tag,
        )
        print(f"  筛选命中 {len(filter_ids)} 条用例")
        if not filter_ids and scope == "full" and module == "all":
            print("  [WARNING] 全量筛选无命中，回退到执行全部用例")
            filter_ids = None
    else:
        print("  [WARNING] 未找到 tag_index.json，回退到文件路径匹配模式")
        print("  [提示] 建议先运行 api-test-tagger 生成标签索引以提升筛选精度")
        matched_files = resolve_scope_by_file_path(project_dir, module=module)
        if matched_files:
            filter_ids = matched_files
            print(f"  文件路径匹配 {len(matched_files)} 个测试文件")
        else:
            print("  未匹配到测试文件，将执行全部用例")

    # --- Step 5: 构建并执行 pytest ---
    print(f"\n[执行] 构建pytest命令...")
    pytest_cmd = build_pytest_command(
        project_dir=project_dir,
        filter_ids=filter_ids,
        filter_expression=filter_expression,
        parallel=parallel,
        retry=retry,
        timeout=timeout,
        output_dir=output_dir,
        env=env,
        dry_run=dry_run,
    )

    cmd_str = " ".join(pytest_cmd)
    print(f"  命令: {cmd_str}\n")

    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    start_time = datetime.now(CST)
    print("=" * 60)
    print(f" 开始执行: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f" 环境: {env} | 范围: {scope} | 并发: {parallel} | 重试: {retry}")
    print("=" * 60)

    try:
        result = subprocess.run(
            pytest_cmd,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=3600,  # 全局超时 1 小时
        )
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        print("\n[ERROR] 执行超时（超过 1 小时），强制终止")
        return 1

    end_time = datetime.now(CST)

    # --- Step 6: 结果收集 ---
    print("\n" + "=" * 60)
    print(" 执行完成，收集结果...")
    print("=" * 60)

    # 解析 pytest 输出统计
    stats = parse_pytest_summary(stdout + stderr)

    # 解析 junit.xml 获取详细结果
    junit_path = os.path.join(output_dir, "junit.xml")
    detailed_results = parse_junit_xml(junit_path)

    # 如果 junit.xml 无结果，从 pytest 输出补充
    if not detailed_results and stats["total_cases"] > 0:
        for i in range(stats["passed"]):
            detailed_results.append({"case_id": f"case_{i}", "name": f"case_{i}", "status": "PASS", "duration_ms": 0, "attempts": 1})

    # 更新 stats
    if detailed_results:
        stats["passed"] = sum(1 for r in detailed_results if r["status"] == "PASS")
        stats["failed"] = sum(1 for r in detailed_results if r["status"] == "FAIL")
        stats["skipped"] = sum(1 for r in detailed_results if r["status"] == "SKIP")
        stats["errors"] = sum(1 for r in detailed_results if r["status"] == "ERROR")
        stats["total_cases"] = len(detailed_results)

    filters = {
        "module": module if module != "all" else None,
        "priority": priority if priority != "all" else None,
        "tag": tag,
        "exclude_tag": exclude_tag,
    }
    # 清理 None 值
    filters = {k: v for k, v in filters.items() if v}

    # 生成 JSON 结果
    json_path = os.path.join(output_dir, "execution_results.json")
    execution_id = generate_execution_results_json(
        project_name=project_name,
        env=env,
        scope=scope,
        filters=filters,
        start_time=start_time,
        end_time=end_time,
        stats=stats,
        results=detailed_results,
        output_path=json_path,
    )
    print(f"\n[结果] JSON: {json_path}")

    # 生成 Markdown 摘要
    md_path = os.path.join(output_dir, "execution_summary.md")
    generate_execution_summary_md(
        env=env,
        scope=scope,
        filters=filters,
        stats=stats,
        results=detailed_results,
        start_time=start_time,
        end_time=end_time,
        output_path=md_path,
    )
    print(f"[结果] Markdown: {md_path}")

    # 打印简要统计
    pass_rate = round(stats["passed"] / stats["total_cases"] * 100, 1) if stats["total_cases"] > 0 else 0
    print(f"\n[统计] 总计: {stats['total_cases']} | 通过: {stats['passed']} | 失败: {stats['failed']} | 跳过: {stats['skipped']} | 通过率: {pass_rate}%")
    print(f"[ID] {execution_id}")

    return 0 if stats["failed"] == 0 else 1


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="接口自动化测试智能执行调度引擎",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础执行
  python3 scripts/test_executor.py ./shop-lab-api-test --env test

  # 标签筛选执行
  python3 scripts/test_executor.py ./shop-lab-api-test --env test --scope smoke --module auth --priority P0

  # 自然语言模式
  python3 scripts/test_executor.py ./shop-lab-api-test --prompt "在 test 环境跑一下登录模块的冒烟测试"

  # 模拟执行
  python3 scripts/test_executor.py ./shop-lab-api-test --env test --scope smoke --dry-run
        """,
    )

    parser.add_argument("project_dir", help="测试脚本项目目录路径")
    parser.add_argument("--env", default="test", choices=VALID_ENVS, help="执行环境 (default: test)")
    parser.add_argument("--scope", default="full", choices=VALID_SCOPES, help="执行范围 (default: full)")
    parser.add_argument("--module", default="all", help="按模块过滤，逗号分隔 (default: all)")
    parser.add_argument("--priority", default="all", help="按优先级过滤，如 P0,P1 (default: all)")
    parser.add_argument("--tag", default=None, help="按标签过滤，逗号分隔")
    parser.add_argument("--exclude-tag", default=None, help="排除指定标签，逗号分隔")
    parser.add_argument("--parallel", type=int, default=DEFAULT_PARALLEL, help=f"并发线程数 (default: {DEFAULT_PARALLEL}, max: {MAX_PARALLEL})")
    parser.add_argument("--retry", type=int, default=DEFAULT_RETRY, help=f"失败重试次数 (default: {DEFAULT_RETRY}, max: {MAX_RETRY})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"单用例超时秒数 (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--output", default="./execution_results", help="执行结果输出目录 (default: ./execution_results)")
    parser.add_argument("--report-format", default="all", choices=["allure", "html", "json", "all"], help="报告格式 (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="仅模拟执行，输出将要执行的用例列表")
    parser.add_argument("--prompt", default=None, help="自然语言描述执行意图")

    args = parser.parse_args()
    sys.exit(run_executor(args))


if __name__ == "__main__":
    main()
