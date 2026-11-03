[CmdletBinding()]
param(
    [string]$ExpectedCommit = "",

    [string]$ExpectedRef = "main"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$skillRoot = Join-Path $repoRoot "skills/zotero-plus"
$errors = [System.Collections.Generic.List[string]]::new()

function Add-Error {
    param([string]$Message)
    $errors.Add($Message)
    Write-Host "ERROR: $Message" -ForegroundColor Red
}

# 1. UPSTREAM_VERSION
$versionFile = Join-Path $skillRoot "UPSTREAM_VERSION"
if (-not (Test-Path -LiteralPath $versionFile)) {
    Add-Error "Missing UPSTREAM_VERSION"
}
else {
    $version = Get-Content -LiteralPath $versionFile -Raw
    if ($version -notmatch "(?m)^repo:\s*ActiveSky/zotero-plus\s*$") {
        Add-Error "UPSTREAM_VERSION repo must be ActiveSky/zotero-plus"
    }
    if ($version -notmatch "(?m)^ref:\s*$([regex]::Escape($ExpectedRef))\s*$") {
        Add-Error "UPSTREAM_VERSION ref does not match $ExpectedRef"
    }
    if ($ExpectedCommit -and $version -notmatch "(?m)^commit:\s*$([regex]::Escape($ExpectedCommit))\s*$") {
        Add-Error "UPSTREAM_VERSION commit does not match $ExpectedCommit"
    }
}

# 2. SKILL.md frontmatter
$skillFile = Join-Path $skillRoot "SKILL.md"
if (-not (Test-Path -LiteralPath $skillFile)) {
    Add-Error "Missing SKILL.md"
}
else {
    $head = Get-Content -LiteralPath $skillFile -TotalCount 30

    $nameLine = $head | Where-Object { $_ -match '^name:\s*(.+)$' } | Select-Object -First 1
    if (-not $nameLine) {
        Add-Error "SKILL.md missing name"
    }
    elseif ($nameLine -notmatch '^name:\s*zotero-plus\s*$') {
        Add-Error "SKILL.md name must be zotero-plus"
    }

    $descLine = $head | Where-Object { $_ -match '^description:\s*(.+)$' } | Select-Object -First 1
    if (-not $descLine) {
        Add-Error "SKILL.md missing description"
    }
    else {
        $desc = ($descLine -replace '^description:\s*', '').Trim().Trim('"').Trim("'")
        if ($desc.Length -gt 1024) {
            Add-Error "description is $($desc.Length) chars (limit 1024)"
        }
    }
}

# 3. Required upstream files
$required = @(
    "LICENSE",
    "scripts/zotero_plus.py",
    "scripts/translate/arxiv2zh.py",
    "scripts/venue/arxiv_marker.py",
    "scripts/naming/rename_attachments.py",
    "data/ccf.json",
    "data/rankings.json",
    "state/.gitkeep"
)
foreach ($relative in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $skillRoot $relative))) {
        Add-Error "Missing required file: $relative"
    }
}

# 4. Sync must not vendor git metadata or upstream CI configuration
foreach ($excluded in @(".git", ".github")) {
    if (Test-Path -LiteralPath (Join-Path $skillRoot $excluded)) {
        Add-Error "Vendored snapshot must not contain $excluded"
    }
}

# 5. Python syntax check (no bytecode written into the repository)
$python = Get-Command python3 -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python -ErrorAction SilentlyContinue
}
if ($python) {
    $parseScript = "import ast, io, sys; ast.parse(io.open(sys.argv[1], encoding='utf-8').read())"
    $pyFiles = @(Get-ChildItem -LiteralPath (Join-Path $skillRoot "scripts") -Recurse -File -Filter "*.py" -ErrorAction SilentlyContinue)
    foreach ($py in $pyFiles) {
        & $python.Source -c $parseScript $py.FullName
        if ($LASTEXITCODE -ne 0) {
            Add-Error "Python syntax error: $($py.FullName)"
        }
    }
}
else {
    Write-Host "Python not found; skipping syntax check." -ForegroundColor Yellow
}

if ($errors.Count -gt 0) {
    Write-Host ""
    Write-Host "Validation failed with $($errors.Count) error(s)." -ForegroundColor Red
    exit 1
}

Write-Host "Validation passed: zotero-plus snapshot is complete." -ForegroundColor Green
exit 0
