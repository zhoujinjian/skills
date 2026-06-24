"""env_repair.py — ENV_ERROR 环境问题自动修复

5 个子类：
    missing_playwright_browser  → python -m playwright install <browser>
    missing_python_package      → pip install <package>
    service_unavailable         → 检测端口 + 提示启动命令
    port_conflict               → 识别占用进程 + 提示 kill
    version_incompatible        → pip install --upgrade <package>

所有副作用操作都通过 AuditLogger.run_shell，写入 audit.log。
"""
from __future__ import annotations

import re
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from audit_log import AuditLogger  # noqa: E402


# ============ 数据结构 ============

@dataclass
class EnvRepairPlan:
    """环境修复计划。"""
    subkind: str  # missing_playwright_browser / missing_python_package / ...
    diagnosis: str  # 诊断说明
    actions: list[dict] = field(default_factory=list)
    # actions 元素：{"kind": "shell"|"info"|"warning", "command"|"message": ..., "auto_run": bool}


@dataclass
class EnvRepairResult:
    """环境修复执行结果。"""
    plan: EnvRepairPlan
    executed: list[dict] = field(default_factory=list)  # 已执行的动作
    success: bool = False
    message: str = ""


# ============ 主入口 ============

def diagnose_env_failure(
    message: str,
    traceback: str = "",
    console_log: str | None = None,
) -> EnvRepairPlan | None:
    """从失败信息诊断 ENV_ERROR 子类。

    Args:
        message: JUnit failure message
        traceback: 完整 traceback
        console_log: console-logs 内容

    Returns:
        EnvRepairPlan 或 None（非 ENV_ERROR）
    """
    combined = f"{message}\n{traceback}"
    if console_log:
        combined += f"\n{console_log}"

    # 1. Playwright 浏览器未安装
    browser = _detect_missing_playwright_browser(combined)
    if browser:
        return _plan_install_playwright_browser(browser)

    # 2. Python 包缺失
    package = _detect_missing_python_package(combined)
    if package:
        return _plan_install_python_package(package)

    # 3. 端口冲突
    port_info = _detect_port_conflict(combined)
    if port_info:
        return _plan_port_conflict(port_info)

    # 4. 服务不可用（ECONNREFUSED）
    service_info = _detect_service_unavailable(combined)
    if service_info:
        return _plan_service_unavailable(service_info)

    # 5. 版本不兼容
    version_info = _detect_version_incompatible(combined)
    if version_info:
        return _plan_version_incompatible(version_info)

    return None


def execute_env_repair(
    plan: EnvRepairPlan,
    logger: AuditLogger,
    project_dir: Path,
    dry_run: bool = False,
    trigger_nodeid: str = "",
) -> EnvRepairResult:
    """执行环境修复计划。

    auto_run=True 的动作会通过 AuditLogger.run_shell 真实执行（除非 dry_run）。
    auto_run=False 的只记录到 audit log，提示用户手动执行。
    """
    result = EnvRepairResult(plan=plan)
    all_success = True

    for action in plan.actions:
        kind = action.get("kind", "info")
        if kind == "shell":
            cmd = action.get("command", [])
            if not cmd:
                continue
            auto_run = action.get("auto_run", True)
            if not auto_run:
                # 仅记录建议
                logger.run_shell(
                    cmd=cmd,
                    cwd=project_dir,
                    dry_run=True,
                    trigger_nodeid=trigger_nodeid,
                    trigger_category="ENV_ERROR",
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
                trigger_category="ENV_ERROR",
            )
            success = exit_code == 0
            result.executed.append({
                "action": "shell",
                "command": " ".join(cmd) if isinstance(cmd, list) else cmd,
                "exit_code": exit_code,
                "stdout_tail": stdout[-200:],
                "stderr_tail": stderr[-200:],
                "success": success,
            })
            if not success:
                all_success = False
        elif kind == "info":
            result.executed.append({
                "action": "info",
                "message": action.get("message", ""),
            })
        elif kind == "warning":
            result.executed.append({
                "action": "warning",
                "message": action.get("message", ""),
            })
            # warning 通常意味着不能自动修
            all_success = False

    result.success = all_success
    result.message = "修复完成" if all_success else "部分修复或需人工介入"
    return result


# ============ 子类检测 ============

