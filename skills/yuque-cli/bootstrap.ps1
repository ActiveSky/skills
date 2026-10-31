$ErrorActionPreference = 'Stop'

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "需要 uv。安装：https://docs.astral.sh/uv/"
}

$root = $PSScriptRoot
$venv = Join-Path $root '.venv'
$python = Join-Path $venv 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    uv venv $venv
    if ($LASTEXITCODE -ne 0) { throw "uv venv 失败" }
}

uv pip install --python $python -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw "uv pip install 失败" }

Write-Host "Vendored yuque-cli ready."
Write-Host "Run: $root\scripts\yuque.ps1 --help"
