"""data_repair.py — DATA_ERROR 测试数据问题自动修复

4 个子类：
    unique_constraint_conflict  → 调 api-testdata-cleaner 清理脏数据
    fixture_init_fail           → 检测 seed 脚本、提示执行
    test_user_consumed          → 在 pages 层加 setup 容错（重试注册）
    external_api_drift          → 检测外部 API 返回异常，提示加 mock

所有副作用操作都通过 AuditLogger。
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audit_log import AuditLogger  # noqa: E402


# ============ 数据结构 ============

@dataclass
class DataRepairPlan:
    subkind: str  # unique_constraint_conflict / fixture_init_fail / test_user_consumed / external_api_drift
    diagnosis: str
    actions: list[dict] = field(default_factory=list)


@dataclass
class DataRepairResult:
    plan: DataRepairPlan
    executed: list[dict] = field(default_factory=list)
    success: bool = False
    message: str = ""


# ============ 主入口 ============

def diagnose_data_failure(
    message: str,
    traceback: str = "",
    console_log: str | None = None,
    fixture_name: str | None = None,
) -> DataRepairPlan | None:
    """从失败信息诊断 DATA_ERROR 子类。"""
    combined = f"{message}\n{traceback}"
    if console_log:
        combined += f"\n{console_log}"

    # 1. 唯一约束冲突
    constraint = _detect_unique_constraint(combined)
    if constraint:
        return _plan_clean_dirty_data(constraint)

    # 2. Fixture 初始化失败
    fixture_info = _detect_fixture_init_fail(combined, fixture_name)
    if fixture_info:
        return _plan_fixture_init(fixture_info)

    # 3. 测试用户被消费
    user_info = _detect_test_user_consumed(combined)
    if user_info:
        return _plan_test_user_regenerate(user_info)

    # 4. 外部 API 漂移
    api_info = _detect_external_api_drift(combined, console_log)
    if api_info:
        return _plan_external_api_mock(api_info)

    return None


def execute_data_repair(
    plan: DataRepairPlan,
    logger: AuditLogger,
    project_dir: Path,
    dry_run: bool = False,
    trigger_nodeid: str = "",
) -> DataRepairResult:
    """执行数据修复。"""
    result = DataRepairResult(plan=plan)
    all_success = True

    for action in plan.actions:
        kind = action.get("kind", "info")
        if kind == "sibling_skill":
            # 调起兄弟技能（如 api-testdata-cleaner）
            skill_name = action.get("skill", "")
            args = action.get("args", [])
            cmd_args = [sys.executable, "-m", skill_name.replace("-", "_")] + args
            exit_code, stdout, stderr, _ = logger.run_shell(
                cmd=cmd_args,
                cwd=project_dir,
                dry_run=dry_run,
                trigger_nodeid=trigger_nodeid,
                trigger_category="DATA_ERROR",
            )
            success = exit_code == 0
            result.executed.append({
                "action": "sibling_skill",
                "skill": skill_name,
                "args": args,
                "exit_code": exit_code,
                "stdout_tail": stdout[-200:],
                "stderr_tail": stderr[-200:],
                "success": success,
            })
            if not success:
                all_success = False
        elif kind == "shell":
            cmd = action.get("command", [])
            auto_run = action.get("auto_run", True)
            if not auto_run:
                logger.run_shell(
                    cmd=cmd,
                    cwd=project_dir,
                    dry_run=True,
                    trigger_nodeid=trigger_nodeid,
                    trigger_category="DATA_ERROR",
                )
                result.executed.append({
                    "action": "manual_shell_required",
                    "command": " ".join(cmd) if isinstance(cmd, list) else cmd,
                    "message": action.get("message", "需手动执行"),
                })
                all_success = False
                continue

            exit_code, stdout, stderr, _ = logger.run_shell(
                cmd=cmd,
                cwd=project_dir,
                dry_run=dry_run,
                trigger_nodeid=trigger_nodeid,
                trigger_category="DATA_ERROR",
            )
            success = exit_code == 0
            result.executed.append({
                "action": "shell",
                "command": " ".join(cmd) if isinstance(cmd, list) else cmd,
                "exit_code": exit_code,
                "success": success,
            })
            if not success:
                all_success = False
        elif kind in ("info", "warning"):
            result.executed.append({
                "action": kind,
                "message": action.get("message", ""),
            })
            if kind == "warning":
                all_success = False

    result.success = all_success
    result.message = "数据修复完成" if all_success else "部分修复或需人工介入"
    return result


# ============ 子类检测 ============

_UNIQUE_CONSTRAINT_PATTERNS = [
    # SQLite: UNIQUE constraint failed: users.email
    re.compile(r"IntegrityError.*?unique\s+constraint\s+failed:\s*([\w.]+)", re.IGNORECASE),
    # 通用 IntegrityError + unique constraint（无具体名字）
    re.compile(r"IntegrityError.*?unique\s+constraint", re.IGNORECASE),
    # PostgreSQL: UniqueViolation: duplicate key ... "users_email_idx"
    re.compile(r"UniqueViolation.*?\"([\w_]+)\"", re.IGNORECASE),
    # 通用：unique constraint failed "name"
    re.compile(r"unique\s+constraint.*?failed.*?\"([\w_]+)\"", re.IGNORECASE),
    # MySQL: duplicate key "name"
    re.compile(r"duplicate\s+key.*?\"([\w_]+)\"", re.IGNORECASE),
    # MySQL: Duplicate entry 'value' for key 'name'
    re.compile(r"Duplicate entry.*?'([^']+)'", re.IGNORECASE),
]


def _detect_unique_constraint(text: str) -> dict | None:
    for pattern in _UNIQUE_CONSTRAINT_PATTERNS:
        m = pattern.search(text)
        if m:
            constraint_name = m.group(1) if m.groups() else "unknown"
            return {"constraint": constraint_name, "raw": m.group(0)}
    return None


_FIXTURE_PATTERNS = [
    re.compile(r"fixture\s+['\"]([\w_]+)['\"].*?not\s+found", re.IGNORECASE),
    re.compile(r"fixture\s+['\"]([\w_]+)['\"].*?failed", re.IGNORECASE),
    re.compile(r"ERROR at setup of\s+([\w_]+)", re.IGNORECASE),
    re.compile(r"registered_user.*?not found", re.IGNORECASE),
]


def _detect_fixture_init_fail(text: str, fixture_hint: str | None = None) -> dict | None:
    """检测 fixture 初始化失败。"""
    for pattern in _FIXTURE_PATTERNS:
        m = pattern.search(text)
        if m:
            fixture_name = m.group(1) if m.groups() else (fixture_hint or "unknown")
            return {"fixture": fixture_name, "raw": m.group(0)}
    if fixture_hint:
        return {"fixture": fixture_hint, "raw": ""}
    return None


_TEST_USER_PATTERNS = [
    re.compile(r"user.*?(?:not found|deleted|disabled|locked)", re.IGNORECASE),
    re.compile(r"test_user_\d+.*?already consumed", re.IGNORECASE),
    re.compile(r"401.*?[Uu]nauthorized.*?[Ll]ogin", re.IGNORECASE),
    re.compile(r"账户.*?(?:不存在|已禁用|已锁定)", re.IGNORECASE),
]


def _detect_test_user_consumed(text: str) -> dict | None:
    for pattern in _TEST_USER_PATTERNS:
        m = pattern.search(text)
        if m:
            return {"reason": m.group(0)}
    return None


_EXTERNAL_API_PATTERNS = [
    re.compile(r"external api.*?(?:changed|drift|incompatible)", re.IGNORECASE),
    re.compile(r"(?:response|schema).*?validation.*?failed.*?api", re.IGNORECASE),
]


def _detect_external_api_drift(text: str, console_log: str | None = None) -> dict | None:
    for pattern in _EXTERNAL_API_PATTERNS:
        m = pattern.search(text)
        if m:
            return {"reason": m.group(0)}
    # console-log 中 4xx 频繁出现也可视为 API 漂移信号
    if console_log:
        if console_log.count("status=4") >= 3 or "## Network" in console_log and "422" in console_log:
            return {"reason": "console-log 显示多次 4xx"}
    return None


# ============ 修复计划构建 ============

def _plan_clean_dirty_data(info: dict) -> DataRepairPlan:
    constraint = info.get("constraint", "unknown")
    return DataRepairPlan(
        subkind="unique_constraint_conflict",
        diagnosis=f"唯一约束冲突：{constraint}（可能存在脏数据）",
        actions=[
            {
                "kind": "sibling_skill",
                "skill": "api-testdata-cleaner",
                "args": ["--target", constraint, "--mode", "duplicates"],
                "message": f"调用 api-testdata-cleaner 清理 {constraint} 重复数据",
            },
            {
                "kind": "info",
                "message": (
                    f"清理后重新执行测试。如仍失败：\n"
                    f"  1. 检查 fixture 是否使用了硬编码主键\n"
                    f"  2. 考虑在 fixture setup 中加 random suffix 避免冲突\n"
                    f"  3. 长期方案：每个测试用独立数据库 / schema"
                ),
            },
        ],
    )


def _plan_fixture_init(info: dict) -> DataRepairPlan:
    fixture = info.get("fixture", "unknown")
    return DataRepairPlan(
        subkind="fixture_init_fail",
        diagnosis=f"Fixture '{fixture}' 初始化失败",
        actions=[
            {
                "kind": "info",
                "message": (
                    f"建议排查：\n"
                    f"  1. 检查 tests/conftest.py 中 fixture '{fixture}' 的实现\n"
                    f"  2. 确认依赖的外部数据（DB / Redis / 文件）已就位\n"
                    f"  3. 若是 DB 种子数据缺失，执行 seed 脚本：\n"
                    f"     python scripts/seed_db.py  # 或项目约定的 seed 命令"
                ),
            },
            {
                "kind": "warning",
                "message": (
                    "fixture 失败原因多样（DB 未初始化、外部服务挂、网络问题），"
                    "本技能不会自动 seed 数据库（避免污染生产共享环境）。"
                ),
            },
        ],
    )


def _plan_test_user_regenerate(info: dict) -> DataRepairPlan:
    return DataRepairPlan(
        subkind="test_user_consumed",
        diagnosis=f"测试用户被消费或失效：{info.get('reason', '')}",
        actions=[
            {
                "kind": "info",
                "message": (
                    "建议：\n"
                    "  1. 在 pages 层加 setup 容错：注册新用户作为 fallback\n"
                    "  2. 调用 api-testdata-cleaner 清理已消费用户\n"
                    "  3. 长期方案：测试套件开始时统一执行 reset_users 脚本"
                ),
            },
            {
                "kind": "warning",
                "message": "需人工确认是否在 pages 层加注册 fallback（可能改变测试范围）",
            },
        ],
    )


def _plan_external_api_mock(info: dict) -> DataRepairPlan:
    return DataRepairPlan(
        subkind="external_api_drift",
        diagnosis=f"外部 API 漂移：{info.get('reason', '')}",
        actions=[
            {
                "kind": "info",
                "message": (
                    "建议：\n"
                    "  1. 在 tests/conftest.py 中加 responses / nosegicle mock\n"
                    "  2. 把 mock 数据放 tests/fixtures/api_responses/\n"
                    "  3. 长期方案：与 API 团队同步 schema 变更，引入契约测试"
                ),
            },
            {
                "kind": "warning",
                "message": "外部 API 漂移超出测试脚本范围，建议联系 API 团队",
            },
        ],
    )
