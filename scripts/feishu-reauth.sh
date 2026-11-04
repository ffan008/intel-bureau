#!/usr/bin/env bash
#
# 飞书重新授权（对应 Windows 的「飞书重新授权.bat」）
#   重新授权「用户身份」（消息 + 文档两类权限）。一般双击「飞书重新授权.command」即可。
#
# 用法：
#   bash scripts/feishu-reauth.sh              # 完整重新授权
#   bash scripts/feishu-reauth.sh --status     # 只看当前授权状态
#   bash scripts/feishu-reauth.sh --url-only   # 只生成授权链接，不等授权
#   bash scripts/feishu-reauth.sh --no-browser # 不自动打开浏览器
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VENV_PY="$ROOT/.venv/bin/python"
DOMAINS='im,docs'

STATUS_ONLY=0
URL_ONLY=0
OPEN_BROWSER=1
for arg in "$@"; do
    case "$arg" in
        --status|--status-only) STATUS_ONLY=1 ;;
        --url-only)             URL_ONLY=1 ;;
        --no-browser)           OPEN_BROWSER=0 ;;
        -h|--help)              sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "未知参数：$arg" >&2; exit 2 ;;
    esac
done

cyan() { printf '\033[36m%s\033[0m\n' "$1"; }
green(){ printf '\033[32m%s\033[0m\n' "$1"; }
red()  { printf '\033[31m%s\033[0m\n' "$1"; }
gray() { printf '\033[90m%s\033[0m\n' "$1"; }
warn() { printf '\033[33m%s\033[0m\n' "$1"; }

# ---------------------------------------------------------------- 找 lark-cli
# 返回一个可以直接执行的「命令前缀」，可能是单个可执行文件，也可能是 node + run.js。
CLI=()
find_cli() {
    local bin="$ROOT/third_party/tools/lark-cli/node_modules/.bin/lark-cli"
    local js="$ROOT/third_party/tools/lark-cli/node_modules/@larksuite/cli/scripts/run.js"
    if [ -f "$bin" ]; then
        chmod +x "$bin" 2>/dev/null || true
        if [ -x "$bin" ]; then CLI=("$bin"); return 0; fi
    fi
    if [ -f "$js" ] && command -v node >/dev/null 2>&1; then
        CLI=("$(command -v node)" "$js")
        return 0
    fi
    if command -v lark-cli >/dev/null 2>&1; then CLI=("$(command -v lark-cli)"); return 0; fi
    return 1
}

# 从输出里取第一条单行 JSON（--json 的输出是单行，日志行不是 JSON）
# lark-cli 1.0.98 的 `--json` 输出是**多行缩进**的，还有日志行混在前面，
# 所以不能按行解析：按大括号配对切出对象，再压成单行交给后面的 jget。
json_line() {
    "$VENV_PY" -c '
import json, sys

text = sys.stdin.read()
dec = json.JSONDecoder()
best = None
i = text.find("{")
while i != -1:
    try:
        obj, end = dec.raw_decode(text, i)
    except ValueError:
        i = text.find("{", i + 1)
        continue
    if isinstance(obj, dict):
        best = obj
        i = text.find("{", end)
    else:
        i = text.find("{", i + 1)
if best is not None:
    print(json.dumps(best, ensure_ascii=False))
'
}

jget() {  # jget '<json>' key.subkey
    "$VENV_PY" - "$1" "$2" <<'PY'
import json, sys
try:
    obj = json.loads(sys.argv[1])
except Exception:
    sys.exit(1)
for part in sys.argv[2].split("."):
    if not isinstance(obj, dict) or part not in obj:
        sys.exit(1)
    obj = obj[part]
if obj is None:
    sys.exit(1)
print(obj if not isinstance(obj, (dict, list)) else json.dumps(obj, ensure_ascii=False))
PY
}

fmt_time() {
    "$VENV_PY" - "$1" <<'PY'
import sys, datetime
v = sys.argv[1]
try:
    d = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    print(d.astimezone().strftime("%Y-%m-%d %H:%M"))
except Exception:
    print(v)
PY
}

show_status() {
    local out st ready=1
    out="$("${CLI[@]}" auth status 2>/dev/null | json_line || true)"
    st="$out"
    if [ -z "$st" ] || ! jget "$st" identities.user >/dev/null 2>&1; then
        red '读不到授权状态。'
        return 1
    fi
    local status name msg exp ref
    status="$(jget "$st" identities.user.status || true)"
    name="$(jget "$st" identities.user.userName || true)"
    msg="$(jget "$st" identities.user.message || true)"
    exp="$(jget "$st" identities.user.expiresAt || true)"
    ref="$(jget "$st" identities.user.refreshExpiresAt || true)"
    if [ "$status" = 'ready' ] || [ "$status" = 'valid' ]; then
        green "用户身份：已授权（${name:-未知账号}）"
    elif [ "$status" = 'needs_refresh' ]; then
        # 访问令牌 2 小时就到期，lark-cli 报 needs_refresh 并在下次调用时自己续期，不需要重新授权
        green "用户身份：已授权（${name:-未知账号}）"
        gray '  访问令牌已到期，下次调用会自动续期，不用管。'
    else
        red "用户身份：未授权（${msg:-$status}）"
        ready=0
    fi
    [ -n "$exp" ] && gray "  访问令牌到期：$(fmt_time "$exp")（到期后会自动续期）"
    [ -n "$ref" ] && gray "  授权最迟有效到：$(fmt_time "$ref")（过了这个时间要重新双击本脚本）"
    return $((1 - ready))
}

