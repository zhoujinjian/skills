# 浏览器检测原理与跨平台指南

## 检测范围

`detect_browsers.py` 检测两类浏览器：

| 来源 | 引擎名 | 用途 |
|------|--------|------|
| Playwright 内置 | `playwright_chromium` / `playwright_firefox` / `playwright_webkit` | 推荐使用，跨平台一致 |
| 系统安装 | `system_chrome` / `system_firefox` / `system_edge` / `system_safari` | 备用方案，CI 环境复用宿主浏览器 |

## Playwright 浏览器二进制位置

| 平台 | 路径 |
|------|------|
| macOS | `~/Library/Caches/ms-playwright/` |
| Linux | `~/.cache/ms-playwright/` |
| Windows | `%LOCALAPPDATA%\ms-playwright\` |

每个浏览器一个子目录，形如：

```
~/Library/Caches/ms-playwright/
├── chromium-1234/
├── chromium_headless_shell-1234/
├── firefox-1456/
└── webkit-2103/
```

## 安装状态检测

通过 `playwright install --dry-run <browser>` 命令判定：

- 输出包含 `is already installed` → 已安装
- 输出包含 `is not installed` → 未安装
- 输出包含 `version` 行 → 提取版本号

**注意**：dry-run 仅检查但不下载，安全可重复执行。

## 系统浏览器检测（按平台）

### macOS

扫描 `/Applications/` 下的常见 `.app`：

```
/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge
/Applications/Firefox.app/Contents/MacOS/firefox
/Applications/Safari.app/Contents/MacOS/Safari
```

版本通过 `defaults read ... Info.plist CFBundleShortVersionString` 读取。

### Linux

通过 `which` / `whereis` 查找可执行文件：

```
google-chrome, google-chrome-stable
chromium, chromium-browser
microsoft-edge, microsoft-edge-stable
firefox
```

版本通过 `<binary> --version` 提取最后一段数字。

### Windows

扫描 `%PROGRAMFILES%` 和 `%PROGRAMFILES(X86)%`：

```
Google\Chrome\Application\chrome.exe
Microsoft\Edge\Application\msedge.exe
Mozilla Firefox\firefox.exe
```

## Headless 支持矩阵

| 浏览器 | Headless 支持 | 备注 |
|--------|--------------|------|
| Playwright Chromium | ✅ | 推荐 CI |
| Playwright Firefox | ✅ | |
| Playwright Webkit | ✅ | |
| System Chrome / Edge | ✅ | 通过 `--headless` 标志 |
| System Firefox | ✅ | |
| System Safari | ❌ | Apple 不支持 headless |

## 自定义浏览器路径

如果 Playwright 安装在非默认位置，通过环境变量：

```bash
export PLAYWRIGHT_BROWSERS_PATH=/custom/path
python3 detect_browsers.py
```

## 推荐策略

1. **CI 环境**：使用 Playwright 内置 chromium，确保版本一致
2. **本地调试**：可使用 System Chrome（headed 模式更接近真实用户）
3. **跨浏览器测试**：必须用 Playwright 三剑客，System 浏览器路径在不同机器不一致
4. **Safari/WebKit**：只能用 Playwright webkit，System Safari 不支持自动化

## 验证检测准确性

```bash
# 表格输出人工核对
python3 detect_browsers.py

# JSON 输出供脚本消费
python3 detect_browsers.py --json -o env.json

# 验证某个浏览器可实际启动
python3 -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); print('ok'); b.close(); p.stop()"
```

## 常见问题

### Q: Playwright 已装但检测不到？

A: 检查 `python3 -m playwright install chromium` 是否实际下载。`pip install playwright` 只装 Python 包，不下载浏览器二进制。

### Q: ms-playwright 目录有多个版本？

A: Playwright 升级时会保留旧版本，新版会自动选择匹配的。检测脚本只扫描最新版本。

### Q: 系统浏览器能用 `--browser` 传给 pytest 吗？

A: **不能**。pytest-playwright 的 `--browser` 只接受 `chromium` / `firefox` / `webkit` 三个 Playwright 内部名。要用 System Chrome 必须在 `conftest.py` 的 `browser_launch_args` 中配置 `executable_path`。
