<#
.SYNOPSIS
  飞书重新授权：重新授权「用户身份」（消息 + 文档两类权限）。
  一般不用直接运行它，双击项目根目录的「飞书重新授权.bat」即可。
.PARAMETER NoBrowser
  不自动打开浏览器，只打印授权链接。
.PARAMETER UrlOnly
  只生成并打印授权链接就退出（用来测试）。
.PARAMETER StatusOnly
  只查看当前授权状态，不重新授权。
#>
[CmdletBinding()]
param(
    [switch]$NoBrowser,
    [switch]$UrlOnly,
    [switch]$StatusOnly
)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Domains = 'im,docs'

function Say([string]$msg, [string]$color = 'Gray') { Write-Host $msg -ForegroundColor $color }

function Find-Cli {
    $mine = Join-Path $Root 'third_party\tools\lark-cli\node_modules\@larksuite\cli\bin\lark-cli.exe'
    if (Test-Path -LiteralPath $mine) { return $mine }
    $cmd = Get-Command lark-cli -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    $wb = Join-Path $env:USERPROFILE '.workbuddy-ai\binaries\node\cli-connector-packages\node_modules\@larksuite\cli\bin\lark-cli.exe'
    if (Test-Path -LiteralPath $wb) { return $wb }
    return $null
}

# 从命令输出里取出第一行单行 JSON（--json 的输出是单行，日志行不是 JSON）
function Get-JsonLine([string]$text) {
    foreach ($line in ($text -split "`r?`n")) {
        $t = $line.Trim()
        if ($t.StartsWith('{') -and $t.EndsWith('}')) {
            try { return ($t | ConvertFrom-Json) } catch { }
        }
    }
    return $null
}

function Format-Time($v) {
    if (-not $v) { return '-' }
    try {
        $d = [datetimeoffset]::Parse([string]$v, [Globalization.CultureInfo]::InvariantCulture)
        return $d.ToLocalTime().ToString('yyyy-MM-dd HH:mm')
    } catch { return [string]$v }
}

function Show-Status([string]$cli) {
    $st = $null
    try { $st = (& $cli auth status 2>$null | Out-String) | ConvertFrom-Json } catch { }
    if (-not $st -or -not $st.identities -or -not $st.identities.user) {
        Say '读不到授权状态。' 'Red'
        return $false
    }
    $u = $st.identities.user
    $ready = ($u.status -eq 'ready')
    if ($ready) { Say ('用户身份：已授权（{0}）' -f $u.userName) 'Green' }
    else { Say ('用户身份：未授权（{0}）' -f $u.message) 'Red' }
    if ($u.expiresAt) { Say ('  访问令牌到期：{0}（到期后会自动续期）' -f (Format-Time $u.expiresAt)) }
    if ($u.refreshExpiresAt) { Say ('  授权最迟有效到：{0}（过了这个时间要重新双击本脚本）' -f (Format-Time $u.refreshExpiresAt)) }
    return $ready
}

# 如果工作台正在运行，顺便让它重新检查一次飞书连接
function Test-Workbench {
    try {
        $s = Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/session' -TimeoutSec 3
        $h = @{ 'X-Bureau-Token' = $s.token }
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/api/platforms/feishu/test' -Method POST -Headers $h -UseBasicParsing -TimeoutSec 60
        $p = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json
        $color = 'Yellow'
        if ($p.health -eq 'ok') { $color = 'Green' }
        Say ('工作台里的飞书连接：{0}（{1}）' -f $p.health, $p.detail) $color
    } catch {
        Say '工作台没有在运行，跳过连接检查（不影响授权，工作台不用重启）。'
    }
}

Say ''
Say '=== 个人情报局 · 飞书重新授权 ===' 'Cyan'

$cli = Find-Cli
if (-not $cli) {
    Say '没有找到 lark-cli。请先运行：' 'Red'
    Say '  powershell -ExecutionPolicy Bypass -File scripts\tools\get-lark-cli.ps1'
    exit 1
}
Say ('使用的 lark-cli：{0}' -f $cli)

if ($StatusOnly) {
    Say ''
    $ok = Show-Status $cli
    Test-Workbench
    if ($ok) { exit 0 } else { exit 1 }
}

Say ''
Say '步骤 1/3：申请授权链接...' 'Cyan'
$out = & $cli auth login --domain $Domains --no-wait --json 2>$null | Out-String
$j = Get-JsonLine $out
if (-not $j -or -not $j.verification_url -or -not $j.device_code) {
    Say '申请授权链接失败。命令输出：' 'Red'
    $t = $out.Trim()
    if ($t.Length -gt 600) { $t = $t.Substring(0, 600) + '...' }
    Say $t
    exit 1
}
$url = [string]$j.verification_url
$code = ''
if ($url -match 'user_code=([A-Za-z0-9-]+)') { $code = $Matches[1] }

Say ''
Say '请在浏览器里打开下面的链接，确认登录的是你本人的飞书账号，然后点「授权」：'
Say ('  ' + $url) 'White'
if ($code) { Say ('  授权码：{0}（链接有效期 10 分钟）' -f $code) }

if ($UrlOnly) {
    Say ''
    Say '（测试模式：只生成链接，不等待授权）'
    exit 0
}

if (-not $NoBrowser) {
    try { Start-Process $url; Say '已尝试用默认浏览器打开授权页；没弹出来的话，请复制上面的链接到浏览器。' } catch { }
}

Say ''
Say '步骤 2/3：等待你在浏览器里确认授权（最多 10 分钟，请不要关闭本窗口）...' 'Cyan'
$res = & $cli auth login --device-code ([string]$j.device_code) --json 2>$null | Out-String
$done = Get-JsonLine $res
if (-not $done -or $done.event -ne 'authorization_complete') {
    Say ''
    Say '没有收到授权完成的结果（可能超时或没有点授权）。命令输出：' 'Red'
    $t = $res.Trim()
    if ($t.Length -gt 600) { $t = $t.Substring(0, 600) + '...' }
    Say $t
    Say '请重新双击本脚本再试一次。'
    exit 1
}
Say '授权完成。' 'Green'
if ($done.missing -and @($done.missing).Count -gt 0) {
    Say ('提示：这些权限没有获批：{0}。需要飞书管理员在开发者后台审批。' -f (@($done.missing) -join '、')) 'Yellow'
}

Say ''
Say '步骤 3/3：确认结果...' 'Cyan'
$ok = Show-Status $cli
Test-Workbench
Say ''
if ($ok) {
    Say '完成。工作台不需要重启，下次定时任务会自动用新的授权。' 'Green'
    exit 0
}
Say '授权后读到的状态不是 ready，请把上面的信息发给我。' 'Red'
exit 1
