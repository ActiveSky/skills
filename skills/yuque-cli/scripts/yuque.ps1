$ErrorActionPreference = 'Stop'

$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到 $python。请先在 skill 根目录运行 .\bootstrap.ps1"
}

& $python (Join-Path $PSScriptRoot 'yuque.py') @args
exit $LASTEXITCODE
