#!/bin/bash
# 双击运行：macOS 会用「终端」打开这个文件。
# 作用与 Windows 版的「一键安装并启动.bat」相同：检查 Python → 安装 → 首次写入演示数据 → 启动大屏。
cd "$(dirname "$0")" || exit 1

if [ ! -f "scripts/first-run.sh" ]; then
    echo "找不到 scripts/first-run.sh。"
    echo "请先把整个文件夹解压出来，不要在压缩包里直接运行。"
    echo
    echo "按回车键关闭…"
    read -r _
    exit 1
fi

exec bash "scripts/first-run.sh"
