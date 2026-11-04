<#
.SYNOPSIS
  一键安装并启动（给第一次用的人）：检查 Python → 安装 → 第一次装时写入演示数据 → 启动工作台。
  一般不用直接运行它，双击根目录的「一键安装并启动.bat」即可。
#>
[CmdletBinding()]
param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$VenvPy = Join-Path $Root '.venv\Scripts\python.exe'

function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }
function Stop-Here([string]$m) {
    Say ''
    Say $m 'Red'
    Say ''
    Say '看不懂的话，把上面这段文字截图发给给你这个包的人。'
    exit 1
}

Say ''
Say '=== 个人情报局 · 一键安装并启动 ===' 'Cyan'
Say ('安装位置：' + $Root)

# 路径提醒：放在需要管理员权限或会被同步盘占用的位置，安装容易出问题
if ($Root -match '\\(Program Files|Windows|Temp)(\\|$)' -or $Root -match 'OneDrive') {
    Say '提醒：当前文件夹在 Program Files / Temp / OneDrive 等位置，容易因为权限或同步出问题。建议把整个文件夹移到 D:\IntelBureau 这样的普通位置再运行。' 'Yellow'
}

# 1. Python 3.12
function Test-Python312 {
    foreach ($c in @(@{ Exe = 'py'; Args = @('-3.12') }, @{ Exe = 'python'; Args = @() }, @{ Exe = 'python3'; Args = @() })) {
        if (-not (Get-Command $c.Exe -ErrorAction SilentlyContinue)) { continue }
        $extra = $c.Args
        try { $v = & $c.Exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null } catch { continue }
        if ($v -eq '3.12') { return $true }
    }
    return $false
}
if (-not (Test-Path $VenvPy)) {
    Say ''
    Say '步骤 1/3：检查 Python 3.12...' 'Cyan'
    if (-not (Test-Python312)) {
        Stop-Here ("没有找到 Python 3.12。请先安装：`n" +
                   "  1. 下载：https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe`n" +
                   "  2. 运行安装程序，第一个界面一定要勾选「Add python.exe to PATH」，再点 Install Now`n" +
                   "  3. 装完后关掉这个窗口，重新双击「一键安装并启动.bat」")
    }
    Say 'Python 3.12 已就绪。' 'Green'
}

# 2. 安装依赖、初始化（第一次要几分钟，需要联网下载依赖）
$firstTime = -not (Test-Path (Join-Path $Root 'data\bureau.db'))
Say ''
Say '步骤 2/3：安装依赖并初始化（第一次大约 2~5 分钟，需要联网，请不要关闭窗口）...' 'Cyan'
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'scripts\setup.ps1')
    if ($LASTEXITCODE -ne 0) { throw "setup 退出码 $LASTEXITCODE" }
} catch {
    Stop-Here ("安装失败：$($_.Exception.Message)`n常见原因：网络不通（可以换个网络或开关代理再试）、杀毒软件拦截、磁盘空间不足。")
}

# 3. 第一次安装：写入演示数据并跑一份演示报告，打开时大屏不是空的
if ($firstTime) {
    Say ''
    Say '第一次安装：写入演示数据（全是虚构的群和对话），并生成一份演示报告...' 'Cyan'
    try {
        & $VenvPy -X utf8 -m bureau demo seed | Out-Null
        & $VenvPy -X utf8 -m bureau run --demo --dry-run | Out-Null
        Say '演示数据已就绪。接入自己的群之后，在「系统」页点「清除演示数据」即可。' 'Green'
    } catch {
        Say ('演示数据没有写入成功（不影响使用）：' + $_.Exception.Message) 'Yellow'
    }
}

# 4. 启动
Say ''
Say '步骤 3/3：启动工作台...' 'Cyan'
Say '启动后会自动打开浏览器窗口；这个黑色窗口要一直开着，关掉它工作台就停了。' 'Yellow'
$args2 = @()
if ($NoBrowser) { $args2 += '-NoBrowser' }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'scripts\start.ps1') @args2
