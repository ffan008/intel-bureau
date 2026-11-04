#!/usr/bin/env bash
#
# 情报局工作台：一键安装并启动（给第一次用的人，对应 Windows 的「一键安装并启动.bat」）
#   检查 Python → 安装依赖 → 第一次装时写入演示数据 → 启动工作台。
#   一般不用直接运行，双击根目录的「一键安装并启动.command」即可。
#
# 用法：
#   bash scripts/first-run.sh
#   bash scripts/first-run.sh --no-browser
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VENV_PY="$ROOT/.venv/bin/python"

BROWSER_FLAG=''
if [ "${1:-}" = '--no-browser' ]; then BROWSER_FLAG='--no-browser'; fi

cyan() { printf '\033[36m%s\033[0m\n' "$1"; }
green(){ printf '\033[32m%s\033[0m\n' "$1"; }
red()  { printf '\033[31m%s\033[0m\n' "$1"; }
gray() { printf '\033[90m%s\033[0m\n' "$1"; }

stop_here() {
    printf '\n'
    red "$1"
    printf '\n'
    gray '看不懂的话，把上面这段文字截图发给给你这个包的人。'
    printf '\n按回车键关闭窗口…'
    read -r _ || true
    exit 1
}

printf '\n'
cyan '=== 个人情报局 · 一键安装并启动（macOS）==='
gray "安装位置：$ROOT"
printf '\n'

# 放在会被同步盘占用、或系统目录里，容易出各种权限问题
case "$ROOT" in
    */Dropbox/*|*/OneDrive/*|*/Documents/*|/Applications/*|/System/*)
        printf '\033[33m提醒：当前文件夹在 %s 这类位置，可能被同步盘或系统权限影响。建议把整个文件夹移到「用户目录」下（比如 ~/IntelBureau）再运行。\033[0m\n' "$ROOT"
        printf '\n' ;;
esac

FIRST_TIME=0
if [ ! -f "$ROOT/data/bureau.db" ]; then FIRST_TIME=1; fi

# 1. 安装（含 Python 检查、依赖、前端、初始化）
cyan '步骤 1/3：安装依赖并初始化（第一次大约 2~5 分钟，需要联网，请不要关闭窗口）…'
printf '\n'
bash "$ROOT/scripts/setup.sh" || stop_here '安装失败。'
printf '\n'

# 2. 第一次安装：写入演示数据，打开时大屏不是空的
if [ "$FIRST_TIME" -eq 1 ]; then
    cyan '步骤 2/3：写入演示数据（全是虚构的群和对话），并生成一份演示报告…'
    if "$VENV_PY" -X utf8 -m bureau demo seed >/dev/null 2>&1 \
       && "$VENV_PY" -X utf8 -m bureau run --demo --dry-run >/dev/null 2>&1; then
        green '    演示数据已就绪。接入自己的群之后，在「系统」页点「清除演示数据」即可。'
    else
        printf '\033[33m    演示数据没有写入成功（不影响使用）。\033[0m\n'
    fi
else
    cyan '步骤 2/3：已经安装过，跳过演示数据。'
fi
printf '\n'

# 3. 启动
cyan '步骤 3/3：启动工作台…'
printf '\033[33m启动后会自动打开浏览器窗口；这个终端窗口要一直开着，关掉它工作台就停了。\033[0m\n'
printf '\033[33m想让它一直在后台运行（不看这个窗口）：双击「开机自启设置.command」选 1。\033[0m\n'
printf '\n'
if [ -n "$BROWSER_FLAG" ]; then
    exec bash "$ROOT/scripts/start.sh" "$BROWSER_FLAG"
else
    exec bash "$ROOT/scripts/start.sh"
fi
