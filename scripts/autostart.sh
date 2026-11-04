#!/usr/bin/env bash
#
# 情报局工作台：登录自启（对应 Windows 的 install-autostart.ps1，改用 launchd）
#   在 ~/Library/LaunchAgents 注册一个 LaunchAgent，登录后在后台起服务，
#   不用一直开着终端窗口；定时出报、错过的任务照常补跑。
#
# 用法：
#   bash scripts/autostart.sh on        安装并立即启用（后台运行，不开窗口）
#   bash scripts/autostart.sh off       取消自启并停掉后台服务
#   bash scripts/autostart.sh status    看当前状态
#   bash scripts/autostart.sh open      打开大屏（后台服务在跑时用这个）
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VENV_PY="$ROOT/.venv/bin/python"
LABEL='com.intelbureau.workbench'
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PORT="${BUREAU_PORT:-8765}"
URL="http://127.0.0.1:$PORT"
UID_NUM="$(id -u)"

cyan() { printf '\033[36m%s\033[0m\n' "$1"; }
green(){ printf '\033[32m%s\033[0m\n' "$1"; }
red()  { printf '\033[31m%s\033[0m\n' "$1"; }
gray() { printf '\033[90m%s\033[0m\n' "$1"; }

loaded() {
    launchctl print "gui/$UID_NUM/$LABEL" >/dev/null 2>&1
}

open_dashboard() {
    for app in 'Google Chrome' 'Microsoft Edge' 'Brave Browser' 'Arc'; do
        if [ -d "/Applications/$app.app" ]; then
            if open -na "$app" --args --app="$URL" --window-size=1600,1000 >/dev/null 2>&1; then return 0; fi
        fi
    done
    open "$URL" >/dev/null 2>&1 || true
}

cmd_on() {
    if [ ! -x "$VENV_PY" ]; then
        red '还没有安装。请先双击「一键安装并启动.command」完成安装。'
        exit 1
    fi

    # launchd 的环境变量很干净（没有 PATH），把 node / claude 这类工具的位置写进去，
    # 否则飞书 lark-cli、Claude Code 提供方在后台会找不到。
    LAUNCH_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    for extra in "$(dirname "$(command -v node 2>/dev/null || echo /nonexistent/x)")" \
                 "$(dirname "$(command -v claude 2>/dev/null || echo /nonexistent/x)")" \
                 "$HOME/.local/bin"; do
        case ":$LAUNCH_PATH:" in
            *":$extra:"*) continue ;;
        esac
        if [ -d "$extra" ]; then LAUNCH_PATH="$extra:$LAUNCH_PATH"; fi
    done

    mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/data/logs"

    cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PY</string>
        <string>-X</string>
        <string>utf8</string>
        <string>-m</string>
        <string>bureau</string>
        <string>serve</string>
        <string>--port</string>
        <string>$PORT</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$ROOT</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$LAUNCH_PATH</string>
        <key>LANG</key>
        <string>zh_CN.UTF-8</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>30</integer>
    <key>ProcessType</key>
    <string>Background</string>
    <key>StandardOutPath</key>
    <string>$ROOT/data/logs/serve.out.log</string>
    <key>StandardErrorPath</key>
    <string>$ROOT/data/logs/serve.err.log</string>
</dict>
</plist>
PLIST_EOF

    if healthy_now; then
        gray '检测到已经有工作台在运行（可能是窗口版）。自启会在下次登录时接管；'
        gray '要现在就让后台版本跑起来，先按 Ctrl+C 关掉那个窗口，再重新执行本脚本。'
    fi

    if loaded; then launchctl bootout "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 || true; fi
    # 注意：launchctl load 即使失败也可能返回 0，所以下面一定要用 print 复核
    launchctl bootstrap "gui/$UID_NUM" "$PLIST" >/dev/null 2>&1 || launchctl load -w "$PLIST" >/dev/null 2>&1 || true
    sleep 2

    if ! loaded; then
        red '自启没有注册成功（launchd 拒绝了这次加载）。'
        gray '  配置文件已经写好了：'"$PLIST"
        gray '  常见的两个原因：① 这个终端不是在你自己桌面的会话里跑的；② 系统刚更新过。'
        gray '  解决办法：打开「终端」App（不是这里的窗口），执行：'
        gray "    bash '$ROOT/scripts/autostart.sh' on"
        gray '  还不行就在「系统设置 → 通用 → 登录项与扩展」里看有没有被拦下来。'
        gray '  不影响手动启动：双击「启动情报局.command」照常能用。'
        exit 1
    fi

    green "已设置登录自启：$LABEL"
    gray  "  后台服务：${URL}（日志：data/logs/serve.out.log、serve.err.log）"
    gray  "  取消：bash scripts/autostart.sh off"
    if healthy_now; then green "后台服务已经起来了：$URL"; else
        gray '后台服务还在启动，稍等几秒刷新浏览器即可。'
    fi
}

healthy_now() {
    curl -fsS --max-time 2 "$URL/api/health" 2>/dev/null | grep -q '"ok":true'
}

cmd_off() {
    if loaded; then
        launchctl bootout "gui/$UID_NUM/$LABEL" >/dev/null 2>&1 || launchctl unload -w "$PLIST" >/dev/null 2>&1 || true
    fi
    rm -f "$PLIST"
    if healthy_now; then
        gray '已取消自启；但 8765 端口上还有工作台在跑（可能是你自己开着的窗口版）。'
    else
        green '已取消自启，后台服务已停止。'
    fi
}

cmd_status() {
    if [ -f "$PLIST" ]; then
        green "自启：已设置（${PLIST}）"
    else
        gray '自启：未设置'
    fi
    if loaded; then
        green '后台服务：launchd 已加载'
    else
        gray '后台服务：launchd 未加载'
    fi
    if healthy_now; then green "访问地址：$URL 正常"; else red "访问地址：$URL 没有响应"; fi
    if [ -f "$ROOT/data/logs/serve.err.log" ]; then
        gray "最近日志：data/logs/serve.err.log"
    fi
}

case "${1:-status}" in
    on)     cmd_on ;;
    off)    cmd_off ;;
    status) cmd_status ;;
    open)   open_dashboard ;;
    -h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' ;;
    *)      echo "未知参数：$1（可用：on / off / status / open）" >&2; exit 2 ;;
esac
