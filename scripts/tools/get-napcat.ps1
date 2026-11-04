<#
.SYNOPSIS
  下载 NapCatQQ 最新 Release（NapCat.Shell.zip，加 -OneKey 时下载 NapCat.Shell.Windows.OneKey.zip），
  用 GitHub API 返回的 digest（sha256）校验后解压到 third_party/tools/napcat/<版本>/。可重复执行。
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\tools\get-napcat.ps1
  powershell -ExecutionPolicy Bypass -File scripts\tools\get-napcat.ps1 -OneKey
#>
param(
    [switch]$OneKey,
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Base = Join-Path $Root 'third_party\tools\napcat'
$Repo = 'NapNeko/NapCatQQ'
$AssetName = if ($OneKey) { 'NapCat.Shell.Windows.OneKey.zip' } else { 'NapCat.Shell.zip' }
$Headers = @{ 'User-Agent' = 'IntelBureau-setup'; 'Accept' = 'application/vnd.github+json' }

function Get-FileSha256([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }

function Invoke-Download([string]$Url, [string]$OutFile) {
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        $ErrorActionPreference = 'Continue'
        & $curl.Source -L --fail --retry 3 --connect-timeout 20 -sS -o $OutFile $Url
        $code = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($code -ne 0) { throw "下载失败（curl 退出码 $code）：$Url" }
    } else {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $OutFile -Headers @{ 'User-Agent' = 'IntelBureau-setup' } -TimeoutSec 600
    }
}

Write-Host "== 获取 $Repo 最新版本信息 ==" -ForegroundColor Cyan
try {
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers $Headers -TimeoutSec 60
} catch {
    throw "无法访问 GitHub API：$($_.Exception.Message)。请检查网络或代理后重试。"
}
$tag = $rel.tag_name
$asset = $rel.assets | Where-Object { $_.name -eq $AssetName } | Select-Object -First 1
if (-not $asset) { throw "Release $tag 里没有 $AssetName，可用文件：$((@($rel.assets.name)) -join ', ')" }
if (-not $asset.digest -or -not ($asset.digest -match '^sha256:([0-9a-fA-F]{64})$')) {
    throw "GitHub 没有为 $AssetName 提供 sha256 digest，无法校验，已停止（不会跳过校验）。"
}
$expected = $Matches[1].ToLowerInvariant()
Write-Host "版本 $tag，文件 $AssetName（$([math]::Round($asset.size / 1MB, 1)) MB）"
Write-Host "官方 sha256：$expected"

$verDir = Join-Path $Base $tag
$target = if ($OneKey) { Join-Path $verDir 'OneKey' } else { Join-Path $verDir 'Shell' }
$zip = Join-Path $Base "$tag-$AssetName"
$marker = Join-Path $target '.bureau-verified.json'
New-Item -ItemType Directory -Force -Path $Base | Out-Null

$done = $false
if ((Test-Path $marker) -and -not $Force) {
    $m = Get-Content $marker -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($m.sha256 -eq $expected) { $done = $true; Write-Host "已安装并校验过，跳过下载与解压：$target" -ForegroundColor Green }
}
if (-not $done) {
    if ((Test-Path $zip) -and -not $Force -and ((Get-FileSha256 $zip) -eq $expected)) {
        Write-Host "已有校验通过的安装包，跳过下载：$zip"
    } else {
        Write-Host "下载中：$($asset.browser_download_url)"
        $part = "$zip.part"
        Invoke-Download $asset.browser_download_url $part
        $actual = Get-FileSha256 $part
        if ($actual -ne $expected) {
            Remove-Item -LiteralPath $part -Force
            throw "sha256 不一致！期望 $expected，实际 $actual。文件已删除，请稍后重试（不会使用未通过校验的文件）。"
        }
        Move-Item -LiteralPath $part -Destination $zip -Force
        Write-Host "sha256 校验通过：$actual" -ForegroundColor Green
    }
    $tmp = "$target.extracting"
    if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
    Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
    if (Test-Path $target) { Remove-Item -LiteralPath $target -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $verDir | Out-Null
    Move-Item -LiteralPath $tmp -Destination $target
    [ordered]@{ asset = $AssetName; tag = $tag; sha256 = $expected; verified_at = (Get-Date).ToString('s') } |
        ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
    Write-Host "已解压到：$target" -ForegroundColor Green
}

$launchers = Get-ChildItem -LiteralPath $target -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in '.bat', '.exe' -and $_.Name -notmatch '^(KillQQ|uninstall)' } | Sort-Object Name
Write-Host ""
Write-Host "== 后续步骤 ==" -ForegroundColor Cyan
Write-Host "启动文件（在 $target）："
foreach ($l in $launchers) { Write-Host "  - $($l.Name)" }
Write-Host "  （Windows 10 用 launcher-win10-user.bat，Windows 11 用 launcher-user.bat）"
Write-Host @"
1. 用「情报员小号」登录：运行上面的启动文件（Shell 版会调用本机已装的 QQ NT），在弹出的二维码或
   WebUI 里用小号扫码。不要用主号登录 NapCat。
2. 打开 WebUI：http://127.0.0.1:6099 （首次登录的 WebUI 令牌见控制台输出或 config\webui.json）。
   安全提醒：NapCat 的 WebUI 默认监听 0.0.0.0（局域网可访问），建议把 config\webui.json 里的
   "host" 改成 "127.0.0.1" 后重启 NapCat。
   进入「网络配置」→ 新建「HTTP 服务器」：名称 bureau、主机 127.0.0.1、端口 3010、
   消息格式 array，并设置一个随机 token（例如运行：[guid]::NewGuid().ToString('N')）。
3. 可选（实时上报）：再新建「HTTP 客户端」：URL 填 http://127.0.0.1:8765/api/ingest/onebot，
   消息格式 array，token 与上一步相同（NapCat 会用它生成 X-Signature 签名）。
4. 把 token 填进工作台：「情报源」→ QQ → NapCatQQ（OneBot 11）→ Token，然后点「测试」。
   完整说明见 docs\SETUP_QQ.md，配置样例见 scripts\tools\napcat-config-template.json。
"@