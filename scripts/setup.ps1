<#
.SYNOPSIS
  情报局工作台：创建或更新虚拟环境、安装依赖、构建前端、初始化配置。
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SkipWeb
#>
[CmdletBinding()]
param(
    [switch]$SkipWeb,
    [switch]$Dev,
    [switch]$RebuildWeb
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$VenvPy = Join-Path $Root '.venv\Scripts\python.exe'

function Write-Step([string]$Text) { Write-Host "==> $Text" -ForegroundColor Cyan }

function Find-Python312 {
    $candidates = @(
        @{ Exe = 'py'; Args = @('-3.12') },
        @{ Exe = 'python'; Args = @() },
        @{ Exe = 'python3'; Args = @() }
    )
    foreach ($c in $candidates) {
        if (-not (Get-Command $c.Exe -ErrorAction SilentlyContinue)) { continue }
        $extra = $c.Args
        try {
            $ver = & $c.Exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        } catch { continue }
        if ($ver -eq '3.12') { return $c }
    }
    return $null
}

# 1. 虚拟环境
if (-not (Test-Path $VenvPy)) {
    Write-Step '创建虚拟环境 .venv（需要 Python 3.12）'
    $py = Find-Python312
    if (-not $py) {
        throw '没有找到 Python 3.12。请从 https://www.python.org/downloads/ 安装 3.12，或安装 py 启动器后重试。'
    }
    $pyArgs = $py.Args
    & $py.Exe @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败' }
} else {
    Write-Step '已有虚拟环境 .venv，更新依赖'
}

# 2. Python 依赖
Write-Step '安装 Python 依赖'
& $VenvPy -m pip install --disable-pip-version-check -q --upgrade pip
$req = if ($Dev) { 'requirements-dev.txt' } else { 'requirements.txt' }
& $VenvPy -m pip install --disable-pip-version-check -q -r $req
if ($LASTEXITCODE -ne 0) { throw "pip install -r $req 失败" }

# 3. 前端（存在 web/package.json 时）
$WebPkg = Join-Path $Root 'web\package.json'
$HasDist = Test-Path (Join-Path $Root 'web\dist\index.html')
if ($HasDist -and -not $RebuildWeb) {
    Write-Step '前端已经构建好（web\dist），跳过构建；需要重新构建时加 -RebuildWeb'
} elseif (-not $SkipWeb -and (Test-Path $WebPkg)) {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        Write-Step '构建前端（npm ci && npm run build）'
        Push-Location (Join-Path $Root 'web')
        try {
            npm ci
            if ($LASTEXITCODE -ne 0) { throw 'npm ci 失败' }
            npm run build
            if ($LASTEXITCODE -ne 0) { throw 'npm run build 失败' }
        } finally {
            Pop-Location
        }
    } else {
        Write-Warning '没有找到 npm（需要 Node.js 20.19 以上），跳过前端构建；访问工作台时会显示提示页。'
    }
} elseif (-not (Test-Path $WebPkg)) {
    Write-Step '没有 web/package.json，跳过前端构建'
}

# 4. 初始化配置与数据库
Write-Step '初始化配置与数据库'
& $VenvPy -X utf8 -m bureau init
if ($LASTEXITCODE -ne 0) { throw '初始化失败' }

Write-Host ''
Write-Host '安装完成。' -ForegroundColor Green
Write-Host '  体检：   .venv\Scripts\python.exe -X utf8 -m bureau doctor'
Write-Host '  演示：   .venv\Scripts\python.exe -X utf8 -m bureau demo seed'
Write-Host '  启动：   powershell -ExecutionPolicy Bypass -File scripts\start.ps1'
