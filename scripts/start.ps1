<#
.SYNOPSIS
  启动情报局工作台，并用 Edge 应用模式（或默认浏览器）打开 http://127.0.0.1:8765。
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\start.ps1
  powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -NoBrowser
#>
[CmdletBinding()]
param(
    [int]$Port = 8765,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$VenvPy = Join-Path $Root '.venv\Scripts\python.exe'
$Url = "http://127.0.0.1:$Port"

if (-not (Test-Path $VenvPy)) {
    throw '还没有安装。请先运行：powershell -ExecutionPolicy Bypass -File scripts\setup.ps1'
}

function Test-Bureau {
    try {
        $r = Invoke-RestMethod -Uri "$Url/api/health" -TimeoutSec 2
        return [bool]$r.ok
    } catch {
        return $false
    }
}

function Open-Dashboard {
    if ($NoBrowser) { return }
    $edgePaths = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\Application\msedge.exe')
    )
    $edge = $edgePaths | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if ($edge) {
        Start-Process -FilePath $edge -ArgumentList "--app=$Url", '--window-size=1920,1080'
    } else {
        Start-Process $Url
    }
}

if (Test-Bureau) {
    Write-Host "工作台已在运行：$Url" -ForegroundColor Green
    Write-Host '已为你打开大屏窗口；这个窗口可以直接关掉，不影响正在运行的工作台。' -ForegroundColor Gray
    Open-Dashboard
    if (-not $NoBrowser) { Start-Sleep -Seconds 4 }          # 让提示留在屏幕上，不要一闪而过
    return
}

Write-Host "启动工作台：$Url （关闭本窗口或按 Ctrl+C 停止）" -ForegroundColor Cyan
$proc = Start-Process -FilePath $VenvPy -ArgumentList @('-X', 'utf8', '-m', 'bureau', 'serve', '--port', "$Port") `
    -WorkingDirectory $Root -NoNewWindow -PassThru

$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    if ($proc.HasExited) { break }
    if (Test-Bureau) { $ready = $true; break }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) {
    if ($proc.HasExited) {
        throw ("服务启动失败（退出码 $($proc.ExitCode)）。常见原因：端口 $Port 被别的程序占用、依赖没装完整、杀毒软件拦截。`n" +
               "可以重新双击「一键安装并启动.bat」修复安装，或运行 .venv\Scripts\python.exe -X utf8 -m bureau doctor 查看原因。")
    }
    Write-Warning '服务 30 秒内没有就绪，仍会继续等待；可以稍后手动打开浏览器。'
} else {
    Open-Dashboard
}
Wait-Process -Id $proc.Id
