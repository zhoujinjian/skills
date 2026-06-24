"""audit_log.py — 副作用操作审计日志

所有 shell_command、文件修改、调兄弟技能等副作用操作都通过本模块记录。
目的：自动化执行后可追溯，失败可回查根因。

日志格式：JSONL（每行一条记录），便于 grep + jq 分析。
默认路径：项目内 .ui-failure-diagnoser/audit.log（跟随 cwd）
       或 --audit-log-path 指定。

记录字段：
    timestamp    ISO 8601 时间戳
    kind         操作类型（shell_command / file_modify / sibling_skill / external_api）
    command      具体命令或操作描述
    cwd          执行时的工作目录
    exit_code    退出码（成功 0，失败 非 0，未执行 null）
    duration_sec 耗时
    stdout_tail  stdout 末尾 N 字符（默认 500，避免日志爆炸）
    stderr_tail  stderr 末尾 N 字符
    trigger_nodeid  触发该操作的失败用例（可空）
    trigger_category  触发该操作的失败分类
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


DEFAULT_LOG_DIR_NAME = ".ui-failure-diagnoser"
DEFAULT_LOG_FILE_NAME = "audit.log"
DEFAULT_TAIL_CHARS = 500


@dataclass
class AuditRecord:
    """单条审计记录。"""
    timestamp: str
    kind: str  # shell_command / file_modify / sibling_skill / external_api
    command: str
    cwd: str = ""
    exit_code: int | None = None
    duration_sec: float = 0.0
    stdout_tail: str = ""
    stderr_tail: str = ""
    trigger_nodeid: str = ""
    trigger_category: str = ""


class AuditLogger:
    """审计日志写入器。所有副作用操作都应通过本类的方法调用。"""

    def __init__(self, log_path: Path | None = None, enabled: bool = True):
        """Args:
            log_path: 日志文件路径。None 时不写文件（仅返回 AuditRecord）。
            enabled: False 时完全不记录（用于 dry-run 或测试）
        """
        self.log_path = log_path
        self.enabled = enabled
        self.records: list[AuditRecord] = []
        if log_path and enabled:
            log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, record: AuditRecord) -> AuditRecord:
        """记录一条事件。dry-run 或 disabled 时只缓存不写文件。"""
        if not self.enabled:
            return record
        self.records.append(record)
        if self.log_path:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
        return record

    def log_file_modify(
        self,
        target: Path,
        description: str,
        trigger_nodeid: str = "",
        trigger_category: str = "",
    ) -> AuditRecord:
        """记录文件修改（不执行，只记录；执行由调用方完成）。"""
        return self.log(AuditRecord(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            kind="file_modify",
            command=f"{description}: {target}",
            cwd=str(target.parent) if target.parent else "",
            trigger_nodeid=trigger_nodeid,
            trigger_category=trigger_category,
        ))

    def run_shell(
        self,
        cmd: list[str] | str,
        cwd: Path | None = None,
        timeout_sec: int = 300,
        trigger_nodeid: str = "",
        trigger_category: str = "",
        dry_run: bool = False,
    ) -> tuple[int, str, str, AuditRecord]:
        """执行 shell 命令并自动记录。

        Args:
            cmd: 命令（list 推荐）或字符串
            cwd: 工作目录
            timeout_sec: 超时
            trigger_nodeid/category: 触发该命令的上下文
            dry_run: True 时只记录不执行（exit_code=None）

        Returns:
            (exit_code, stdout, stderr, audit_record)
        """
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        cmd_list = cmd if isinstance(cmd, list) else cmd.split()
        start = time.time()
        timestamp = datetime.now().isoformat(timespec="seconds")

        if dry_run:
            record = AuditRecord(
                timestamp=timestamp,
                kind="shell_command",
                command=cmd_str,
                cwd=str(cwd) if cwd else "",
                exit_code=None,
                duration_sec=0.0,
                stdout_tail="",
                stderr_tail="[DRY-RUN] not executed",
                trigger_nodeid=trigger_nodeid,
                trigger_category=trigger_category,
            )
            self.log(record)
            return 0, "", "[DRY-RUN] not executed", record

        try:
            result = subprocess.run(
                cmd_list,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            exit_code = result.returncode
            stdout = result.stdout or ""
            stderr = result.stderr or ""
        except subprocess.TimeoutExpired as e:
            exit_code = -1
            stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
            stderr = f"[TIMEOUT after {timeout_sec}s] {(e.stderr or '') if isinstance(e.stderr, str) else ''}"
        except FileNotFoundError as e:
            exit_code = -2
            stdout = ""
            stderr = f"[COMMAND NOT FOUND] {e}"

        duration = time.time() - start
        record = AuditRecord(
            timestamp=timestamp,
            kind="shell_command",
            command=cmd_str,
            cwd=str(cwd) if cwd else "",
            exit_code=exit_code,
            duration_sec=round(duration, 2),
            stdout_tail=stdout[-DEFAULT_TAIL_CHARS:],
            stderr_tail=stderr[-DEFAULT_TAIL_CHARS:],
            trigger_nodeid=trigger_nodeid,
            trigger_category=trigger_category,
        )
        self.log(record)
        return exit_code, stdout, stderr, record

    def invoke_sibling_skill(
        self,
        skill_name: str,
        args: list[str],
        cwd: Path | None = None,
        trigger_nodeid: str = "",
        trigger_category: str = "",
        dry_run: bool = False,
    ) -> tuple[int, str, str, AuditRecord]:
        """调起兄弟技能（如 api-testdata-cleaner）。

        兄弟技能入口约定：<skill_dir>/scripts/run.sh 或 Python 模块。
        本方法只做命令拼装，实际调度由调用方决定。
        """
        cmd = [sys.executable, "-m", skill_name.replace("-", "_")] + args
        record_kind_override = "sibling_skill"
        exit_code, stdout, stderr, record = self.run_shell(
            cmd=cmd,
            cwd=cwd,
            trigger_nodeid=trigger_nodeid,
            trigger_category=trigger_category,
            dry_run=dry_run,
        )
        # 改 kind 为 sibling_skill
        record.kind = record_kind_override
        record.command = f"[sibling:{skill_name}] " + record.command
        return exit_code, stdout, stderr, record


def default_log_path(project_dir: Path | None = None) -> Path:
    """默认日志路径：项目内 .ui-failure-diagnoser/audit.log。"""
    base = project_dir or Path.cwd()
    return base / DEFAULT_LOG_DIR_NAME / DEFAULT_LOG_FILE_NAME
