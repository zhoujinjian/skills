"""verify_fix.py — 单用例重跑验证

subprocess 调起 pytest 重跑修复后的单个用例，解析退出码判断通过/失败/错误/超时。
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VerifyResult:
    """验证结果。"""
    status: str  # passed / failed / error / timeout
    pytest_exit_code: int
    duration_sec: float
    stdout: str = ""
    stderr: str = ""


def verify_single_test(
    project_dir: Path,
    nodeid: str,
    base_url: str | None = None,
    browser: str | None = None,
    timeout_sec: int = 300,
) -> VerifyResult:
    """重跑单个测试用例。

    Args:
        project_dir: 测试项目根目录（cwd）
        nodeid: pytest nodeid（file::Class::test 或 file::test）
        base_url: 可选，--base-url 参数
        browser: 可选，--browser 参数
        timeout_sec: 超时秒数（默认 300s = 5 分钟，足够 UI 测试）

    Returns:
        VerifyResult
    """
    cmd: list[str] = [sys.executable, "-m", "pytest", nodeid, "-v"]
    if base_url:
        cmd.extend(["--base-url", base_url])
    if browser:
        cmd.extend(["--browser", browser])

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as e:
        return VerifyResult(
            status="timeout",
            pytest_exit_code=-1,
            duration_sec=timeout_sec,
            stdout=e.stdout or "" if isinstance(e.stdout, str) else "",
            stderr=e.stderr or "" if isinstance(e.stderr, str) else "",
        )

    duration = time.time() - start
    status_map = {
        0: "passed",
        1: "failed",
    }
    status = status_map.get(result.returncode, "error")

    return VerifyResult(
        status=status,
        pytest_exit_code=result.returncode,
        duration_sec=duration,
        stdout=result.stdout,
        stderr=result.stderr,
    )
