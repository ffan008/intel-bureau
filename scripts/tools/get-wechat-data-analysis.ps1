<#
.SYNOPSIS
  下载 WeChatDataAnalysis 最新 Release 的 Windows 安装包（*Setup.exe），用 GitHub API 的 digest（sha256）
  校验，并与 Release 附带的 SHA256SUMS.txt 交叉核对，保存到 third_party/tools/wda/。
  本脚本不会运行安装包，只打印安装和使用步骤。可重复执行。
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\tools\get-wechat-data-analysis.ps1
#>
param([switch]$Force)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Dir = Join-Path $Root 'third_party\tools\wda'
$Repo = 'LifeArchiveProject/WeChatDataAnalysis'
$Headers = @{ 'User-Agent' = 'IntelBureau-setup'; 'Accept' = 'application/vnd.github+json' }

function Get-FileSha256([string]$Path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant() }
function Get-Digest($asset) {
    if (-not $asset.digest -or -not ($asset.digest -match '^sha256:([0-9a-fA-F]{64})$')) {
        throw "GitHub 没有为 $($asset.name) 提供 sha256 digest，无法校验，已停止（不会跳过校验）。"
    }
    return $Matches[1].ToLowerInvariant()
}
function Invoke-Download([string]$Url, [string]$OutFile) {
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        $ErrorActionPreference = 'Continue'
        & $curl.Source -L --fail --retry 3 --connect-timeout 20 -sS -o $OutFile $Url
        $code = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($code -ne 0) { throw "下载失败（curl 退出码 $code）：$Url" }
    } else {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $OutFile -Headers @{ 'User-Agent' = 'IntelBureau-setup' } -TimeoutSec 1800
    }
}

Write-Host "== 获取 $Repo 最新版本信息 ==" -ForegroundColor Cyan
try {
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers $Headers -TimeoutSec 60
} catch {
    throw "无法访问 GitHub API：$($_.Exception.Message)。请检查网络或代理后重试。"
}
$tag = $rel.tag_name
$asset = $rel.assets | Where-Object { $_.name -like '*Setup.exe' } | Select-Object -First 1
if (-not $asset) { throw "Release $tag 里没有 Windows 安装包（*Setup.exe）。可用文件：$((@($rel.assets.name)) -join ', ')" }
$expected = Get-Digest $asset
Write-Host "版本 $tag，文件 $($asset.name)（$([math]::Round($asset.size / 1MB, 1)) MB）"
Write-Host "官方 sha256：$expected"

# 交叉核对：Release 附带的 SHA256SUMS.txt（它本身也按 digest 校验）
$sumsAsset = $rel.assets | Where-Object { $_.name -eq 'SHA256SUMS.txt' } | Select-Object -First 1
if ($sumsAsset) {
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    $sumsFile = Join-Path $Dir "$tag-SHA256SUMS.txt"
    Invoke-Download $sumsAsset.browser_download_url $sumsFile
    if ((Get-FileSha256 $sumsFile) -ne (Get-Digest $sumsAsset)) { throw 'SHA256SUMS.txt 本身的 sha256 不一致，已停止。' }
    $line = Get-Content $sumsFile -Encoding UTF8 | Where-Object { $_ -match [regex]::Escape($asset.name) } | Select-Object -First 1
    if ($line -and ($line -match '^([0-9a-fA-F]{64})')) {
        if ($Matches[1].ToLowerInvariant() -ne $expected) { throw "SHA256SUMS.txt 与 GitHub digest 不一致，已停止。" }
        Write-Host 'SHA256SUMS.txt 与 GitHub digest 一致'
    } else {
        Write-Host 'SHA256SUMS.txt 里没有该安装包的条目，只按 GitHub digest 校验' -ForegroundColor Yellow
    }
}

New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$out = Join-Path $Dir $asset.name
if ((Test-Path $out) -and -not $Force -and ((Get-FileSha256 $out) -eq $expected)) {
    Write-Host "已有校验通过的安装包，跳过下载：$out" -ForegroundColor Green
} else {
    Write-Host "下载中（约 $([math]::Round($asset.size / 1MB)) MB，请耐心等待）：$($asset.browser_download_url)"
    $part = "$out.part"
    Invoke-Download $asset.browser_download_url $part
    $actual = Get-FileSha256 $part
    if ($actual -ne $expected) {
        Remove-Item -LiteralPath $part -Force
        throw "sha256 不一致！期望 $expected，实际 $actual。文件已删除，请稍后重试（不会使用未通过校验的文件）。"
    }
    Move-Item -LiteralPath $part -Destination $out -Force
    Write-Host "sha256 校验通过：$actual" -ForegroundColor Green
}

Write-Host ""
Write-Host "安装包已保存（本脚本不会运行它）：$out" -ForegroundColor Cyan
Write-Host @"
== 安装与使用步骤 ==
1. 双击运行上面的安装包，按提示安装 WeChatDataAnalysis（Windows 可能弹出 SmartScreen 提示，确认来源后选「仍要运行」）。
2. 保持 PC 微信 4.x 处于登录状态，打开 WeChatDataAnalysis。
3. 在 WDA 里按向导「获取密钥」→「解密数据库」（只读取你自己的本地数据）。
4. 在 WDA 里开启「实时模式」，之后新消息无需重新导出。
5. 打开工作台 →「情报源」→ 微信 → 适配器选「WeChatDataAnalysis 本地 API」，地址保持 http://127.0.0.1:10392，点「测试」。
安全提醒：WDA 的本地 API（10392 端口）没有鉴权，而且允许任意网页跨域访问（CORS 为 *）。
运行期间不要打开不可信的网页，不用时请关闭 WDA。完整说明见 docs\SETUP_WECHAT.md。
"@