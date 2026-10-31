$ErrorActionPreference = 'Stop'

$root = Split-Path $PSScriptRoot -Parent
$candidates = @(
    (Join-Path $root '.venv\Scripts\python.exe'),
    (Join-Path $env:USERPROFILE '.agents\skills\yuque-cli\.venv\Scripts\python.exe')
)
$python = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $python) {
    throw "未找到 Python 环境。请先运行 $root\bootstrap.ps1（或 .agents 下同名 skill 的 bootstrap.ps1）"
}

& $python (Join-Path $PSScriptRoot 'yuque.py') @args
exit $LASTEXITCODE
