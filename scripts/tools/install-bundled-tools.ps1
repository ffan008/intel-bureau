<#
.SYNOPSIS
  安装随包带的三个接入工具（不需要联网）：微信 WeChatDataAnalysis、QQ NapCatQQ、飞书 lark-cli。
  一般不用直接运行，双击根目录的「安装接入工具.bat」即可。
.PARAMETER Tool
  menu（默认，显示菜单）/ wechat / qq / feishu / all
.PARAMETER NoRun
  只校验和准备，不运行安装程序（测试用）。
#>
[CmdletBinding()]
param(
    [ValidateSet('menu', 'wechat', 'qq', 'feishu', 'all')][string]$Tool = 'menu',
    [switch]$NoRun
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Tools = Join-Path $Root 'third_party\tools'

function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }
function Sha256([string]$p) { (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLowerInvariant() }
function Ask([string]$q) { if ($NoRun) { return $false }; (Read-Host "$q (Y/n)") -notmatch '^[nN]' }

# ---------------------------------------------------------------- 微信
function Install-Wechat {
    Say ''
    Say '=== 微信：WeChatDataAnalysis ===' 'Cyan'
    $dir = Join-Path $Tools 'wda'
    $setup = Get-ChildItem -LiteralPath $dir -Filter '*Setup.exe' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $setup) { Say '包里没有找到安装程序（third_party\tools\wda）。可以运行 scripts\tools\get-wechat-data-analysis.ps1 联网下载。' 'Red'; return }
    $sums = Join-Path $dir 'v2.10.0-SHA256SUMS.txt'
    $expected = $null
    if (Test-Path -LiteralPath $sums) {
        foreach ($line in Get-Content -LiteralPath $sums -Encoding UTF8) {
            if ($line -match '^([0-9A-Fa-f]{64})\s+\*?(.+Setup\.exe)\s*$' -and $Matches[2] -eq $setup.Name) { $expected = $Matches[1].ToLowerInvariant() }
        }
    }
    Say ('校验安装程序（{0:N0} MB，需要几秒）...' -f ($setup.Length / 1MB))
    $actual = Sha256 $setup.FullName
    if ($expected -and $actual -ne $expected) { Say "校验不一致！文件可能损坏，请重新获取压缩包。期望 $expected，实际 $actual" 'Red'; return }
    Say ($(if ($expected) { '校验通过（与官方 SHA-256 一致）。' } else { '没有找到官方校验值，已跳过比对。' })) 'Green'
    Say ('安装程序：' + $setup.FullName)
    if (Ask '现在运行安装程序吗？（会弹出安装向导，一路下一步即可）') {
        Start-Process -FilePath $setup.FullName
        Say '安装向导已打开。装好后打开「微信数据分析助手」，按 docs\SETUP_WECHAT.md 登录并完成解密，然后回到工作台「情报源」→ 微信，打开启用开关。' 'Yellow'
    } else {
        Say '需要时双击上面这个 Setup.exe 即可。装好后按 docs\SETUP_WECHAT.md 操作。'
    }
}