_PLAYWRIGHT_BROWSER_PATTERNS = [
    (re.compile(r"playwright.*install\s+(chromium|firefox|webkit)", re.IGNORECASE), None),
    (re.compile(r"browser.*was not found.*?(chromium|firefox|webkit|chrome)", re.IGNORECASE), None),
    (re.compile(r"Executable doesn't exist.*?(chromium|firefox|webkit|chrome)", re.IGNORECASE), None),
    (re.compile(r"BrowserType\.launch.*?(chromium|firefox|webkit|chrome)", re.IGNORECASE), None),
]


def _detect_missing_playwright_browser(text: str) -> str | None:
    """检测 Playwright 浏览器缺失。"""
    for pattern, _ in _PLAYWRIGHT_BROWSER_PATTERNS:
        m = pattern.search(text)
        if m:
            browser = m.group(1).lower()
            # chrome → chromium（Playwright 内部名）
            if browser == "chrome":
                browser = "chromium"
            return browser
    # 通用关键字（无具体浏览器名）
    if "playwright install" in text.lower():
        return "chromium"  # 默认推荐
    return None


_PACKAGE_PATTERNS = [
    re.compile(r"ModuleNotFoundError:\s+No module named '([^']+)'", re.IGNORECASE),
    re.compile(r"ImportError:\s+No module named '?([\w.]+)'?", re.IGNORECASE),
    re.compile(r"ModuleNotFoundError:\s+No module named \"([^\"]+)\"", re.IGNORECASE),
]


def _detect_missing_python_package(text: str) -> str | None:
    """检测 Python 包缺失（ImportError / ModuleNotFoundError）。"""
    for pattern in _PACKAGE_PATTERNS:
        m = pattern.search(text)
        if m:
            module = m.group(1)
            # 模块名 → 包名映射（处理常见不一致）
            return _module_to_package(module)
    return None


_MODULE_TO_PACKAGE = {
    "yaml": "pyyaml",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "pil": "Pillow",
    "sklearn": "scikit-learn",
    "OpenSSL": "pyOpenSSL",
    "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "jwt": "PyJWT",
    "attr": "attrs",
}


def _module_to_package(module: str) -> str:
    """Python 模块名 → pip 包名映射。"""
    # 取顶级模块（去掉 .xxx 子模块）
    top = module.split(".")[0]
    return _MODULE_TO_PACKAGE.get(top, top)


_PORT_CONFLICT_PATTERNS = [
    re.compile(r"Address already in use.*?port\s*(\d+)", re.IGNORECASE),
    re.compile(r"EADDRINUSE.*?(\d+)", re.IGNORECASE),
    re.compile(r"port\s*(\d+).*?already.*?in.*?use", re.IGNORECASE),
]


def _detect_port_conflict(text: str) -> dict | None:
    """检测端口冲突。"""
    for pattern in _PORT_CONFLICT_PATTERNS:
        m = pattern.search(text)
        if m:
            return {"port": int(m.group(1))}
    return None


_SERVICE_UNAVAILABLE_PATTERNS = [
    re.compile(r"ECONNREFUSED.*?(\d+\.\d+\.\d+\.\d+):(\d+)", re.IGNORECASE),
    re.compile(r"Connection refused.*?(\d+\.\d+\.\d+\.\d+):(\d+)", re.IGNORECASE),
    re.compile(r"ERR_CONNECTION_REFUSED.*?(\d+\.\d+\.\d+\.\d+):(\d+)", re.IGNORECASE),
    re.compile(r"localhost:(\d+).*?not reachable", re.IGNORECASE),
]


def _detect_service_unavailable(text: str) -> dict | None:
    """检测服务不可用（ECONNREFUSED / 连接被拒）。"""
    for pattern in _SERVICE_UNAVAILABLE_PATTERNS:
        m = pattern.search(text)
        if m:
            groups = m.groups()
            if len(groups) >= 2:
                return {"host": groups[0], "port": int(groups[1])}
            return {"host": "127.0.0.1", "port": int(groups[0])}
    return None


_VERSION_INCOMPATIBLE_PATTERNS = [
    re.compile(r"playwright.*?version.*?(incompatible|mismatch|too old)", re.IGNORECASE),
    re.compile(r"requires\s+([\w-]+)\s*>=\s*([\d.]+).*?but you have\s+([\d.]+)", re.IGNORECASE),
]


def _detect_version_incompatible(text: str) -> dict | None:
    """检测版本不兼容。"""
    for pattern in _VERSION_INCOMPATIBLE_PATTERNS:
        m = pattern.search(text)
        if m:
            return {
                "package": "playwright",  # 默认
                "detail": m.group(0),
            }
    return None


# ============ 修复计划构建 ============

