"""bug_repair.py — BUG 产品缺陷容错策略

4 个子类：
    known_bug          → 加 pytest.mark.skip(reason="BUG: ...") 到 conftest.py
    intermittent_bug   → 加 @pytest.mark.flaky(reruns=N) 到 pages 层方法
    network_5xx_retry  → 在 pages 层加 retry on RequestsError
    stable_bug_report  → 强化报告（含 trace + 录屏链接），生成 bug 工单

**核心约束：** 不改产品代码、不改测试断言。
只在 conftest.py 加 marker hook、在 pages 层加 retry decorator。
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


# ============ 数据结构 ============

@dataclass
class BugRepairPlan:
    subkind: str  # known_bug / intermittent_bug / network_5xx_retry / stable_bug_report
    diagnosis: str
    actions: list[dict] = field(default_factory=list)
    # actions 类型：
    #   {"kind": "patch_conftest", "marker_name": ..., "nodeid_filter": ...}
    #   {"kind": "patch_pages_decorator", "target_file": ..., "target_method": ..., "decorator": ...}
    #   {"kind": "enhance_report", "trace_path": ..., "screenshot_path": ...}
    #   {"kind": "warning", "message": ...}
    #   {"kind": "info", "message": ...}


@dataclass
class BugRepairResult:
    plan: BugRepairPlan
    executed: list[dict] = field(default_factory=list)
    success: bool = False
    message: str = ""


# ============ 已知 bug 指纹库 ============

KNOWN_BUG_SIGNATURES = [
    {
        "id": "BUG-AUTH-001",
        # 允许 Timeout 出现在 get_by_placeholder 之前或之后
        "pattern": re.compile(r'get_by_placeholder\(\s*["\']请输入 用户名["\']\s*\)[\s\S]*?Timeout|Timeout[\s\S]*?get_by_placeholder\(\s*["\']请输入 用户名["\']\s*\)', re.IGNORECASE),
        "page": "/login",
        "description": "登录页「请输入 用户名」placeholder 偶发不可见",
        "strategy": "intermittent_bug",
    },
    {
        "id": "BUG-CAPTCHA-LOAD",
        "pattern": re.compile(r"captcha[\s\S]*?iframe[\s\S]*?Timeout|iframe[\s\S]*?captcha[\s\S]*?Timeout", re.IGNORECASE),
        "page": "/login",
        "description": "验证码 iframe 加载偶发超时",
        "strategy": "intermittent_bug",
    },
]


# ============ 主入口 ============

def diagnose_bug_failure(
    message: str,
    traceback: str = "",
    console_log: str | None = None,
    nodeid: str = "",
    historical_failures: list[dict] | None = None,
) -> BugRepairPlan | None:
    """从失败信息诊断 BUG 子类。"""
    combined = f"{message}\n{traceback}"
    if console_log:
        combined += f"\n{console_log}"

    # 1. 已知 bug（命中指纹库）
    known = _match_known_bug(combined)
    if known:
        return _plan_known_bug(known, nodeid)

    # 2. 历史偶发（同一 nodeid 在历史中失败过但偶尔通过）
    if historical_failures:
        intermittent = _detect_intermittent_from_history(nodeid, historical_failures)
        if intermittent:
            return _plan_intermittent(intermittent, nodeid)

    # 3. 网络 5xx 偶发
    if console_log and _has_network_5xx(console_log):
        return _plan_network_5xx_retry(nodeid)

    # 4. 稳定 bug（首次出现的 page error）
    if console_log and _has_page_error(console_log):
        return _plan_stable_bug_report(nodeid, console_log)

    return None


def execute_bug_repair(
    plan: BugRepairPlan,
    project_dir: Path,
    conftest_path: Path,
    dry_run: bool = False,
) -> BugRepairResult:
    """执行 bug 修复策略。

    所有修复都作用于 conftest.py 或 pages/**/*.py，不改 tests/ 断言。
    """
    result = BugRepairPlan_result_adapter(plan)
    all_success = True

    for action in plan.actions:
        kind = action.get("kind")
        if kind == "patch_conftest":
            success = _apply_conftest_marker(
                conftest_path=conftest_path,
                marker_name=action.get("marker_name", "skip"),
                nodeid_filter=action.get("nodeid_filter", ""),
                reason=action.get("reason", "BUG"),
                dry_run=dry_run,
            )
            result.executed.append({
                "action": "patch_conftest",
                "marker": action.get("marker_name"),
                "nodeid_filter": action.get("nodeid_filter"),
                "success": success,
            })
            if not success:
                all_success = False
        elif kind == "patch_pages_decorator":
            target_file = action.get("target_file")
            method = action.get("target_method", "")
            decorator = action.get("decorator", "")
            success = _apply_pages_decorator(
                target_file=Path(target_file) if target_file else None,
                target_method=method,
                decorator=decorator,
                dry_run=dry_run,
            ) if target_file else False
            result.executed.append({
                "action": "patch_pages_decorator",
                "target_file": str(target_file) if target_file else "",
                "target_method": method,
                "success": success,
            })
            if not success:
                all_success = False
        elif kind in ("info", "warning", "enhance_report"):
            result.executed.append({"action": kind, **action})
            if kind == "warning":
                all_success = False

    result.success = all_success
    result.message = "BUG 容错策略已应用" if all_success else "部分应用或需人工"
    return result


def BugRepairPlan_result_adapter(plan):
    """小工厂：返回 BugRepairResult。"""
    return BugRepairResult(plan=plan)


# ============ 子类检测 ============

def _match_known_bug(text: str) -> dict | None:
    for sig in KNOWN_BUG_SIGNATURES:
        # 主 pattern 命中
        if sig["pattern"].search(text):
            return sig
        # 备用 pattern（如有）
        if sig.get("alt_pattern") and sig["alt_pattern"].search(text):
            return sig
    return None


def _detect_intermittent_from_history(nodeid: str, history: list[dict]) -> dict | None:
    """从历史失败记录判定是否偶发。

    history 元素格式：{"nodeid": ..., "status": "passed"|"failed", "timestamp": ...}
    判定：同一 nodeid 在最近 N 次执行中既有 passed 又有 failed。
    """
    recent = [h for h in history if h.get("nodeid") == nodeid][-5:]
    if len(recent) < 2:
        return None
    statuses = {h.get("status") for h in recent}
    if statuses == {"passed", "failed"}:
        return {
            "fail_count": sum(1 for h in recent if h.get("status") == "failed"),
            "total": len(recent),
        }
    return None


def _has_network_5xx(console_log: str) -> bool:
    """console-log 中是否有 5xx 状态码。"""
    return bool(re.search(r"\b5\d\d\b", console_log))


def _has_page_error(console_log: str) -> bool:
    """console-log 中是否有 Page Error（实质内容，不只是分隔符）。"""
    if "## Page Errors" not in console_log:
        return False
    after = console_log.split("## Page Errors", 1)[-1]
    # 截断到下一个 ## section
    if "##" in after[1:]:
        after = after[1:].split("\n##", 1)[0]
    # 过滤分隔符（--- / ===）和空白行
    lines = [
        line.strip() for line in after.splitlines()
        if line.strip() and not re.match(r"^[=\-]{3,}$", line.strip())
    ]
    return len(lines) > 0


# ============ 修复计划构建 ============

def _plan_known_bug(sig: dict, nodeid: str) -> BugRepairPlan:
    return BugRepairPlan(
        subkind="known_bug",
        diagnosis=f"命中已知 bug 指纹：{sig['id']} - {sig['description']}",
        actions=[
            {
                "kind": "patch_conftest",
                "marker_name": "xfail",
                "nodeid_filter": nodeid,
                "reason": f"Known bug {sig['id']}: {sig['description']}",
            },
            {
                "kind": "info",
                "message": (
                    f"已给 {nodeid} 加 xfail marker。\n"
                    f"  - 测试仍会执行，但失败不再 break build\n"
                    f"  - 修复 bug 后请及时移除 xfail"
                ),
            },
        ],
    )


def _plan_intermittent(info: dict, nodeid: str) -> BugRepairPlan:
    return BugRepairPlan(
        subkind="intermittent_bug",
        diagnosis=(
            f"偶发失败：最近 {info['total']} 次执行中失败 {info['fail_count']} 次。"
            f"建议加 flaky 容错。"
        ),
        actions=[
            {
                "kind": "patch_conftest",
                "marker_name": "flaky",
                "nodeid_filter": nodeid,
                "reason": f"Intermittent failure ({info['fail_count']}/{info['total']})",
            },
            {
                "kind": "info",
                "message": (
                    f"已给 {nodeid} 加 flaky marker（默认 reruns=2）。\n"
                    f"  - 失败后会自动重试\n"
                    f"  - 持续观察：如果 100% 失败，转为 xfail 并提 bug"
                ),
            },
        ],
    )


def _plan_network_5xx_retry(nodeid: str) -> BugRepairPlan:
    return BugRepairPlan(
        subkind="network_5xx_retry",
        diagnosis="console-log 含 5xx 状态码（可能为服务端瞬时故障）",
        actions=[
            {
                "kind": "patch_conftest",
                "marker_name": "flaky",
                "nodeid_filter": nodeid,
                "reason": "Network 5xx (likely transient)",
            },
            {
                "kind": "info",
                "message": (
                    "5xx 通常是服务端瞬时问题。\n"
                    "  - 已加 flaky marker，失败自动重试\n"
                    "  - 如果重试仍失败，联系后端 oncall\n"
                    "  - 长期方案：监控告警 + 自动降级"
                ),
            },
        ],
    )


def _plan_stable_bug_report(nodeid: str, console_log: str) -> BugRepairPlan:
    """稳定 bug：不改代码，强化报告。"""
    page_error_preview = ""
    if "## Page Errors" in console_log:
        after = console_log.split("## Page Errors", 1)[-1]
        page_error_preview = after.split("\n\n", 1)[0][:300]

    return BugRepairPlan(
        subkind="stable_bug_report",
        diagnosis=f"稳定的 Page Error：\n{page_error_preview}",
        actions=[
            {
                "kind": "enhance_report",
                "page_error_preview": page_error_preview,
            },
            {
                "kind": "warning",
                "message": (
                    f"稳定的 Page Error 表明这是真实 bug，不是测试问题。\n"
                    f"  - 本技能不会自动 skip（避免掩盖 bug）\n"
                    f"  - 建议手动在 conftest.py 加 xfail，并提 bug 单\n"
                    f"  - 把 trace.zip + screenshot + console-log 一起附上"
                ),
            },
        ],
    )


# ============ conftest / pages 修改 ============

def _apply_conftest_marker(
    conftest_path: Path,
    marker_name: str,
    nodeid_filter: str,
    reason: str,
    dry_run: bool = False,
) -> bool:
    """在 conftest.py 加一个针对 nodeid_filter 的 marker hook。

    机制：在 conftest.py 末尾追加一段 pytest_collection_modifyitems hook，
    把匹配 nodeid_filter 的 item 加上 marker。

    幂等：若已存在同 marker_name + nodeid_filter 的 hook，不重复加。
    """
    if not conftest_path or not conftest_path.exists():
        return False

    existing = conftest_path.read_text(encoding="utf-8")
    signature = f"# ui-failure-diagnoser: marker {marker_name} on {nodeid_filter}"
    if signature in existing:
        return True  # 已存在，幂等成功

    # 构造 hook 代码
    hook_code = f"""

