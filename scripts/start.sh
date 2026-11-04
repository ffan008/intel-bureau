#!/usr/bin/env bash
#
# 情报局工作台：启动（对应 Windows 的 scripts\start.ps1）
#   起服务 → 等健康检查通过 → 用 Chrome 的「应用窗口」打开大屏（没有 Chrome 就用默认浏览器）。
#   这个终端窗口会一直占着；关掉窗口或按 Ctrl+C 就停止工作台。
#
# 用法：
#   bash scripts/start.sh
#   bash scripts/start.sh --port 8765
#   bash scripts/start.sh --no-browser      # 只起服务，不开窗口
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VENV_PY="$ROOT/.venv/bin/python"

PORT=8765
OPEN_BROWSER=1

while [ $# -gt 0 ]; do
    case "$1" in
        --port)        PORT="$2"; shift 2 ;;
        --port=*)      PORT="${1#*=}"; shift ;;
        --no-browser)  OPEN_BROWSER=0; shift ;;
        -h|--help)     sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)             echo "未知参数：$1（可用：--port / --no-browser）" >&2; exit 2 ;;
    esac
done

URL="http://127.0.0.1:$PORT"

cyan() { printf '\033[36m%s\033[0m\n' "$1"; }
gray() { printf '\033[90m%s\033[0m\n' "$1"; }
green(){ printf '\033[32m%s\033[0m\n' "$1"; }
red()  { printf '\033[31m%s\033[0m\n' "$1"; }

if [ ! -x "$VENV_PY" ]; then
    red '还没有安装。请先运行：bash scripts/setup.sh（或双击「一键安装并启动.command」）'
    exit 1
fi

healthy() {
    curl -fsS --max-time 2 "$URL/api/health" 2>/dev/null | grep -q '"ok":true'
}

open_dashboard() {
    [ "$OPEN_BROWSER" -eq 0 ] && return 0
    # 优先用「应用窗口」：没有地址栏和标签页，像原生大屏
    for app in 'Google Chrome' 'Microsoft Edge' 'Brave Browser' 'Arc'; do
        if [ -d "/Applications/$app.app" ]; then
            if open -na "$app" --args --app="$URL" --window-size=1600,1000 >/dev/null 2>&1; then
                return 0
            fi
        fi
    done
    open "$URL" >/dev/null 2>&1 || true
}

# 已经在跑：不重复启动，直接开窗口
if healthy; then
    green "工作台已经在运行：$URL"
    gray '已为你打开大屏窗口。这个终端窗口可以直接关掉，不影响正在运行的工作台。'
    open_dashboard
    [ "$OPEN_BROWSER" -eq 1 ] && sleep 2
    exit 0
fi

cyan "启动工作台：${URL}（按 Ctrl+C 或关闭本窗口即停止）"

SERVER_PID=''
cleanup() {
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup INT TERM EXIT

"$VENV_PY" -X utf8 -m bureau serve --port "$PORT" &
SERVER_PID=$!

ready=0
i=0
while [ "$i" -lt 60 ]; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then break; fi
    if healthy; then ready=1; break; fi
    sleep 0.5
    i=$((i + 1))
done

if [ "$ready" -eq 1 ]; then
    open_dashboard
else
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        red "服务 30 秒内没有就绪，先不打开浏览器；稍后可以手动访问 $URL"
    else
        red "服务启动失败。常见原因：端口 $PORT 被占用、依赖没装完整。"
        red "可以看看上面的报错，或运行：.venv/bin/python -X utf8 -m bureau doctor"
        exit 1
    fi
fi

wait "$SERVER_PID" || true
