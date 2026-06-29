# extend-tools/fix_qemu_img_setup.ps1
# 一次性: 仅装 qemu-img, 跳过 install.ps1 Stage 0 (rustup, 已 timeout 600s)
# 触发 UAC (admin 静默装), Owner 点 Yes
# Idempotent: qemu-img.exe 已装则跳过
param([switch]$Force)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$BinDir = Join-Path $RepoRoot "extend-tools\bin\win-x64"
$StageDir = Join-Path $BinDir "_stage"
if (-not (Test-Path $StageDir)) { New-Item -ItemType Directory -Path $StageDir | Out-Null }

$qemu_install_path = "C:\Program Files\qemu"
$qemu_exe = Join-Path $qemu_install_path "qemu-img.exe"

# 1) idempotent check
if ((Test-Path $qemu_exe) -and (-not $Force)) {
    Write-Host "[skip] qemu-img already installed: $qemu_exe" -ForegroundColor Gray
    Write-Host "[next] `qemu-img --version`" -ForegroundColor Cyan
    exit 0
}

# 2) download NSIS installer
$url = "https://qemu.weilnetz.de/w64/qemu-w64-setup-2025.05.12.exe"
$installer = Join-Path $StageDir "qemu-w64-setup-2025.05.12.exe"
Write-Host "[download] $url -> $installer ..." -NoNewline
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try {
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing -TimeoutSec 300
} catch {
    # fallback: 不走默认代理 (per user memory 走 127.0.0.1:9567, 但 NSIS 大概率直连)
    Write-Host " FAILED, try without proxy..." -ForegroundColor Yellow
    $env:EXTEND_TOOLS_PROXY = ""
    Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing -TimeoutSec 300
}
Write-Host " OK ($([math]::Round((Get-Item $installer).Length / 1MB, 1)) MB)" -ForegroundColor Green

# 3) UAC trigger: NSIS 静默装到 C:\Program Files\qemu\ 必须 admin
Write-Host "[UAC] NSIS silent install /S requires admin (UAC prompt)" -ForegroundColor Cyan
Write-Host "       Please click 'Yes' to allow installing QEMU" -ForegroundColor Cyan
$proc = Start-Process -FilePath $installer -ArgumentList "/S" -Verb RunAs -Wait -NoNewWindow
if ($proc.ExitCode -ne 0) {
    throw "QEMU setup.exe silent install failed, exit code: $($proc.ExitCode)"
}

# 4) verify
if (-not (Test-Path $qemu_exe)) {
    throw "QEMU installed but qemu-img.exe not found at $qemu_install_path"
}
Remove-Item $installer -Force -ErrorAction SilentlyContinue
Write-Host "[OK] qemu-img in PATH: $qemu_exe" -ForegroundColor Green
Write-Host "[next] " -NoNewline; Write-Host "qemu-img --version" -ForegroundColor Yellow
Write-Host "       实战: " -NoNewline; Write-Host "qemu-img convert -f vmdk -O raw flag.vmdk flag.raw" -ForegroundColor Yellow
