# extend-tools/install.ps1
# AutoMisc cross-platform extend-tools installer (per v0.5-platform-extend-tools governance change)
#
# Usage (Windows PowerShell 5.1+ / PowerShell 7+):
#   cd D:\hacktools\misc\automisc
#   powershell -ExecutionPolicy Bypass -File "extend-tools\install.ps1"
#
# Idempotent: existing binaries are skipped on re-run (unless -Force)
# Failure handling: single tool failure does not block others; summary at end
# SHA256: printed after download, user manually fills into manifest.yaml
#
# Proxy (per user memory: China mainland):
#   Default: http://127.0.0.1:9567
#   Override: $env:EXTEND_TOOLS_PROXY = "" (disable) or set custom URL
#
# Maintenance: add new tool -> edit $binaries array here AND manifest.yaml (both)

[CmdletBinding()]
param(
    [switch]$Force  # Force re-download (ignore existing)
)

$ErrorActionPreference = "Continue"

# ---- Proxy (China mainland network per user memory) ----
$ProxyUrl = $env:EXTEND_TOOLS_PROXY
if ([string]::IsNullOrWhiteSpace($ProxyUrl)) {
    $ProxyUrl = "http://127.0.0.1:9567"
}
Write-Host "[proxy] Using: $ProxyUrl (set `$env:EXTEND_TOOLS_PROXY='' to disable)" -ForegroundColor Cyan

# ---- Paths ----
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$BinDir = Join-Path $RepoRoot "extend-tools\bin\win-x64"
$StageDir = Join-Path $RepoRoot "extend-tools\bin\win-x64\_stage"

# ---- Binaries to download ----
# binwalk is NOT here: it's a Python package, handled in $pip_packages below.
$binaries = @(
    @{
        name = "exiftool"
        version = "13.29"
        # exiftool.org main site down (2026-06-27), SourceForge /download returns HTML
        # Use ShareX maintained Windows prebuilt (direct GitHub release asset)
        url = "https://github.com/ShareX/ExifTool/releases/download/v13.29/exiftool-13.29-win64.zip"
        target = "exiftool.exe"
        post_extract = "exiftool_zip"
    },
    @{
        name = "7zr"
        version = "24.07"
        url = "https://www.7-zip.org/a/7zr.exe"
        target = "7zr.exe"
        post_extract = "sevenz_link"
    },
    @{
        name = "foremost"
        version = "1.5.7"
        url = "https://github.com/raddyfiy/foremost/raw/master/binary/foremost.exe"
        target = "foremost.exe"
        post_extract = $null
    }
)

# ---- Python packages (pip install from source) ----
# binwalk: no official Windows prebuilt (ReFirmLabs never published release assets).
#          v3 is Rust rewrite, v2 latest PyPI is 2.1.0 (incompatible with Python 3.12+).
#          -> download v2.3.2 source zip + patch compat.py + pip install from source.
$pip_packages = @(
    @{
        name = "binwalk"
        version = "2.3.2"
        url = "https://github.com/ReFirmLabs/binwalk/archive/refs/tags/v2.3.2.zip"
        notes = "v2.3.2 source + patch (imp -> importlib) for Python 3.12+ compat"
    }
)

# ---- Helper: download a URL to a path ----
function Download-File {
    param([string]$Url, [string]$Out)
    Write-Host "[download] $Url -> $Out" -NoNewline
    Invoke-WebRequest -Uri $Url -OutFile $Out -UseBasicParsing -TimeoutSec 120 -ErrorAction Stop -Proxy $ProxyUrl
    Write-Host " OK" -ForegroundColor Green
}

