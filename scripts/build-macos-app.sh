#!/usr/bin/env bash
#
# 情报局工作台：打成 macOS 安装包（.app + .dmg）
#
# 用法：
#   bash scripts/build-macos-app.sh              # 打包 + 生成 dmg
#   bash scripts/build-macos-app.sh --no-dmg     # 只打包 .app
#   bash scripts/build-macos-app.sh --skip-web   # 跳过前端 build（dist 已是最新时）
#
# 产物：
#   dist-app/情报局.app
#   dist-app/情报局-<版本>-<架构>.dmg
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VENV_PY="$ROOT/.venv/bin/python"
APP_NAME="情报局"
VERSION="1.0.0"
MAKE_DMG=1
SKIP_WEB=0

while [ $# -gt 0 ]; do
    case "$1" in
        --no-dmg)   MAKE_DMG=0; shift ;;
        --skip-web) SKIP_WEB=1; shift ;;
        -h|--help)  sed -n '2,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)          echo "未知参数：$1" >&2; exit 2 ;;
    esac
done

cyan() { printf '\033[36m%s\033[0m\n' "$1"; }
gray() { printf '\033[90m%s\033[0m\n' "$1"; }
green(){ printf '\033[32m%s\033[0m\n' "$1"; }
red()  { printf '\033[31m%s\033[0m\n' "$1" >&2; }

[ -x "$VENV_PY" ] || { red '还没装环境：先跑 bash scripts/setup.sh'; exit 1; }

# ---------- 1. 前端 ----------
if [ "$SKIP_WEB" -eq 0 ]; then
    if [ ! -d web/node_modules ]; then
        cyan '[1/5] 安装前端依赖'
        ( cd web && npm install --no-audit --no-fund )
    fi
    cyan '[1/5] 构建前端'
    ( cd web && npm run build )
else
    gray '[1/5] 跳过前端构建'
fi
[ -f web/dist/index.html ] || { red 'web/dist 不存在，去掉 --skip-web 重新构建'; exit 1; }

# ---------- 2. 依赖 ----------
cyan '[2/5] 检查打包依赖'
"$VENV_PY" -c "import PyInstaller" 2>/dev/null || "$VENV_PY" -m pip install --quiet pyinstaller

# ---------- 3. 图标 ----------
cyan '[3/5] 准备图标'
if [ ! -f pack/appicon.icns ]; then
    "$VENV_PY" pack/make_icon.py
else
    gray '  已有 pack/appicon.icns，跳过'
fi

# ---------- 4. 打包 ----------
cyan '[4/5] PyInstaller 打包（约 1 分钟）'
rm -rf dist-app build-app
"$VENV_PY" -m PyInstaller pack/intelbureau.spec --noconfirm \
    --distpath dist-app --workpath build-app

APP_PATH="dist-app/${APP_NAME}.app"
[ -d "$APP_PATH" ] || { red "打包失败：找不到 $APP_PATH"; exit 1; }
SIZE=$(du -sh "$APP_PATH" | cut -f1)
green "  ✓ ${APP_PATH}（${SIZE}）"

# ---------- 5. dmg ----------
if [ "$MAKE_DMG" -eq 1 ]; then
    cyan '[5/5] 生成 dmg'
    ARCH=$(uname -m)
    DMG="dist-app/${APP_NAME}-${VERSION}-${ARCH}.dmg"
    STAGE=$(mktemp -d)
    trap 'rm -rf "$STAGE"' EXIT
    cp -R "$APP_PATH" "$STAGE/"
    ln -s /Applications "$STAGE/Applications"
    cat > "$STAGE/首次打开请先看这里.txt" <<'TXT'
情报局 · 作战大屏
==================

第一次打开会被 macOS 拦住（提示「无法验证开发者」），这是未上架 App Store 的
软件都会遇到的，不是文件有问题。两种放行方式，任选一种：

  方式一：右键点「情报局」→ 选「打开」→ 弹窗里再点「打开」
  方式二：打开「系统设置 → 隐私与安全性」，页面下方点「仍要打开」

之后就能正常双击启动了。

装好后会发生什么
----------------
· 菜单栏出现一个「◉」，点它可以打开大屏、报告目录、数据目录、日志，或退出
· 大屏会自动用 Chrome 的应用窗口打开（没装 Chrome 就用默认浏览器）
· 所有数据只存在本机：
    ~/Library/Application Support/IntelBureau
  升级或删掉 App 都不会动这些数据，想彻底清空就手动删掉这个目录

想采微信 / QQ 的群，还需要另外装采集工具
----------------------------------------
本安装包不含微信和 QQ 的采集工具（它们各自有自己的安装程序）：
· 微信 → WeChatDataAnalysis（本地 API，跑在 127.0.0.1:10392）
· QQ   → NapCat（OneBot，跑在 127.0.0.1:3010）
装好并登录后，回到大屏「情报源」页面点「测试连接」，通过即可。

飞书采集需要 Node.js 和 lark-cli，本包未内置；要用飞书请到
https://github.com/ffan008/intel-bureau 看 docs/SETUP_FEISHU.md。
TXT
    rm -f "$DMG"
    hdiutil create -volname "$APP_NAME" -srcfolder "$STAGE" -ov -format UDZO -quiet "$DMG"
    green "  ✓ ${DMG}（$(du -sh "$DMG" | cut -f1)）"
    gray ''
    gray '  提示：本机直接构建的 dmg 没有开发者签名，拷给别人下载后首次打开会被 Gatekeeper 拦，'
    gray '        按 dmg 里的说明右键打开即可；要彻底免掉得买 Apple 开发者账号做公证。'
fi

green ''
green '打包完成。'