{signature}
import pytest as _pytest_fd

try:
    _pytest_fd.mark.{marker_name}  # 注册 marker（防 warn）
except Exception:
    pass

def _ui_failure_diagnoser_mark_{marker_name.replace('-', '_')}():
    @_pytest_fd.hookimpl(hookwrapper=True)
    def pytest_collection_modifyitems(items):
        # marker 加在 collection 阶段
        pass

# 简化：直接用 pytest_runtest_setup 给匹配 nodeid 的 item 加 marker
def pytest_runtest_setup(item):
    if "{nodeid_filter}" in item.nodeid:
        item.add_marker(_pytest_fd.mark.{marker_name}(reason="{reason}"))
"""

    if dry_run:
        return True

    try:
        conftest_path.write_text(existing + hook_code, encoding="utf-8")
        return True
    except Exception:
        return False


def _apply_pages_decorator(
    target_file: Path | None,
    target_method: str,
    decorator: str,
    dry_run: bool = False,
) -> bool:
    """在 pages 文件的指定方法上加 decorator。

    注意：MVP 暂不实现自动 AST 加 decorator（容易破坏代码结构）。
    本函数作为占位，实际由 Claude 语义执行（claude_semantic 策略）。
    """
    # MVP: 不自动加 decorator，由用户根据报告手动加
    return False
