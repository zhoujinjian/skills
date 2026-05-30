#!/bin/bash
# ============================================================
# start_chrome_cdp.sh
# 在 Terminal（沙箱外）启动 Chrome CDP 服务，供 ui-page-parser 连接
#
# 用法：
#   bash start_chrome_cdp.sh                          # headless 模式（默认）
#   bash start_chrome_cdp.sh --interactive            # 交互式模式（有界面，用于认证登录）
#   bash start_chrome_cdp.sh --interactive --port 9223
#   bash start_chrome_cdp.sh --port 9222
# ============================================================

INTERACTIVE=false
PORT=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --interactive) INTERACTIVE=true; shift ;;
    --port) PORT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

PORT=${PORT:-9222}
PROFILE_DIR="/tmp/chrome_cdp_profile_${PORT}"
LOG_FILE="/tmp/chrome_cdp_${PORT}.log"

# 检查是否已有 Chrome CDP 在运行
if curl -s --max-time 1 "http://localhost:${PORT}/json/version" > /dev/null 2>&1; then
  echo "✅ Chrome CDP 服务已在运行（localhost:${PORT}），无需重复启动"
  curl -s "http://localhost:${PORT}/json/version" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'   Browser: {d[\"Browser\"]}')" 2>/dev/null
  exit 0
fi

# 检查 Chrome 是否安装
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if [ ! -f "$CHROME" ]; then
  echo "❌ 未找到 Google Chrome，请先安装"
  exit 1
fi

if [ "$INTERACTIVE" = true ]; then
  echo "🚀 启动 Chrome CDP 服务（交互式模式，端口 ${PORT}）..."
  echo "   浏览器将显示界面，可手动登录需要认证的网站"
  mkdir -p "$PROFILE_DIR"

  "$CHROME" \
    --remote-debugging-port="${PORT}" \
    --no-sandbox \
    --disable-gpu \
    --disable-dev-shm-usage \
    --user-data-dir="${PROFILE_DIR}" \
    about:blank > "${LOG_FILE}" 2>&1 &

  CHROME_PID=$!
  echo "   Chrome PID: ${CHROME_PID}"
else
  echo "🚀 启动 Chrome CDP 服务（headless 模式，端口 ${PORT}）..."
  mkdir -p "$PROFILE_DIR"

  "$CHROME" \
    --headless=new \
    --remote-debugging-port="${PORT}" \
    --no-sandbox \
    --disable-gpu \
    --disable-dev-shm-usage \
    --user-data-dir="${PROFILE_DIR}" \
    about:blank > "${LOG_FILE}" 2>&1 &

  CHROME_PID=$!
  echo "   Chrome PID: ${CHROME_PID}"
fi

# 等待 CDP 服务就绪（最多 10 秒）
echo -n "   等待 CDP 就绪 "
for i in $(seq 1 10); do
  sleep 1
  echo -n "."
  if curl -s --max-time 1 "http://localhost:${PORT}/json/version" > /dev/null 2>&1; then
    echo ""
    echo "✅ Chrome CDP 服务已就绪！"
    echo ""
    echo "📋 浏览器信息："
    curl -s "http://localhost:${PORT}/json/version" | python3 -m json.tool 2>/dev/null | grep -E "Browser|Protocol" | head -3

    if [ "$INTERACTIVE" = true ]; then
      echo ""
      echo "🔑 交互式模式：请在浏览器中完成登录，然后回到 Claude Code 执行抓取"
      echo "   登录后保持浏览器窗口打开，CDP 连接会复用已认证的会话"
    else
      echo ""
      echo "💡 现在可以在 Claude Code 中运行 ui-page-parser 了"
    fi
    echo ""
    echo "   停止服务：kill ${CHROME_PID}"
    exit 0
  fi
done

echo ""
echo "❌ CDP 服务启动超时，查看日志："
cat "${LOG_FILE}"
exit 1