# ---------------------------------------------------------------- QQ
function Install-Qq {
    Say ''
    Say '=== QQ：NapCatQQ ===' 'Cyan'
    $base = Join-Path $Tools 'napcat'
    $zip = Get-ChildItem -LiteralPath $base -Filter '*NapCat.Shell.zip' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $zip) { Say '包里没有找到 NapCat（third_party\tools\napcat）。可以运行 scripts\tools\get-napcat.ps1 联网下载。' 'Red'; return }
    $tag = ($zip.Name -split '-')[0]
    $expected = '6801f93e533846cea05f4f531874a0e84371ab2331c5585b57cd7e3b869cf96b'
    $target = Join-Path (Join-Path $base $tag) 'Shell'
    $marker = Join-Path $target '.bureau-verified.json'
    $done = $false
    if (Test-Path -LiteralPath $marker) {
        try { if ((Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json).sha256 -eq $expected) { $done = $true } } catch { }
    }
    if ($done) {
        Say ('已经解压过了：' + $target) 'Green'
    } else {
        Say '校验压缩包...'
        $actual = Sha256 $zip.FullName
        if ($actual -ne $expected) { Say "校验不一致！文件可能损坏，请重新获取压缩包。期望 $expected，实际 $actual" 'Red'; return }
        Say '校验通过，解压中...' 'Green'
        $tmp = "$target.extracting"
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
        Expand-Archive -LiteralPath $zip.FullName -DestinationPath $tmp -Force
        if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        Move-Item -LiteralPath $tmp -Destination $target
        [ordered]@{ asset = 'NapCat.Shell.zip'; tag = $tag; sha256 = $expected; verified_at = (Get-Date).ToString('s'); source = 'bundled' } |
            ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
        Say ('已解压到：' + $target) 'Green'
    }
    Say ''
    Say '接下来（详细步骤见 docs\SETUP_QQ.md）：' 'Yellow'
    Say '  1. 电脑上要装有 QQ（NT 版）。强烈建议用一个「小号」登录，不要用主号。'
    Say '  2. 双击下面的启动文件（Windows 11 选第一个，Windows 10 选第二个），弹出二维码后用小号扫码：'
    Say ('       ' + (Join-Path $target 'launcher-user.bat'))
    Say ('       ' + (Join-Path $target 'launcher-win10-user.bat'))
    Say '  3. 浏览器打开 http://127.0.0.1:6099 ，新建一个「HTTP 服务器」：主机 127.0.0.1、端口 3010，并设一个 token。'
    Say '  4. 回到工作台「情报源」→ QQ，填入同一个 token，点「测试」。'
}

# ---------------------------------------------------------------- 飞书
function Install-Feishu {
    Say ''
    Say '=== 飞书：lark-cli（官方命令行工具）===' 'Cyan'
    $exe = Join-Path $Tools 'lark-cli\node_modules\@larksuite\cli\bin\lark-cli.exe'
    if (-not (Test-Path -LiteralPath $exe)) { Say '包里没有找到 lark-cli。可以先装 Node.js，再运行 scripts\tools\get-lark-cli.ps1 联网安装。' 'Red'; return }
    $ver = (& $exe --version 2>&1 | Select-Object -First 1)
    Say ("lark-cli 已就绪：$ver（不需要安装 Node.js，工作台会自动找到它）") 'Green'
    Say ''
    Say '接下来（详细步骤见 docs\SETUP_FEISHU.md）：' 'Yellow'
    Say '  1. 第一次使用要配置一个飞书应用：运行下面这条命令，按提示在浏览器里操作。'
    Say ('       "' + $exe + '" config init')
    Say '  2. 然后双击根目录的「飞书重新授权.bat」，在浏览器里点「授权」。'
    Say '  3. 回到工作台「情报源」→ 飞书，打开启用开关，点「测试」。'
    if (Ask '现在运行「config init」吗？') {
        & $exe config init
    }
}

function Show-Menu {
    Say ''
    Say '=== 个人情报局 · 安装接入工具 ===' 'Cyan'
    Say '想读取哪个平台的群消息，就装哪个。只想看演示或导入聊天记录文件的话，这三个都不用装。'
    Say ''
    Say '  1  微信（WeChatDataAnalysis，约 380 MB 安装程序）'
    Say '  2  QQ（NapCatQQ）'
    Say '  3  飞书（lark-cli）'
    Say '  4  三个都准备'
    Say '  0  退出'
    Say ''
    switch ((Read-Host '请输入数字').Trim()) {
        '1' { Install-Wechat }
        '2' { Install-Qq }
        '3' { Install-Feishu }
        '4' { Install-Wechat; Install-Qq; Install-Feishu }
        default { }
    }
}

switch ($Tool) {
    'wechat' { Install-Wechat }
    'qq' { Install-Qq }
    'feishu' { Install-Feishu }
    'all' { Install-Wechat; Install-Qq; Install-Feishu }
    default { Show-Menu }
}
