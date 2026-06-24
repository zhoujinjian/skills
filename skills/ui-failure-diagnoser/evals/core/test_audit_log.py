"""Tests for audit_log.py — 副作用操作审计."""
import json
import sys
import subprocess
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from audit_log import AuditLogger, AuditRecord, default_log_path


# ============ 基础结构 ============

def test_audit_record_dataclass_has_required_fields():
    r = AuditRecord(
        timestamp="2026-06-23T10:00:00",
        kind="shell_command",
        command="echo hi",
    )
    assert r.kind == "shell_command"
    assert r.exit_code is None
    assert r.duration_sec == 0.0


def test_default_log_path_under_project(tmp_path):
    p = default_log_path(tmp_path)
    assert p.name == "audit.log"
    assert ".ui-failure-diagnoser" in str(p)


# ============ 日志写入 ============

def test_log_writes_jsonl_line(tmp_path):
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path=log_path)
    logger.log(AuditRecord(
        timestamp="2026-06-23T10:00:00",
        kind="file_modify",
        command="patched base_page.py",
    ))
    content = log_path.read_text()
    record = json.loads(content.strip())
    assert record["kind"] == "file_modify"
    assert record["command"] == "patched base_page.py"


def test_log_disabled_does_not_write_file(tmp_path):
    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path=log_path, enabled=False)
    logger.log(AuditRecord(
        timestamp="x",
        kind="shell_command",
        command="x",
    ))
    assert not log_path.exists()
    # 但记录仍缓存在内存
    assert len(logger.records) == 0  # disabled 直接 short-circuit


def test_log_file_modify_helper(tmp_path):
    log_path = tmp_path / "a.log"
    logger = AuditLogger(log_path=log_path)
    logger.log_file_modify(
        target=tmp_path / "page.py",
        description="rewrote timeout",
        trigger_nodeid="tests/x.py::t",
        trigger_category="TIMEOUT_ERROR",
    )
    record = json.loads(log_path.read_text().strip())
    assert record["kind"] == "file_modify"
    assert "rewrote timeout" in record["command"]
    assert record["trigger_nodeid"] == "tests/x.py::t"
    assert record["trigger_category"] == "TIMEOUT_ERROR"


# ============ run_shell ============

def test_run_shell_executes_and_logs(tmp_path):
    log_path = tmp_path / "a.log"
    logger = AuditLogger(log_path=log_path)
    exit_code, stdout, stderr, record = logger.run_shell(
        cmd=["echo", "hello"],
        cwd=tmp_path,
    )
    assert exit_code == 0
    assert "hello" in stdout
    assert record.exit_code == 0
    assert record.duration_sec >= 0
    # 日志已落盘
    log_record = json.loads(log_path.read_text().strip())
    assert log_record["command"] == "echo hello"
    assert log_record["exit_code"] == 0


def test_run_shell_dry_run_does_not_execute(tmp_path):
    log_path = tmp_path / "a.log"
    logger = AuditLogger(log_path=log_path)
    with mock.patch("audit_log.subprocess.run") as mock_run:
        mock_run.side_effect = AssertionError("should not run")
        exit_code, stdout, stderr, record = logger.run_shell(
            cmd=["echo", "hi"],
            dry_run=True,
        )
    assert exit_code == 0
    assert "DRY-RUN" in stderr
    assert record.exit_code is None
    mock_run.assert_not_called()


def test_run_shell_captures_nonzero_exit(tmp_path):
    logger = AuditLogger(log_path=tmp_path / "a.log")
    exit_code, stdout, stderr, record = logger.run_shell(
        cmd=["sh", "-c", "exit 42"],
    )
    assert exit_code == 42
    assert record.exit_code == 42


def test_run_shell_captures_timeout(tmp_path):
    logger = AuditLogger(log_path=tmp_path / "a.log")
    exit_code, stdout, stderr, record = logger.run_shell(
        cmd=["sleep", "10"],
        timeout_sec=1,
    )
    assert exit_code == -1
    assert "TIMEOUT" in stderr
    assert record.exit_code == -1


def test_run_shell_captures_command_not_found(tmp_path):
    logger = AuditLogger(log_path=tmp_path / "a.log")
    exit_code, stdout, stderr, record = logger.run_shell(
        cmd=["this-command-does-not-exist-xyz"],
    )
    assert exit_code == -2
    assert "COMMAND NOT FOUND" in stderr


def test_run_shell_truncates_long_stdout(tmp_path):
    """stdout 末尾超过 500 字符时只保留 tail 500。"""
    logger = AuditLogger(log_path=tmp_path / "a.log")
    cmd = ["sh", "-c", "printf 'a%.0s' {1..2000}"]  # 输出 2000 个 a
    _, _, _, record = logger.run_shell(cmd=cmd)
    assert len(record.stdout_tail) <= 500


# ============ trigger 上下文 ============

def test_run_shell_propagates_trigger_context(tmp_path):
    log_path = tmp_path / "a.log"
    logger = AuditLogger(log_path=log_path)
    logger.run_shell(
        cmd=["echo", "hi"],
        trigger_nodeid="tests/auth/test_login.py::TestX::test_a",
        trigger_category="ENV_ERROR",
    )
    record = json.loads(log_path.read_text().strip())
    assert record["trigger_nodeid"] == "tests/auth/test_login.py::TestX::test_a"
    assert record["trigger_category"] == "ENV_ERROR"


# ============ invoke_sibling_skill ============

def test_invoke_sibling_skill_marks_kind(tmp_path):
    log_path = tmp_path / "a.log"
    logger = AuditLogger(log_path=log_path)
    with mock.patch("audit_log.subprocess.run") as mock_run:
        m = mock.Mock()
        m.returncode = 0
        m.stdout = "ok"
        m.stderr = ""
        mock_run.return_value = m
        exit_code, _, _, record = logger.invoke_sibling_skill(
            skill_name="api-testdata-cleaner",
            args=["--target", "users"],
        )
    assert exit_code == 0
    assert record.kind == "sibling_skill"
    assert "api-testdata-cleaner" in record.command


# ============ 多条日志追加 ============

def test_multiple_logs_append_to_same_file(tmp_path):
    log_path = tmp_path / "a.log"
    logger = AuditLogger(log_path=log_path)
    for i in range(3):
        logger.log(AuditRecord(timestamp=f"t{i}", kind="x", command=f"c{i}"))
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 3
