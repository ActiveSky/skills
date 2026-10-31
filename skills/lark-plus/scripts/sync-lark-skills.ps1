[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Tag,

    [string]$Commit = "",

    [switch]$SkipValidate
)

$ErrorActionPreference = "Stop"

$skillRoot = Split-Path -Parent $PSScriptRoot
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("lark-plus-sync-" + [guid]::NewGuid().ToString("N"))

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $upstream = Join-Path $tempRoot "larksuite-cli"

    Write-Host "Cloning larksuite/cli@$Tag ..."
    Invoke-Git clone --depth 1 --branch $Tag https://github.com/larksuite/cli.git $upstream

    if (-not $Commit) {
        $Commit = (& git -C $upstream rev-parse HEAD).Trim()
    }

    $upstreamSkills = Join-Path $upstream "skills"
    if (-not (Test-Path $upstreamSkills)) {
        throw "Upstream skills directory not found: $upstreamSkills"
    }

    $incoming = Get-ChildItem $upstreamSkills -Directory -Filter "lark-*" | Sort-Object Name
    if (-not $incoming) {
        throw "No lark-* skills found in $upstreamSkills"
    }

    # Remove the previous snapshot, then copy the upstream set verbatim.
    Get-ChildItem $skillRoot -Directory -Filter "lark-*" | ForEach-Object {
        Write-Host "Removing stale $($_.Name)"
        Remove-Item $_.FullName -Recurse -Force
    }

    foreach ($dir in $incoming) {
        Write-Host "Copying $($dir.Name)"
        $dest = Join-Path $skillRoot $dir.Name
        New-Item -ItemType Directory -Path $dest -Force | Out-Null
        Get-ChildItem -LiteralPath $dir.FullName -Force |
            Copy-Item -Destination $dest -Recurse -Force
    }

    $license = Join-Path $upstream "LICENSE"
    if (Test-Path $license) {
        Copy-Item -LiteralPath $license -Destination (Join-Path $skillRoot "UPSTREAM_LICENSE") -Force
    }

    $versionFile = Join-Path $skillRoot "UPSTREAM_VERSION"
    @"
repo: larksuite/cli
tag: $Tag
commit: $Commit
synced_at: $((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))
"@ | Set-Content -LiteralPath $versionFile -Encoding utf8

    Write-Host "Synced $($incoming.Count) skills to $skillRoot"
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if (-not $SkipValidate) {
    & (Join-Path $PSScriptRoot "validate-lark-plus.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Validation failed"
    }
}
