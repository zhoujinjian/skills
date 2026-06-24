"""Tests for env_repair.py — ENV_ERROR 自动修复."""
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from env_repair import (
    diagnose_env_failure,
    execute_env_repair,
    EnvRepairPlan,
    _detect_missing_playwright_browser,
    _detect_missing_python_package,
    _detect_port_conflict,
    _detect_service_unavailable,
    _module_to_package,
)
from audit_log import AuditLogger


# ============ 模块 → 包名映射 ============

def test_module_to_package_common_mappings():
    assert _module_to_package("yaml") == "pyyaml"
    assert _module_to_package("cv2") == "opencv-python"
    assert _module_to_package("PIL") == "Pillow"
    assert _module_to_package("sklearn") == "scikit-learn"
    assert _module_to_package("bs4") == "beautifulsoup4"


def test_module_to_package_passthrough():
    assert _module_to_package("playwright") == "playwright"
    assert _module_to_package("pytest_playwright") == "pytest_playwright"


def test_module_to_package_strips_submodule():
    assert _module_to_package("dotenv.main") == "python-dotenv"


# ============ Playwright 浏览器缺失 ============

def test_detect_playwright_browser_missing_chromium():
    msg = "Executable doesn't exist at .../chromium-1234/chrome"
    assert _detect_missing_playwright_browser(msg) == "chromium"


def test_detect_playwright_browser_install_hint():
    msg = "未安装，运行 `python3 -m playwright install firefox`"
    assert _detect_missing_playwright_browser(msg) == "firefox"


def test_detect_playwright_browser_normalize_chrome():
    msg = "BrowserType.launch: chrome was not found"
    assert _detect_missing_playwright_browser(msg) == "chromium"


def test_detect_playwright_browser_no_match():
    assert _detect_missing_playwright_browser("random error") is None


# ============ Python 包缺失 ============

def test_detect_python_package_import_error():
    msg = "ModuleNotFoundError: No module named 'requests'"
    assert _detect_missing_python_package(msg) == "requests"


def test_detect_python_package_double_quotes():
    msg = 'ModuleNotFoundError: No module named "yaml"'
    assert _detect_missing_python_package(msg) == "pyyaml"


def test_detect_python_package_no_match():
    assert _detect_missing_python_package("TimeoutError") is None


# ============ 端口冲突 ============

def test_detect_port_conflict_eaddrinuse():
    msg = "Error: Address already in use port 3000"
    info = _detect_port_conflict(msg)
    assert info is not None
    assert info["port"] == 3000


def test_detect_port_conflict_no_match():
    assert _detect_port_conflict("TimeoutError") is None


# ============ 服务不可用 ============

def test_detect_service_unavailable_econnrefused():
    msg = "net::ERR_CONNECTION_REFUSED 127.0.0.1:3000"
    info = _detect_service_unavailable(msg)
    assert info is not None
    assert info["host"] == "127.0.0.1"
    assert info["port"] == 3000


def test_detect_service_unavailable_no_match():
    assert _detect_service_unavailable("TimeoutError") is None


# ============ 主入口：diagnose_env_failure ============

def test_diagnose_playwright_browser_missing():
    msg = "playwright._impl._errors.Error: BrowserType.launch: Executable doesn't exist (chromium)"
    plan = diagnose_env_failure(msg)
    assert plan is not None
    assert plan.subkind == "missing_playwright_browser"
    assert any("playwright" in " ".join(a.get("command", [])) for a in plan.actions if a.get("kind") == "shell")


def test_diagnose_python_package_missing():
    msg = "ModuleNotFoundError: No module named 'requests'"
    plan = diagnose_env_failure(msg)
    assert plan is not None
    assert plan.subkind == "missing_python_package"


def test_diagnose_returns_none_for_non_env():
    plan = diagnose_env_failure("TimeoutError: 10000ms exceeded")
    assert plan is None


# ============ 执行：execute_env_repair ============

def test_execute_env_repair_dry_run_executes_nothing(tmp_path):
    logger = AuditLogger(log_path=tmp_path / "audit.log")
    plan = EnvRepairPlan(
        subkind="missing_python_package",
        diagnosis="...",
        actions=[{
            "kind": "shell",
            "command": ["echo", "should-not-run"],
            "auto_run": True,
        }],
    )
    with mock.patch("env_repair.AuditLogger.run_shell") as mock_run:
        mock_run.return_value = (0, "dry-run output", "", mock.Mock())
        result = execute_env_repair(
            plan=plan,
            logger=logger,
            project_dir=tmp_path,
            dry_run=True,
        )
    # dry_run=True 时仍走 logger.run_shell，但 logger 内部不执行
    assert len(result.executed) == 1
    assert result.executed[0]["action"] == "shell"


def test_execute_env_repair_real_run(tmp_path):
    logger = AuditLogger(log_path=tmp_path / "audit.log")
    plan = EnvRepairPlan(
        subkind="missing_python_package",
        diagnosis="...",
        actions=[{
            "kind": "shell",
            "command": ["echo", "hello"],
            "auto_run": True,
        }],
    )
    result = execute_env_repair(
        plan=plan,
        logger=logger,
        project_dir=tmp_path,
        dry_run=False,
    )
    assert len(result.executed) == 1
    assert result.executed[0]["exit_code"] == 0
    assert result.success is True


def test_execute_env_repair_warning_blocks_success(tmp_path):
    logger = AuditLogger(log_path=tmp_path / "audit.log")
    plan = EnvRepairPlan(
        subkind="port_conflict",
        diagnosis="...",
        actions=[{
            "kind": "warning",
            "message": "端口被占用",
        }],
    )
    result = execute_env_repair(
        plan=plan,
        logger=logger,
        project_dir=tmp_path,
    )
    assert result.success is False
    assert "人工" in result.message or "介入" in result.message


def test_execute_env_repair_manual_action_recorded_but_not_run(tmp_path):
    logger = AuditLogger(log_path=tmp_path / "audit.log")
    plan = EnvRepairPlan(
        subkind="port_conflict",
        diagnosis="...",
        actions=[{
            "kind": "shell",
            "command": ["lsof", "-i", ":3000"],
            "auto_run": False,  # 手动
            "message": "用户手动执行",
        }],
    )
    with mock.patch("env_repair.AuditLogger.run_shell") as mock_run:
        m = mock.Mock()
        m.return_value = (0, "", "", mock.Mock())
        mock_run.return_value = m
        result = execute_env_repair(
            plan=plan,
            logger=logger,
            project_dir=tmp_path,
        )
    # 手动动作应记录但不计入 success
    assert any(e.get("action") == "manual_shell_required" for e in result.executed)
    assert result.success is False


# ============ 真实执行（hit subprocess）============

def test_execute_real_echo_command(tmp_path):
    """真实执行 echo，验证 audit log 落盘。"""
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path=log_path)
    plan = EnvRepairPlan(
        subkind="missing_playwright_browser",
        diagnosis="...",
        actions=[{
            "kind": "shell",
            "command": ["echo", "installing chromium"],
            "auto_run": True,
        }],
    )
    result = execute_env_repair(
        plan=plan, logger=logger, project_dir=tmp_path,
    )
    assert result.success is True
    # audit.log 至少有 1 条 shell_command 记录
    assert log_path.exists()
    log_content = log_path.read_text()
    assert "installing chromium" in log_content
