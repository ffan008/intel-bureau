#!/bin/bash
# 双击运行：启动情报局工作台，并用 Chrome 的应用窗口打开大屏。
# 对应 Windows 版的「启动情报局.bat」。第一次用请先双击「一键安装并启动.command」。
cd "$(dirname "$0")" || exit 1

if [ ! -f "scripts/start.sh" ]; then
    echo "找不到 scripts/start.sh。请先把整个文件夹解压出来，不要在压缩包里直接运行。"
    echo
    echo "按回车键关闭…"
    read -r _
    exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "还没有安装。先双击「一键安装并启动.command」；"
    echo "或者现在直接安装并启动？按回车继续，按 Ctrl+C 取消。"
    read -r _
    exec bash "scripts/first-run.sh"
fi

exec bash "scripts/start.sh"
