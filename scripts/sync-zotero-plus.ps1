[CmdletBinding()]
param(
    [string]$Ref = "main",

    [string]$Commit = "",

    [switch]$SkipValidate
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$skillRoot = Join-Path $repoRoot "skills/zotero-plus"
$upstreamUrl = "https://github.com/ActiveSky/zotero-plus.git"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("zotero-plus-sync-" + [guid]::NewGuid().ToString("N"))

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & git @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

try {
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    $upstream = Join-Path $tempRoot "zotero-plus"

    Write-Host "Cloning ActiveSky/zotero-plus@$Ref ..."
    Invoke-Git clone --depth 1 --branch $Ref $upstreamUrl $upstream

    if (-not $Commit) {
        $Commit = (& git -C $upstream rev-parse HEAD).Trim()
    }

    # Rebuild the vendored snapshot from scratch so removed upstream files do not linger.
    if (Test-Path -LiteralPath $skillRoot) {
        Remove-Item -LiteralPath $skillRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $skillRoot -Force | Out-Null

    # The whole upstream repository is the skill; skip only git metadata and
    # upstream-only CI configuration.
    Get-ChildItem -LiteralPath $upstream -Force |
        Where-Object { $_.Name -notin @(".git", ".github") } |
        Copy-Item -Destination $skillRoot -Recurse -Force

    $versionFile = Join-Path $skillRoot "UPSTREAM_VERSION"
    $versionText = @"
repo: ActiveSky/zotero-plus
ref: $Ref
commit: $Commit
synced_at: $((Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))
"@
    # Always write LF so Windows and CI produce identical files.
    $versionText = ($versionText -replace "`r`n", "`n") + "`n"
    Set-Content -LiteralPath $versionFile -Value $versionText -Encoding utf8 -NoNewline

    Write-Host "Synced zotero-plus into $skillRoot"
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if (-not $SkipValidate) {
    & (Join-Path $repoRoot "scripts/validate-zotero-plus.ps1") -ExpectedCommit $Commit -ExpectedRef $Ref
    if ($LASTEXITCODE -ne 0) {
        throw "Validation failed"
    }
}
