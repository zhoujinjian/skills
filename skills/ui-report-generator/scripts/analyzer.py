"""analyzer.py — 报告数据分析

聚合统计：by_module / by_priority / by_browser / by_category / by_root_cause
风险分析：高风险模块（通过率 <70%）+ flaky + 失败聚类
优化建议：基于失败模式生成
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from parsers import DiagnoseRecord, ReportDocument, UITestCase


# ============ 聚合维度 ============


def aggregate_by_module(cases: list[UITestCase]) -> dict[str, dict]:
    """按模块（path 第 2 段）聚合。

    'tests/product/test_search.py' → 'product'
    'tests/auth/test_login.py' → 'auth'
    """
    by: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "passed": 0, "failed": 0, "errors": 0,
        "skipped": 0, "durations": [],
    })
    for c in cases:
        module = _extract_module(c)
        d = by[module]
        d["total"] += 1
        if c.status == "passed":
            d["passed"] += 1
        elif c.status == "failed":
            d["failed"] += 1
        elif c.status == "error":
            d["errors"] += 1
        elif c.status == "skipped":
            d["skipped"] += 1
        d["durations"].append(c.duration)

    result: dict[str, dict] = {}
    for mod, d in by.items():
        avg = sum(d["durations"]) / len(d["durations"]) if d["durations"] else 0
        pass_rate = (d["passed"] / d["total"] * 100) if d["total"] else 0
        result[mod] = {
            "total": d["total"],
            "passed": d["passed"],
            "failed": d["failed"] + d["errors"],
            "skipped": d["skipped"],
            "pass_rate": round(pass_rate, 1),
            "avg_duration": round(avg, 2),
            "risk": _risk_level(pass_rate),
        }
    return result


def aggregate_by_priority(cases: list[UITestCase]) -> dict[str, dict]:
    """按优先级 marker 聚合：P0/P1/P2/P3。"""
    by: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "passed": 0, "failed": 0,
    })
    for c in cases:
        prio = _extract_priority(c)
        d = by[prio]
        d["total"] += 1
        if c.status == "passed":
            d["passed"] += 1
        elif c.status in ("failed", "error"):
            d["failed"] += 1

    result: dict[str, dict] = {}
    for prio in ["P0", "P1", "P2", "P3", "未标记"]:
        if prio in by:
            d = by[prio]
            pass_rate = (d["passed"] / d["total"] * 100) if d["total"] else 0
            result[prio] = {
                "total": d["total"],
                "passed": d["passed"],
                "failed": d["failed"],
                "pass_rate": round(pass_rate, 1),
            }
    return result


def aggregate_by_browser(cases: list[UITestCase]) -> dict[str, dict]:
    """按浏览器引擎聚合：chromium/firefox/webkit。"""
    by: dict[str, dict] = defaultdict(lambda: {
        "total": 0, "passed": 0, "failed": 0,
    })
    for c in cases:
        b = c.browser or "未指定"
        d = by[b]
        d["total"] += 1
        if c.status == "passed":
            d["passed"] += 1
        elif c.status in ("failed", "error"):
            d["failed"] += 1

    result: dict[str, dict] = {}
    for browser, d in by.items():
        pass_rate = (d["passed"] / d["total"] * 100) if d["total"] else 0
        result[browser] = {
            "total": d["total"],
            "passed": d["passed"],
            "failed": d["failed"],
            "pass_rate": round(pass_rate, 1),
        }
    return result


def aggregate_diagnose(records: list[DiagnoseRecord]) -> tuple[dict[str, int], dict[str, int]]:
    """从 diagnose records 聚合 by_category + by_root_cause。"""
    by_cat: Counter = Counter()
    by_rc: Counter = Counter()

    for r in records:
        if r.category:
            by_cat[r.category] += 1
        # 优先取升级后的根因
        rc = r.upgraded_root_cause or r.root_cause
        if rc:
            label = rc + "（升级）" if r.upgraded_root_cause else rc
            by_rc[label] += 1

    return dict(by_cat), dict(by_rc)


# ============ 风险与建议 ============


def analyze_risk(by_module: dict[str, dict]) -> list[dict]:
    """识别高风险模块（通过率 < 70%）。"""
    risks = []
    for mod, d in by_module.items():
        if d["total"] < 1:
            continue
        if d["risk"] == "high":
            risks.append({
                "module": mod,
                "pass_rate": d["pass_rate"],
                "failed": d["failed"],
                "total": d["total"],
                "level": "高",
                "reason": f"通过率 {d['pass_rate']}% < 70%",
            })
        elif d["risk"] == "mid":
            risks.append({
                "module": mod,
                "pass_rate": d["pass_rate"],
                "failed": d["failed"],
                "total": d["total"],
                "level": "中",
                "reason": f"通过率 {d['pass_rate']}% 偏低（70-90%）",
            })
    return sorted(risks, key=lambda r: (r["level"] == "中", r["pass_rate"]))


def cluster_failures(failures: list[UITestCase], records: list[DiagnoseRecord]) -> list[dict]:
    """按根因聚类失败用例。"""
    record_by_nodeid = {r.nodeid: r for r in records}
    clusters: dict[str, list[str]] = defaultdict(list)
    for f in failures:
        rec = record_by_nodeid.get(f.nodeid)
        rc = (rec.upgraded_root_cause or rec.root_cause) if rec else None
        key = rc or _fallback_cluster_key(f)
        clusters[key].append(f.nodeid)

    result = []
    for rc, nodeids in clusters.items():
        result.append({
            "root_cause": rc,
            "count": len(nodeids),
            "nodeids": nodeids,
        })
    return sorted(result, key=lambda c: -c["count"])


def generate_suggestions(
    by_module: dict[str, dict],
    by_category: dict[str, int],
    by_root_cause: dict[str, int],
    records: list[DiagnoseRecord],
) -> list[dict]:
    """基于失败模式生成优化建议。"""
    suggestions: list[dict] = []

    # 1. 高频根因建议
    top_rc = max(by_root_cause.items(), key=lambda x: x[1]) if by_root_cause else None
    if top_rc and top_rc[1] >= 2:
        suggestions.append({
            "priority": "P0",
            "category": "根因聚类",
            "suggestion": f"重点修复根因「{top_rc[0]}」（命中 {top_rc[1]} 次）",
            "action": _rc_action(top_rc[0]),
        })

    # 2. ENV 问题
    if by_category.get("ENV_ERROR", 0) > 0:
        suggestions.append({
            "priority": "P0",
            "category": "环境",
            "suggestion": "存在 ENV_ERROR，先修复环境再回归（playwright install / pip install / 端口冲突）",
            "action": "运行 diagnose.py 自动类别修复，或手动检查 CI 环境",
        })

    # 3. LOCATOR/TIMEOUT 多发
    locator_count = by_category.get("LOCATOR_ERROR", 0) + by_category.get("TIMEOUT_ERROR", 0)
    if locator_count >= 2:
        suggestions.append({
            "priority": "P1",
            "category": "前端稳定性",
            "suggestion": f"LOCATOR/TIMEOUT 失败 {locator_count} 次，前端选择器可能不稳定或加载时序变化",
            "action": "排查 pages.yaml 是否过期；考虑增加 wait_for_load_state；对 flaky 用例加 retry",
        })

    # 4. 高风险模块
    high_risk = [m for m, d in by_module.items() if d["risk"] == "high"]
    if high_risk:
        suggestions.append({
            "priority": "P1",
            "category": "模块质量",
            "suggestion": f"高风险模块：{', '.join(high_risk)}（通过率 < 70%）",
            "action": "优先补齐该模块的边界场景与负向用例；联系前端确认最近 DOM 改动",
        })

    # 5. 升级为 assertion_mismatch 的用例
    upgraded = [r for r in records if r.upgraded_root_cause == "assertion_mismatch"]
    if upgraded:
        suggestions.append({
            "priority": "P1",
            "category": "业务对齐",
            "suggestion": f"{len(upgraded)} 条用例 verify 失败已升级为 assertion_mismatch，等待逻辑不是根因",
            "action": "排查后端搜索接口是否返回数据；测试库是否有对应商品；业务逻辑是否变更",
        })

    # 6. 跨浏览器不一致
    browsers_with_fail = []
    for b, d in by_module.items() if False else {}.items():
        pass
    # 单独算 by_browser 的不一致
    return suggestions


def _rc_action(root_cause: str) -> str:
    """根据根因给出具体动作。"""
    actions = {
        "missing_async_list_wait": "在 get_product_count 等列表方法前插入 _wait_for_product_list_loaded；diagnose.py 已支持自动 AST 修复",
        "assertion_mismatch": "排查后端接口或测试数据，等待逻辑非根因",
        "locator_drift": "对比 pages.yaml 金标准，更新选择器；引入 data-testid",
        "insufficient_wait": "调大 timeout 至 max(N*3, 30000)；加 wait_for_load_state",
        "page_not_loaded": "在 page.goto 后加 wait_for_load_state('networkidle')",
        "missing_iframe_switch": "用 frame_locator 包裹交互",
        "shadow_dom_not_pierced": "使用 >>> 穿透选择器",
        "missing_browser_binary": "运行 python -m playwright install chromium",
        "missing_python_package": "pip install 缺失的包",
        "known_bug_pattern": "在 conftest.py 注入 xfail/flaky marker",
    }
    return actions.get(root_cause, "参考 ui-failure-diagnoser 报告")


# ============ 工具函数 ============


def _extract_module(case: UITestCase) -> str:
    """从 file 路径或 classname 提取模块名。

    file 路径优先：
        'tests/product/test_search.py' → 'product'
        'tests/auth/test_login.py' → 'auth'
        'tests/test_smoke.py' → 'smoke'

    file 为空时从 classname 回退（JUnit XML 常不包含 file= 属性）：
        'tests.product.test_search.TestSearchPositive' → 'product'
        'tests.auth.test_login.TestLogin' → 'auth'
        'tests.test_smoke.TestSmoke' → 'smoke'
    """
    if case.file:
        parts = case.file.replace("\\", "/").split("/")
        if "tests" in parts:
            idx = parts.index("tests")
            if idx + 1 < len(parts) and not parts[idx + 1].startswith("test_"):
                return parts[idx + 1]
            return parts[-1].replace("test_", "").replace(".py", "") or "未分类"
        name = parts[-1].replace(".py", "")
        if name.startswith("test_"):
            name = name[5:]
        if name:
            return name

    # classname 回退：tests.product.test_search.TestSearchPositive → product
    if case.classname:
        parts = case.classname.split(".")
        if "tests" in parts:
            idx = parts.index("tests")
            if idx + 1 < len(parts):
                seg = parts[idx + 1]
                if not seg.startswith("test_"):
                    return seg
                # tests.test_smoke.TestSmoke → 'smoke'
                return seg.replace("test_", "") or "未分类"
        if len(parts) >= 2 and not parts[-1].startswith("Test"):
            return parts[-2]
    return "未分类"


def _extract_priority(case: UITestCase) -> str:
    for m in case.markers:
        if m in ("P0", "P1", "P2", "P3"):
            return m
    return "未标记"


def _risk_level(pass_rate: float) -> str:
    if pass_rate < 70:
        return "high"
    if pass_rate < 90:
        return "mid"
    return "low"


def _fallback_cluster_key(case: UITestCase) -> str:
    """没有诊断记录时的兜底聚类：按错误类型。"""
    if not case.message:
        return "未分类错误"
    if "Timeout" in case.message:
        return "TimeoutError（未诊断）"
    if "AssertionError" in case.message or "Assertion" in case.message:
        return "AssertionError（未诊断）"
    if "Locator" in case.message or "selector" in case.message.lower():
        return "LocatorError（未诊断）"
    return "其他（未诊断）"