# 工作台在跑时，顺便让它重新检查一次飞书连接
test_workbench() {
    local s tok resp
    s="$(curl -fsS --max-time 3 http://127.0.0.1:8765/api/session 2>/dev/null || true)"
    if [ -z "$s" ]; then
        gray '工作台没有在运行，跳过连接检查（不影响授权，工作台不用重启）。'
        return 0
    fi
    tok="$(jget "$s" token 2>/dev/null || true)"
    resp="$(curl -fsS --max-time 60 -X POST -H "X-Bureau-Token: $tok" \
            http://127.0.0.1:8765/api/platforms/feishu/test 2>/dev/null || true)"
    if [ -z "$resp" ]; then
        gray '工作台里的飞书连接检查没有返回结果。'
        return 0
    fi
    local health detail
    health="$(jget "$resp" health 2>/dev/null || echo '?')"
    detail="$(jget "$resp" detail 2>/dev/null || echo '')"
    if [ "$health" = 'ok' ]; then green "工作台里的飞书连接：${health}（${detail}）"; else warn "工作台里的飞书连接：${health}（${detail}）"; fi
}

printf '\n'
cyan '=== 个人情报局 · 飞书重新授权（macOS）==='

if ! find_cli; then
    red '没有找到 lark-cli。'
    gray '  随包的工具在 third_party/tools/lark-cli；如果被删了，可以执行：'
    gray '  npm i -g @larksuite/cli'
    exit 1
fi
gray "使用的 lark-cli：${CLI[*]}"

if [ "$STATUS_ONLY" -eq 1 ]; then
    printf '\n'
    ok=0
    show_status || ok=1
    test_workbench
    exit "$ok"
fi

printf '\n'
cyan '步骤 1/3：申请授权链接…'
out="$("${CLI[@]}" auth login --domain "$DOMAINS" --no-wait --json 2>/dev/null | json_line || true)"
url="$(jget "$out" verification_url 2>/dev/null || true)"
code_dev="$(jget "$out" device_code 2>/dev/null || true)"
if [ -z "$url" ] || [ -z "$code_dev" ]; then
    red '申请授权链接失败。命令输出：'
    printf '%s\n' "$out" | head -c 600
    printf '\n'
    exit 1
fi

user_code=''
case "$url" in
    *user_code=*) user_code="${url#*user_code=}"; user_code="${user_code%%&*}" ;;
esac

printf '\n'
printf '请在浏览器里打开下面的链接，确认登录的是你本人的飞书账号，然后点「授权」：\n'
printf '  \033[97m%s\033[0m\n' "$url"
[ -n "$user_code" ] && gray "  授权码：${user_code}（链接有效期 10 分钟）"

if [ "$URL_ONLY" -eq 1 ]; then
    printf '\n'
    gray '（测试模式：只生成链接，不等待授权）'
    exit 0
fi

if [ "$OPEN_BROWSER" -eq 1 ]; then
    open "$url" >/dev/null 2>&1 && gray '已尝试用默认浏览器打开授权页；没弹出来的话，请复制上面的链接到浏览器。'
fi

printf '\n'
cyan '步骤 2/3：等待你在浏览器里确认授权（最多 10 分钟，请不要关闭本窗口）…'
res="$("${CLI[@]}" auth login --device-code "$code_dev" --json 2>/dev/null | json_line || true)"
event="$(jget "$res" event 2>/dev/null || true)"
if [ "$event" != 'authorization_complete' ]; then
    printf '\n'
    red '没有收到授权完成的结果（可能超时或没有点授权）。命令输出：'
    printf '%s\n' "$res" | head -c 600
    printf '\n'
    gray '请重新双击「飞书重新授权.command」再试一次。'
    exit 1
fi
green '授权完成。'
missing="$(jget "$res" missing 2>/dev/null || true)"
if [ -n "$missing" ] && [ "$missing" != '[]' ] && [ "$missing" != 'null' ]; then
    warn "提示：这些权限没有获批：${missing}。需要飞书管理员在开发者后台审批。"
fi

printf '\n'
cyan '步骤 3/3：确认结果…'
ok=0
show_status || ok=1
test_workbench
printf '\n'
if [ "$ok" -eq 0 ]; then
    green '完成。工作台不需要重启，下次定时任务会自动用新的授权。'
    exit 0
fi
red '授权后读到的状态不是 ready，请把上面的信息发给我。'
exit 1
