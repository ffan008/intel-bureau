#!/usr/bin/env bash
#
# 把「源码版」的数据搬到「安装版」的数据目录，省得重新勾白名单、重新等采集。
#
# 用法：bash scripts/migrate-to-app.sh [--dry-run]
#
# 搬运内容：
#   data/          聊天记录 + 报告 + 日志 + 缓存（约 190MB）
#   config/settings.yaml  你的兴趣关键词、采集配置
#   config/secrets.yaml   工作台令牌、WDA Token
#
# 目标目录：~/Library/Application Support/IntelBureau
# 已存在同名文件时会先备份成 *.bak-<时间戳>，不会直接覆盖。
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$HOME/Library/Application Support/IntelBureau"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

cyan() { printf '\033[36m%s\033[0m\n' "$1"; }
gray() { printf '\033[90m%s\033[0m\n' "$1"; }
green(){ printf '\033[32m%s\033[0m\n' "$1"; }
red()  { printf '\033[31m%s\033[0m\n' "$1" >&2; }

[ -d "$ROOT/data" ] || { red "找不到 $ROOT/data，请在本项目目录里运行"; exit 1; }

STAMP=$(date +%Y%m%d-%H%M%S)
cyan "源目录：$ROOT"
cyan "目标  ：$DEST"
[ "$DRY" -eq 1 ] && gray '（试运行，不会真的写文件）'

mkdir -p "$DEST/config"

backup_if_exists() {
    local f="$1"
    if [ -e "$f" ]; then
        gray "  已有 $(basename "$f")，备份为 $(basename "$f").bak-$STAMP"
        [ "$DRY" -eq 0 ] && mv "$f" "$f.bak-$STAMP"
    fi
}

# 1) 配置：只搬用户自己的两个文件，模板让 App 首次启动自己铺
for name in settings.yaml secrets.yaml; do
    src="$ROOT/config/$name"
    [ -f "$src" ] || { gray "  跳过 config/$name（不存在）"; continue; }
    backup_if_exists "$DEST/config/$name"
    [ "$DRY" -eq 0 ] && cp -p "$src" "$DEST/config/$name"
    green "  ✓ config/$name"
done

# 2) 数据：整个 data/ 搬过去
if [ -d "$DEST/data" ]; then
    gray "  目标已有 data/，先备份为 data.bak-$STAMP"
    [ "$DRY" -eq 0 ] && mv "$DEST/data" "$DEST/data.bak-$STAMP"
fi
if [ "$DRY" -eq 0 ]; then
    cp -Rp "$ROOT/data" "$DEST/data"
    green "  ✓ data/（$(du -sh "$DEST/data" | cut -f1)）"
else
    gray "  将复制 data/（$(du -sh "$ROOT/data" | cut -f1)）"
fi

green ''
if [ "$DRY" -eq 1 ]; then
    gray '试运行结束。确认没问题后去掉 --dry-run 再跑一次。'
else
    green '迁移完成。现在可以打开「情报局」App 了。'
    gray "  注意：先把还在跑的源码版服务停掉（终端里 Ctrl+C），否则 8765 端口被占，App 只会打开已有窗口。"
    gray "  旧数据备份在 $DEST 里，确认没问题后可以手动删掉 *.bak-$STAMP。"
fi
