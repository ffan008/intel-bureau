#!/bin/bash
# 双击运行：开机（登录）自启设置。
# 设置后工作台在后台常驻，不用一直开着终端窗口；定时出报、补跑都照常。
cd "$(dirname "$0")" || exit 1

if [ ! -f "scripts/autostart.sh" ]; then
    echo "找不到 scripts/autostart.sh。请先把整个文件夹解压出来。"
    echo
    echo "按回车键关闭…"
    read -r _
    exit 1
fi

echo
echo "=== 情报局工作台 · 开机自启设置 ==="
echo
echo "  1) 设置登录自启（后台运行，不开窗口）"
echo "  2) 取消自启（停止后台服务）"
echo "  3) 查看当前状态"
echo "  4) 现在打开大屏（后台服务在跑时用这个）"
echo
printf '请选择 [1-4]，直接回车看状态：'
read -r choice

case "$choice" in
    1) bash "scripts/autostart.sh" on ;;
    2) bash "scripts/autostart.sh" off ;;
    3) bash "scripts/autostart.sh" status ;;
    4) bash "scripts/autostart.sh" open ;;
    *) bash "scripts/autostart.sh" status ;;
esac

echo
echo "按回车键关闭窗口…"
read -r _
