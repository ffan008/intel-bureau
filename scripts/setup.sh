#!/usr/bin/env bash
#
# 情报局工作台：macOS 安装脚本（对应 Windows 的 scripts\setup.ps1）
#   创建/更新 .venv、安装依赖、构建前端、修正文件权限、初始化配置与数据库。
#
# 用法：
#   bash scripts/setup.sh                # 安装或更新
#   bash scripts/setup.sh --rebuild-web  # 强制重新构建前端
#   bash scripts/setup.sh --skip-web     # 不碰前端（用已有的 web/dist）
#   bash scripts/setup.sh --dev          # 连带安装开发依赖（pytest）
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VENV_PY="$ROOT/.venv/bin/python"

SKIP_WEB=0
DEV=0
REBUILD_WEB=0

while [ $# -gt 0 ]; do
    case "$1" in
        --skip-web)    SKIP_WEB=1; shift ;;
        --dev)         DEV=1; shift ;;
        --rebuild-web) REBUILD_WEB=1; shift ;;
        -h|--help)     sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)             echo "未知参数：$1（可用：--skip-web / --dev / --rebuild-web）" >&2; exit 2 ;;
    esac
done

step()  { printf '\033[36m==> %s\033[0m\n' "$1"; }
ok()    { printf '\033[32m%s\033[0m\n' "$1"; }
warn()  { printf '\033[33m%s\033[0m\n' "$1"; }
die()   { printf '\n\033[31m%s\033[0m\n' "$1"; exit 1; }

# ---------------------------------------------------------------- 1. Python 3.12+
find_python() {
    for cand in python3.12 python3.13 python3.14 python3; do
        if command -v "$cand" >/dev/null 2>&1; then
            if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; then
                command -v "$cand"
                return 0
            fi
        fi
    done
    for cand in /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /usr/local/bin/python3.13; do
        if [ -x "$cand" ] && "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' >/dev/null 2>&1; then
            echo "$cand"
            return 0
        fi
    done
    return 1
}

if [ ! -x "$VENV_PY" ]; then
    step '创建虚拟环境 .venv（需要 Python 3.12 以上）'
    PY="$(find_python)" || die "没有找到 Python 3.12 以上的解释器。
  装一个（推荐）：brew install python@3.13
  装完后关掉这个窗口，重新双击「一键安装并启动.command」。"
    echo "    使用 ${PY}（$("$PY" -V 2>&1)）"
    "$PY" -m venv "$ROOT/.venv" || die '创建虚拟环境失败。可以手动执行：'"$PY"' -m venv .venv'
else
    step "已有虚拟环境 .venv（$("$VENV_PY" -V 2>&1)），更新依赖"
fi

# ---------------------------------------------------------------- 2. Python 依赖
step '安装 Python 依赖'
"$VENV_PY" -m pip install --disable-pip-version-check -q --upgrade pip >/dev/null 2>&1 || warn '升级 pip 失败，继续'
REQ='requirements.txt'
if [ "$DEV" -eq 1 ]; then REQ='requirements-dev.txt'; fi
"$VENV_PY" -m pip install --disable-pip-version-check -q -r "$REQ" || die "依赖安装失败（${REQ}）。
  最常见的原因是网络：换一个网络，或先开代理再重试。
  也可以手动执行：$VENV_PY -m pip install -r $REQ"

# macOS 本机 OCR（图片文字识别）。失败不影响其它功能。
if [ -f "$ROOT/requirements-macos.txt" ]; then
    step '安装 macOS 本机 OCR 组件（可选，失败也不影响使用）'
    if "$VENV_PY" -m pip install --disable-pip-version-check -q -r "$ROOT/requirements-macos.txt" >/dev/null 2>&1; then
        ok '    本机 OCR 组件已装好（Vision；中文图还需要系统语言包或 tesseract，见下面的自检）'
    else
        warn '    没装上：图片里的文字将跳过识别（可以用「视觉模型」模式代替）'
    fi
fi

# ---------------------------------------------------------------- 3. 前端
DIST_INDEX="$ROOT/web/dist/index.html"
if [ -f "$DIST_INDEX" ] && [ "$REBUILD_WEB" -eq 0 ]; then
    step '前端已经构建好（web/dist），跳过；需要重建时加 --rebuild-web'
elif [ "$SKIP_WEB" -eq 0 ] && [ -f "$ROOT/web/package.json" ]; then
    if command -v npm >/dev/null 2>&1; then
        step '构建前端（npm ci && npm run build，约 1~2 分钟）'
        ( cd "$ROOT/web" && npm ci --no-audit --no-fund >/dev/null && npm run build ) \
            || die '前端构建失败。可以先跳过：bash scripts/setup.sh --skip-web（用已有的 web/dist）'
    else
        warn '没有找到 npm（需要 Node.js 20.19 以上），跳过前端构建；大屏会显示提示页。'
        warn '  装 Node：brew install node'
    fi
else
    step '没有 web/package.json，跳过前端构建'
fi

# ---------------------------------------------------------------- 4. 执行权限
# 从 Windows 打的压缩包解出来，.sh / .command / npm 的 .bin 都会丢失可执行位。
step '修正文件权限'
chmod +x "$ROOT"/*.command 2>/dev/null || true
chmod +x "$ROOT"/scripts/*.sh 2>/dev/null || true
find "$ROOT/third_party/tools" -path '*/node_modules/.bin/*' -type f -exec chmod +x {} + 2>/dev/null || true

# ---------------------------------------------------------------- 5. 初始化
step '初始化配置与数据库'
"$VENV_PY" -X utf8 -m bureau init || die '初始化失败。'

# ---------------------------------------------------------------- 6. OCR 自检
step '检查图片文字识别（OCR，可选功能）'
"$VENV_PY" -X utf8 - <<'PY' || true
import shutil, subprocess
from bureau.media import ocr
if ocr.IS_WINDOWS:
    print("    Windows 系统 OCR（scripts/tools/ocr.ps1）")
else:
    langs = ocr._vision_supported()
    where = ocr._vision_langs("zh-Hans-CN")[0]
    if langs:
        has_zh = any(l.startswith("zh") for l in langs)
        print(f"    macOS Vision：{len(langs)} 种语言" + ("（含中文）" if has_zh else "（不含中文，中文图会走下面的 tesseract）"))
    else:
        print("    macOS Vision：不可用（没装 pyobjc）")
    tess = shutil.which("tesseract")
    if tess:
        try:
            out = subprocess.run([tess, "--list-langs"], capture_output=True, text=True, timeout=20).stdout
        except Exception:
            out = ""
        has_zh = "chi_sim" in out.split() or "chi_sim" in out
        print(f"    tesseract：已安装" + ("（含简体中文）" if has_zh else "（缺中文包：brew install tesseract-lang）"))
    else:
        print("    tesseract：未安装")
    if not (langs and any(l.startswith("zh") for l in langs)) and not tess:
        print("    ⚠ 中文图片暂时识别不了。三种办法：①「系统设置 → 通用 → 语言与地区」添加简体中文；")
        print("      ② brew install tesseract tesseract-lang；③ 在「智能体」页把 OCR 改成「视觉模型」。")
        print("      不影响其它功能。")
PY

printf '\n'
ok '安装完成。'
printf '  体检：   .venv/bin/python -X utf8 -m bureau doctor\n'
printf '  演示：   .venv/bin/python -X utf8 -m bureau demo seed\n'
printf '  启动：   bash scripts/start.sh    （或双击「启动情报局.command」）\n'
