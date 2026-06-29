# extend-tools/fix_qemu_img_setup.ps1
# Skip install.ps1 Stage 0 (rustup); only QEMU NSIS install.
# Triggers UAC (admin session needed); Owner clicks Yes.
param([switch]$Force)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$BinDir = Join-Path $RepoRoot "extend-tools\bin\win-x64"
$StageDir = Join-Path $BinDir "_stage"
if (-not (Test-Path $StageDir)) {
    New-Item -ItemType Directory -Path $StageDir | Out-Null
}

$qemu_install_path = "C:\Program Files\qemu"
$qemu_exe = Join-Path $qemu_install_path "qemu-img.exe"

# Idempotent check
if ((Test-Path $qemu_exe) -and (-not $Force)) {
    Write-Host "[skip] qemu-img already installed:" $qemu_exe -ForegroundColor Gray
    exit 0
}

# Download NSIS installer (~100MB)
$url = "https://qemu.weilnetz.de/w64/qemu-w64-setup-2025.05.12.exe"
$installer = Join-Path $StageDir "qemu-w64-setup-2025.05.12.exe"
Write-Host "[download] qemu NSIS installer ..." -NoNewline
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try {
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing -TimeoutSec 300
} catch {
    Write-Host "FAILED, retry without proxy ..." -ForegroundColor Yellow
    $env:EXTEND_TOOLS_PROXY = ""
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing -TimeoutSec 300
}
$size_bytes = (Get-Item $installer).Length
$size_mb = [int]($size_bytes / 1MB)
Write-Host " OK ($size_mb MB)" -ForegroundColor Green

# UAC trigger: NSIS /S silent install to C:\Program Files\qemu (admin)
Write-Host "[UAC] Click Yes on the User Account Control dialog" -ForegroundColor Cyan
$proc = Start-Process -FilePath $installer -ArgumentList "/S" -Verb RunAs -Wait -NoNewWindow
if ($proc.ExitCode -ne 0) {
    throw "QEMU silent install failed, exit: $($proc.ExitCode)"
}

# Verify
if (-not (Test-Path $qemu_exe)) {
    throw "qemu-img.exe not found at $qemu_install_path"
}
Remove-Item $installer -Force -ErrorAction SilentlyContinue
Write-Host "[OK] qemu-img in PATH:" $qemu_exe -ForegroundColor Green
Write-Host "[next] verify:" -ForegroundColor Cyan
Write-Host "  qemu-img --version"
Write-Host "[next] run real binary:"
Write-Host "  qemu-img convert -f vmdk -O raw flag.vmdk flag.raw"
