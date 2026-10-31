[CmdletBinding()]
param(
    [string]$ExpectedTag = ""
)

$ErrorActionPreference = "Stop"

$skillRoot = Split-Path -Parent $PSScriptRoot
$errors = [System.Collections.Generic.List[string]]::new()

function Add-Error {
    param([string]$Message)
    $errors.Add($Message)
    Write-Host "ERROR: $Message" -ForegroundColor Red
}

# 1. UPSTREAM_VERSION
$versionFile = Join-Path $skillRoot "UPSTREAM_VERSION"
if (-not (Test-Path $versionFile)) {
    Add-Error "Missing UPSTREAM_VERSION"
}
else {
    $version = Get-Content $versionFile -Raw
    if ($ExpectedTag -and $version -notmatch "(?m)^tag:\s*$([regex]::Escape($ExpectedTag))\s*$") {
        Add-Error "UPSTREAM_VERSION tag does not match $ExpectedTag"
    }
}

# 2. Router frontmatter
$routerFile = Join-Path $skillRoot "SKILL.md"
$router = $null
if (-not (Test-Path $routerFile)) {
    Add-Error "Missing SKILL.md"
}
else {
    $router = Get-Content $routerFile -Raw
    $head = Get-Content $routerFile -TotalCount 30

    $nameLine = $head | Where-Object { $_ -match '^name:\s*(.+)$' } | Select-Object -First 1
    if (-not $nameLine) {
        Add-Error "SKILL.md missing name"
    }
    elseif ($nameLine -notmatch '^name:\s*lark-plus\s*$') {
        Add-Error "SKILL.md name must be lark-plus"
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

# 3. Vendored skill directories
$skillDirs = @(Get-ChildItem $skillRoot -Directory -Filter "lark-*" | Sort-Object Name)
if ($skillDirs.Count -eq 0) {
    Add-Error "No lark-* skill directories found"
}

foreach ($dir in $skillDirs) {
    $skillFile = Join-Path $dir.FullName "SKILL.md"
    if (-not (Test-Path $skillFile)) {
        Add-Error "$($dir.Name) is missing SKILL.md"
        continue
    }

    $head = Get-Content $skillFile -TotalCount 20
    $nameLine = $head | Where-Object { $_ -match '^name:\s*(.+)$' } | Select-Object -First 1
    if ($nameLine) {
        $name = ($nameLine -replace '^name:\s*', '').Trim().Trim('"').Trim("'")
        if ($name -ne $dir.Name) {
            Add-Error "$($dir.Name)/SKILL.md name '$name' does not match directory"
        }
    }

    if ($router -and $router -notmatch [regex]::Escape($dir.Name)) {
        Add-Error "router SKILL.md does not mention $($dir.Name)"
    }
}

# 4. Relative Markdown links
$linkPattern = [regex]'\]\(([^)]+)\)'
$mdFiles = @(Get-ChildItem $skillRoot -Recurse -File -Filter "*.md")
foreach ($file in $mdFiles) {
    $content = Get-Content $file.FullName -Raw
    # Ignore fenced code blocks so examples do not produce false positives.
    $content = $content -replace '(?s)```.*?```', ''

    foreach ($match in $linkPattern.Matches($content)) {
        $link = $match.Groups[1].Value.Trim()
        if ($link -match '^(https?:|mailto:|tel:|data:|#)') { continue }

        $link = ($link -split '#')[0].Trim()
        if ([string]::IsNullOrWhiteSpace($link)) { continue }
        if ($link -match '^<(.+)>$') { $link = $Matches[1] }
        if ($link.StartsWith('/')) { continue }

        # Skip placeholders and illustrative examples used in the upstream docs.
        if ($link -match '^[@$]' -or $link -match '(?i)(img_|imageurl|图片|xxx|^url$)') { continue }

        try {
            $link = [uri]::UnescapeDataString($link)
        }
        catch {
            # Keep the original link if it is not valid URL-encoded text.
        }

        $extension = [IO.Path]::GetExtension($link).ToLowerInvariant()
        if ($extension -in @('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.ico')) { continue }

        $target = Join-Path $file.DirectoryName $link
        $rootFull = [IO.Path]::GetFullPath($skillRoot).TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
        $targetFull = [IO.Path]::GetFullPath($target)
        if (-not $targetFull.StartsWith($rootFull, [StringComparison]::OrdinalIgnoreCase)) { continue }

        if (-not (Test-Path -LiteralPath $target)) {
            Add-Error "Broken link in $($file.FullName) -> $link"
        }
    }
}

if ($errors.Count -gt 0) {
    Write-Host ""
    Write-Host "Validation failed with $($errors.Count) error(s)." -ForegroundColor Red
    exit 1
}

Write-Host "Validation passed: $($skillDirs.Count) skills, $($mdFiles.Count) Markdown files." -ForegroundColor Green
exit 0