# ---- Ensure dirs ----
if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
}
if (Test-Path $StageDir) {
    Remove-Item $StageDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

Write-Host ""
Write-Host "=== AutoMisc extend-tools installer (v0.5-platform-extend-tools) ===" -ForegroundColor Cyan
Write-Host "Target: $BinDir"
Write-Host ""

$results = @()

# ---- Stage 1: Download + extract binaries ----
Write-Host "--- Stage 1: Binaries (3 tools) ---" -ForegroundColor Cyan

foreach ($tool in $binaries) {
    $dest = Join-Path $BinDir $tool.target

    if ((Test-Path $dest) -and (-not $Force)) {
        Write-Host "[skip] $($tool.name): already exists at $dest" -ForegroundColor Gray
        $results += [PSCustomObject]@{name=$tool.name; status="skipped"; path=$dest}
        continue
    }

    $tmp = Join-Path $StageDir "$($tool.name).download"

    try {
        Download-File -Url $tool.url -Out $tmp

        switch ($tool.post_extract) {
            "exiftool_zip" {
                Write-Host "[extract] $($tool.name) unzip + setup ..." -NoNewline
                Add-Type -AssemblyName System.IO.Compression.FileSystem
                $extract_dir = Join-Path $StageDir "$($tool.name)_extract"
                if (Test-Path $extract_dir) { Remove-Item $extract_dir -Recurse -Force }
                [System.IO.Compression.ZipFile]::ExtractToDirectory($tmp, $extract_dir)
                # ShareX zip: exiftool.exe + exiftool_files/ at root
                # Official zip: exiftool(-k).exe + exiftool_files/ at root
                $inner = Get-ChildItem -Path $extract_dir -Filter "exiftool.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
                if (-not $inner) {
                    $inner = Get-ChildItem -Path $extract_dir -Recurse -Filter "exiftool(-k).exe" | Select-Object -First 1
                    if (-not $inner) {
                        throw "exiftool.exe (or exiftool(-k).exe) not found in zip"
                    }
                }
                Move-Item $inner.FullName $dest -Force
                # exiftool_files/ directory is perl lib, required next to exiftool.exe
                $lib_dir = Join-Path $extract_dir "exiftool_files"
                $dest_lib = Join-Path $BinDir "exiftool_files"
                if (Test-Path $lib_dir) {
                    if (Test-Path $dest_lib) { Remove-Item $dest_lib -Recurse -Force }
                    Move-Item $lib_dir $dest_lib -Force
                }
                Remove-Item $extract_dir -Recurse -Force
                Remove-Item $tmp -Force -ErrorAction SilentlyContinue
                Write-Host " OK" -ForegroundColor Green
            }
            "sevenz_link" {
                Move-Item $tmp $dest -Force
                # Create 7z.exe hardlink (adapter uses '7z' name, standalone exe is '7zr')
                $link = Join-Path $BinDir "7z.exe"
                if (-not (Test-Path $link)) {
                    $result = cmd /c mklink /H "$link" "$dest" 2>&1
                    if ($LASTEXITCODE -ne 0) {
                        Write-Host "[warn] mklink failed, copying instead" -ForegroundColor Yellow
                        Copy-Item $dest $link -Force
                    }
                }
                Write-Host "[link] 7z.exe -> 7zr.exe" -ForegroundColor Green
            }
            default {
                Move-Item $tmp $dest -Force
            }
        }

        # Compute SHA256 (user fills into manifest.yaml)
        $hash = (Get-FileHash $dest -Algorithm SHA256).Hash
        Write-Host "[sha256] $($tool.name): $hash"
        Write-Host "         Copy to manifest.yaml tool.sha256 field" -ForegroundColor Gray
        Write-Host ""

        $results += [PSCustomObject]@{name=$tool.name; status="ok"; path=$dest; sha256=$hash}

    } catch {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "         error: $_" -ForegroundColor Red
        if (Test-Path $tmp) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
        $results += [PSCustomObject]@{name=$tool.name; status="failed"; error="$_"}
    }
}

# ---- Stage 2: pip install binwalk (from patched source) ----
Write-Host ""
Write-Host "--- Stage 2: Python packages (1 tool, source + patch) ---" -ForegroundColor Cyan

foreach ($pkg in $pip_packages) {
    # Quick check: already installed at correct version?
    $installed_ok = $false
    try {
        $ver = & python -c "import binwalk; print(binwalk.__version__)" 2>$null
        if ($ver -eq $pkg.version) {
            $installed_ok = $true
            Write-Host "[skip] $($pkg.name): v$($pkg.version) already installed" -ForegroundColor Gray
            $results += [PSCustomObject]@{name=$pkg.name; status="skipped"; path="python -m binwalk"}
        }
    } catch {}

    if ($installed_ok) { continue }

    try {
        Write-Host "[download] $($pkg.name) v$($pkg.version) source ..." -NoNewline
        $src_zip = Join-Path $StageDir "$($pkg.name)-v$($pkg.version).zip"
        Download-File -Url $pkg.url -Out $src_zip | Out-Null
        # Download-File already prints OK; suppress

        Write-Host "[extract] $($pkg.name) source ..." -NoNewline
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $src_extract = Join-Path $StageDir "$($pkg.name)-v$($pkg.version)"
        if (Test-Path $src_extract) { Remove-Item $src_extract -Recurse -Force }
        [System.IO.Compression.ZipFile]::ExtractToDirectory($src_zip, $StageDir)
        Write-Host " OK" -ForegroundColor Green

        # Patch compat.py: append _imp_load_source helper (Python 3.12+ removed imp)
        $compat_py = Join-Path $src_extract "src\binwalk\core\compat.py"
        if (-not (Test-Path $compat_py)) {
            throw "compat.py not found at $compat_py (source layout changed?)"
        }
        $compat_content = Get-Content $compat_py -Raw -Encoding UTF8
        if ($compat_content -notmatch "def _imp_load_source") {
            $patch = @'


# v0.5-platform-extend-tools: Python 3.12+ removed `imp` module.
# Drop-in replacement using importlib (used by plugin.py and module.py).
import importlib.util as _il_util


def _imp_load_source(name, path):
    """Drop-in replacement for removed ``imp.load_source(name, path)``."""
    spec = _il_util.spec_from_file_location(name, path)
    mod = _il_util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
'@
            Add-Content -Path $compat_py -Value $patch -Encoding UTF8
            Write-Host "[patch] $($pkg.name) compat.py: added _imp_load_source" -ForegroundColor Gray
        }

        # Patch plugin.py + module.py: use compat._imp_load_source instead of imp.load_source
        foreach ($rel in @("src\binwalk\core\plugin.py", "src\binwalk\core\module.py")) {
            $py = Join-Path $src_extract $rel
            if (Test-Path $py) {
                $c = Get-Content $py -Raw -Encoding UTF8
                $changed = $false
                if ($c -match "^import imp\b") {
                    $c = $c -replace "^import imp\b", "# import imp removed (Python 3.12+)"
                    $changed = $true
                }
                if ($c -match "imp\.load_source") {
                    $c = $c -replace "imp\.load_source", "_imp_load_source"
                    # Add import if missing
                    if ($c -notmatch "from binwalk\.core\.compat import _imp_load_source") {
                        $c = $c -replace "(^import os\r?\n)", "`$1from binwalk.core.compat import _imp_load_source`r`n"
                    }
                    $changed = $true
                }
                if ($changed) {
                    Set-Content $py -Value $c -Encoding UTF8 -NoNewline
                    Write-Host "[patch] $rel : imp -> compat._imp_load_source" -ForegroundColor Gray
                }
            }
        }

        Write-Host "[pip install] $($pkg.name) v$($pkg.version) (no-deps) ..." -NoNewline
        & python -m pip install --proxy $ProxyUrl --force-reinstall --no-deps --quiet $src_extract
        if ($LASTEXITCODE -ne 0) {
            throw "pip install failed with exit $LASTEXITCODE"
        }
        Write-Host " OK" -ForegroundColor Green

        $results += [PSCustomObject]@{name=$pkg.name; status="ok"; path="python -m binwalk v$($pkg.version)"}

    } catch {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "         error: $_" -ForegroundColor Red
        $results += [PSCustomObject]@{name=$pkg.name; status="failed"; error="$_"}
    }
}

# ---- Cleanup stage ----
if (Test-Path $StageDir) {
    Remove-Item $StageDir -Recurse -Force -ErrorAction SilentlyContinue
}

# ---- Summary ----
Write-Host ""
Write-Host "=== Summary ===" -ForegroundColor Cyan
$ok_count = 0; $skip_count = 0; $fail_count = 0
foreach ($r in $results) {
    switch ($r.status) {
        "ok" {
            Write-Host "  [OK]      $($r.name)" -ForegroundColor Green
            $ok_count++
        }
        "skipped" {
            Write-Host "  [SKIP]    $($r.name) (already installed)" -ForegroundColor Gray
            $skip_count++
        }
        "failed" {
            Write-Host "  [FAILED]  $($r.name) - $($r.error)" -ForegroundColor Red
            $fail_count++
        }
    }
}

Write-Host ""
Write-Host "Total: $($results.Count) | OK: $ok_count | SKIP: $skip_count | FAILED: $fail_count"
Write-Host ""

if ($fail_count -gt 0) {
    Write-Host "WARNING: Some tools failed. You can:" -ForegroundColor Yellow
    Write-Host "   1. Re-run: powershell -ExecutionPolicy Bypass -File extend-tools\install.ps1 -Force" -ForegroundColor Yellow
    Write-Host "   2. Manually download (copy url from manifest.yaml to browser, place in $BinDir)" -ForegroundColor Yellow
    Write-Host "   3. Check network / GitHub rate limit" -ForegroundColor Yellow
    exit 1
}

Write-Host "All done. You can now run automisc-gui." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  cd $RepoRoot"
Write-Host "  .venv\Scripts\Activate.ps1   # if venv not yet activated"
Write-Host "  automisc-gui                  # or: python -m automisc gui"
Write-Host ""
Write-Host "Verify: python -m automisc tools list  (should show binwalk / exiftool / 7zr / foremost)"