<#
.SYNOPSIS
  把飞书官方 lark-cli（npm 包 @larksuite/cli@1.0.98）安装到 third_party/tools/lark-cli，然后打印登录状态。
  npm 会按 package-lock 的 sha512 校验包本身；包的 postinstall 会下载对应平台的二进制，
  并用包内 checksums.txt 做 SHA-256 校验（不一致时安装失败）。可重复执行。
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\tools\get-lark-cli.ps1
#>
param(
    [string]$Version = '1.0.98',
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Prefix = Join-Path $Root 'third_party\tools\lark-cli'
$PkgJson = Join-Path $Prefix 'node_modules\@larksuite\cli\package.json'
$Exe = Join-Path $Prefix 'node_modules\@larksuite\cli\bin\lark-cli.exe'

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
$alreadyBundled = (Test-Path $Exe) -and -not $Force
if (-not $npm -and -not $alreadyBundled) { throw '没有找到 npm。请先安装 Node.js（https://nodejs.org，选 LTS 版），再重新运行本脚本。' }

$installed = $null
if (Test-Path $PkgJson) { $installed = (Get-Content $PkgJson -Raw -Encoding UTF8 | ConvertFrom-Json).version }
if ($installed -eq $Version -and (Test-Path $Exe) -and -not $Force) {
    Write-Host "lark-cli $Version 已安装，跳过：$Prefix" -ForegroundColor Green
} else {
    Write-Host "== 安装 @larksuite/cli@$Version 到 $Prefix ==" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $Prefix | Out-Null
    $ErrorActionPreference = 'Continue'      # npm 会把警告写到 stderr，PowerShell 5.1 下不能因此中断
    & $npm.Source install --prefix $Prefix "@larksuite/cli@$Version" --no-fund --no-audit
    $code = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($code -ne 0) { throw "npm install 失败（退出码 $code）。如果是网络问题，可设置代理后重试。" }
    if (-not (Test-Path $Exe)) { throw "安装完成但没有找到 $Exe（postinstall 下载二进制可能失败），请查看上面的 npm 输出。" }
}

$env:LARKSUITE_CLI_NO_UPDATE_NOTIFIER = '1'
$env:LARKSUITE_CLI_NO_SKILLS_NOTIFIER = '1'
Write-Host ""
Write-Host "版本：$(& $Exe --version)"
Write-Host "路径：$Exe"
Write-Host ""
Write-Host "== lark-cli auth status ==" -ForegroundColor Cyan
$ErrorActionPreference = 'Continue'
$raw = & $Exe auth status --json 2>$null | Out-String
$ErrorActionPreference = 'Stop'
try { $st = $raw | ConvertFrom-Json } catch { $st = $null }
if (-not $st) {
    Write-Host '还没有配置飞书应用。请运行：' -NoNewline; Write-Host " `"$Exe`" config init" -ForegroundColor Yellow
} else {
    Write-Host "应用：$($st.appId)    默认身份：$($st.identity)"
    foreach ($name in 'bot', 'user') {
        $i = $st.identities.$name
        if ($i) {
            $label = if ($name -eq 'bot') { '机器人身份' } else { '用户身份' }
            $who = if ($i.userName) { "（$($i.userName)）" } else { '' }
            $color = if ($i.available) { 'Green' } else { 'Yellow' }
            Write-Host ("  {0}：{1}{2}  {3}" -f $label, $i.status, $who, $i.message) -ForegroundColor $color
        }
    }
    if (-not $st.identities.user.available) {
        Write-Host ""
        Write-Host '用户身份不可用时，在终端运行下面的命令重新授权（会打开浏览器，需要你本人确认）：'
        Write-Host "  `"$Exe`" auth login --domain im" -ForegroundColor Yellow
    }
}
Write-Host ""
Write-Host '接入说明见 docs\SETUP_FEISHU.md。'
