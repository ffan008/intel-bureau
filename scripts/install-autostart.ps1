<#
.SYNOPSIS
  通过 Windows 任务计划程序设置开机（登录）自启：用 pythonw 隐藏运行 python -m bureau serve。
.DESCRIPTION
  只为当前用户注册，不需要管理员权限，不提升权限。卸载：scripts\uninstall-autostart.ps1
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = 'IntelBureau',
    [int]$Port = 8765,
    [int]$DelaySeconds = 30
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Pythonw = Join-Path $Root '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $Pythonw)) {
    throw "没有找到 $Pythonw。请先运行 scripts\setup.ps1"
}

$user = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $Pythonw -Argument "-X utf8 -m bureau serve --port $Port" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$trigger.Delay = 'PT{0}S' -f $DelaySeconds
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

if ($PSCmdlet.ShouldProcess($TaskName, '注册登录自启任务')) {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description '情报局工作台：登录后在后台启动 http://127.0.0.1:8765（定时出报、补跑错过的任务）' -Force | Out-Null
    Write-Host "已注册任务「$TaskName」：登录 $DelaySeconds 秒后在后台启动工作台。" -ForegroundColor Green
    Write-Host '立即启动：Start-ScheduledTask -TaskName ' $TaskName
}
