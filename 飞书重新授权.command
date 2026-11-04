#!/bin/bash
# 双击运行：飞书重新授权。对应 Windows 版的「飞书重新授权.bat」。
cd "$(dirname "$0")" || exit 1

if [ ! -f "scripts/feishu-reauth.sh" ]; then
    echo "找不到 scripts/feishu-reauth.sh。请先把整个文件夹解压出来。"
    echo
    echo "按回车键关闭…"
    read -r _
    exit 1
fi

bash "scripts/feishu-reauth.sh"
echo
echo "按回车键关闭窗口…"
read -r _