def _plan_install_playwright_browser(browser: str) -> EnvRepairPlan:
    return EnvRepairPlan(
        subkind="missing_playwright_browser",
        diagnosis=f"Playwright 浏览器 {browser} 未安装",
        actions=[
            {
                "kind": "shell",
                "command": [sys.executable, "-m", "playwright", "install", browser],
                "auto_run": True,
                "message": f"自动安装 Playwright {browser}",
            },
            {
                "kind": "info",
                "message": (
                    f"安装完成后重新运行测试。如仍有问题，可尝试：\n"
                    f"  {sys.executable} -m playwright install-deps {browser}  # 系统依赖（Linux）"
                ),
            },
        ],
    )


def _plan_install_python_package(package: str) -> EnvRepairPlan:
    return EnvRepairPlan(
        subkind="missing_python_package",
        diagnosis=f"Python 包 {package} 缺失",
        actions=[
            {
                "kind": "shell",
                "command": [sys.executable, "-m", "pip", "install", package],
                "auto_run": True,
                "message": f"自动安装 Python 包 {package}",
            },
            {
                "kind": "info",
                "message": (
                    "建议同时检查 requirements.txt / pyproject.toml 是否声明该依赖，"
                    "避免下次环境重建时再次缺失。"
                ),
            },
        ],
    )


def _plan_port_conflict(info: dict) -> EnvRepairPlan:
    port = info["port"]
    return EnvRepairPlan(
        subkind="port_conflict",
        diagnosis=f"端口 {port} 被占用",
        actions=[
            {
                "kind": "shell",
                "command": ["lsof", "-i", f":{port}"],
                "auto_run": True,
                "message": f"自动检测占用 {port} 的进程",
            },
            {
                "kind": "warning",
                "message": (
                    f"端口 {port} 已被占用。请根据上面 lsof 输出决定：\n"
                    f"  1. kill -9 <PID>  终止占用进程（谨慎！）\n"
                    f"  2. 修改测试使用的端口到其他空闲端口\n"
                    f"  3. 等待占用进程自然退出\n"
                    f"本技能不会自动 kill 进程（避免误杀系统服务）。"
                ),
            },
        ],
    )


def _plan_service_unavailable(info: dict) -> EnvRepairPlan:
    host = info.get("host", "127.0.0.1")
    port = info.get("port", 0)
    # 推测服务类型
    service_hint = _guess_service_by_port(port)
    return EnvRepairPlan(
        subkind="service_unavailable",
        diagnosis=f"服务 {host}:{port} 不可达{f'（疑似 {service_hint}）' if service_hint else ''}",
        actions=[
            {
                "kind": "shell",
                "command": ["nc", "-z", host, str(port)],
                "auto_run": True,
                "message": f"再次探测 {host}:{port}",
            },
            {
                "kind": "info",
                "message": (
                    f"建议手动启动服务：\n"
                    + _service_start_hint(port, host)
                ),
            },
        ],
    )


def _guess_service_by_port(port: int) -> str | None:
    common = {
        3000: "Node.js dev server",
        3001: "Node.js dev server (alt)",
        4200: "Angular dev server",
        5000: "Flask dev server",
        5173: "Vite dev server",
        8000: "Django / Flask",
        8080: "通用 HTTP",
        8888: "Jupyter",
        9000: "PHP-FPM / 通用",
        27017: "MongoDB",
        3306: "MySQL",
        5432: "PostgreSQL",
        6379: "Redis",
    }
    return common.get(port)


def _service_start_hint(port: int, host: str) -> str:
    """根据端口推测启动命令。"""
    hints = {
        3000: "  cd <frontend> && npm run dev",
        5173: "  cd <frontend> && npm run dev",
        8000: "  cd <backend> && python manage.py runserver  (或 flask run)",
        8080: "  cd <backend> && npm run start  /  java -jar app.jar",
    }
    return hints.get(port, f"  找到对应项目目录并启动开发服务器（监听 {host}:{port}）")


def _plan_version_incompatible(info: dict) -> EnvRepairPlan:
    package = info.get("package", "playwright")
    return EnvRepairPlan(
        subkind="version_incompatible",
        diagnosis=f"{package} 版本不兼容：{info.get('detail', '')}",
        actions=[
            {
                "kind": "shell",
                "command": [sys.executable, "-m", "pip", "install", "--upgrade", package],
                "auto_run": True,
                "message": f"自动升级 {package}",
            },
            {
                "kind": "info",
                "message": (
                    f"升级后可能需要重新安装浏览器：\n"
                    f"  {sys.executable} -m playwright install"
                ),
            },
        ],
    )
