<#
.SYNOPSIS
  删除 install-autostart.ps1 注册的登录自启任务（不影响数据与配置）。
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\uninstall-autostart.ps1
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = 'IntelBureau'
)

$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "没有找到任务「$TaskName」，无需卸载。"
    return
}
if ($PSCmdlet.ShouldProcess($TaskName, '删除登录自启任务')) {
    if ($task.State -eq 'Running') {
        Stop-ScheduledTask -TaskName $TaskName
    }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "已删除任务「$TaskName」。正在运行的工作台进程不会被结束，可在任务管理器里结束 pythonw.exe。" -ForegroundColor Green
}
