"""Tests for data_repair.py — DATA_ERROR 自动修复."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from data_repair import (
    diagnose_data_failure,
    execute_data_repair,
    DataRepairPlan,
    _detect_unique_constraint,
    _detect_fixture_init_fail,
    _detect_test_user_consumed,
    _detect_external_api_drift,
)
from audit_log import AuditLogger


# ============ unique constraint 检测 ============

def test_detect_unique_constraint_sqlite():
    msg = "sqlite3.IntegrityError: UNIQUE constraint failed: users.email"
    info = _detect_unique_constraint(msg)
    assert info is not None
    assert "users.email" in info["constraint"]


def test_detect_unique_constraint_mysql():
    msg = "Duplicate entry 'test@x.com' for key 'users.email'"
    info = _detect_unique_constraint(msg)
    assert info is not None


def test_detect_unique_constraint_postgres():
    msg = 'UniqueViolation: duplicate key value violates unique constraint "users_email_idx"'
    info = _detect_unique_constraint(msg)
    assert info is not None


def test_detect_unique_constraint_no_match():
    assert _detect_unique_constraint("TimeoutError") is None


# ============ fixture 检测 ============

def test_detect_fixture_not_found():
    msg = "fixture 'registered_user' not found"
    info = _detect_fixture_init_fail(msg)
    assert info is not None
    assert info["fixture"] == "registered_user"


def test_detect_fixture_error_at_setup():
    msg = "ERROR at setup of test_login_with_valid_user"
    info = _detect_fixture_init_fail(msg)
    assert info is not None


def test_detect_fixture_hint_fallback():
    info = _detect_fixture_init_fail("some random error", fixture_hint="my_user_fixture")
    assert info is not None
    assert info["fixture"] == "my_user_fixture"


def test_detect_fixture_no_match():
    assert _detect_fixture_init_fail("TimeoutError") is None


# ============ 测试用户消费 ============

def test_detect_test_user_not_found():
    msg = "user test_user_42 not found in DB"
    info = _detect_test_user_consumed(msg)
    assert info is not None


def test_detect_test_user_chinese():
    msg = "账户 已禁用，请联系管理员"
    info = _detect_test_user_consumed(msg)
    assert info is not None


def test_detect_test_user_no_match():
    assert _detect_test_user_consumed("TimeoutError") is None


# ============ 外部 API 漂移 ============

def test_detect_external_api_explicit():
    msg = "external api response schema changed"
    info = _detect_external_api_drift(msg)
    assert info is not None


def test_detect_external_api_4xx_in_console():
    """console-log 中有多次 4xx 视为 API 漂移。"""
    console_log = """
## Network
  GET /api/users  status=422
  POST /api/login  status=422
  GET /api/products  status=422
"""
    info = _detect_external_api_drift("TimeoutError", console_log=console_log)
    assert info is not None


# ============ 主入口 diagnose_data_failure ============

def test_diagnose_returns_unique_constraint_plan():
    msg = "IntegrityError: UNIQUE constraint failed: users.email"
    plan = diagnose_data_failure(msg)
    assert plan is not None
    assert plan.subkind == "unique_constraint_conflict"
    # 应当有 sibling_skill 动作
    has_skill = any(a.get("kind") == "sibling_skill" for a in plan.actions)
    assert has_skill


def test_diagnose_returns_fixture_plan():
    msg = "fixture 'registered_user' not found"
    plan = diagnose_data_failure(msg)
    assert plan is not None
    assert plan.subkind == "fixture_init_fail"


def test_diagnose_returns_none_for_non_data():
    plan = diagnose_data_failure("TimeoutError")
    assert plan is None


# ============ 执行 ============

def test_execute_data_repair_dry_run_records(tmp_path):
    logger = AuditLogger(log_path=tmp_path / "audit.log")
    plan = DataRepairPlan(
        subkind="unique_constraint_conflict",
        diagnosis="...",
        actions=[{
            "kind": "sibling_skill",
            "skill": "api-testdata-cleaner",
            "args": ["--target", "users"],
        }],
    )
    with mock.patch("data_repair.AuditLogger.run_shell") as mock_run:
        mock_run.return_value = (0, "cleaned 3 rows", "", mock.Mock())
        result = execute_data_repair(
            plan=plan,
            logger=logger,
            project_dir=tmp_path,
            dry_run=True,
        )
    assert len(result.executed) == 1
    assert result.executed[0]["action"] == "sibling_skill"


def test_execute_data_repair_warning_marks_unsuccess(tmp_path):
    logger = AuditLogger(log_path=tmp_path / "audit.log")
    plan = DataRepairPlan(
        subkind="fixture_init_fail",
        diagnosis="...",
        actions=[{
            "kind": "warning",
            "message": "需手动",
        }],
    )
    result = execute_data_repair(plan=plan, logger=logger, project_dir=tmp_path)
    assert result.success is False


def test_execute_data_repair_real_run_with_echo(tmp_path):
    """用真实 shell 调用 echo 模拟兄弟技能成功。"""
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path=log_path)
    plan = DataRepairPlan(
        subkind="unique_constraint_conflict",
        diagnosis="...",
        actions=[{
            "kind": "shell",  # 用 shell 测真实执行
            "command": ["echo", "cleanup done"],
            "auto_run": True,
        }],
    )
    result = execute_data_repair(plan=plan, logger=logger, project_dir=tmp_path)
    assert result.success is True
    assert log_path.exists()
