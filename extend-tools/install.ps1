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
        name = "7zip"
        version = "23.01"
        # 7-Zip 23.01 Windows x64 安装器 (NSIS, 1.5MB 安装器, 展开后 ~5MB).
        # per v0.5-7z-layout-migrate (Owner 2026-06-30 21:53 拍板):
        # 从 7zr standalone 1MB 切到完整安装, 部署到 extend-tools/bin/win-x64/7-Zip/ subdir.
        url = "https://www.7-zip.org/a/7z2301-x64.exe"
        target = "7-Zip\7z.exe"  # indicator path (skip check 命中这个)
        post_extract = "sevenz_extract"
    },
    @{
        name = "foremost"
        version = "1.5.7"
        url = "https://github.com/raddyfiy/foremost/raw/master/binary/foremost.exe"
        target = "foremost.exe"
        post_extract = $null
    },
    @{
        name = "file"
        version = "5.29"
        # nscaife/file-windows 2017-01-08 release (latest). file CLI Win 不可用,
        # libmagic 预编译 + GPL 兼容 license.
        url = "https://github.com/nscaife/file-windows/releases/download/20170108/file-windows-20170108.zip"
        target = "file.exe"
        post_extract = "file_zip"
    }
)

# 注: evtx_dump (omerbenamram/evtx v0.12.2 Rust CLI) **不**走 install.ps1 — 2026-06-28 决策:
# 当前 adapter (src/automisc/tools/forensics/log/evtx_dump.py) 用 python-evtx 0.8.1 实现
# (结构化字段访问 + EventID scoring + 命令行关键字匹配), evtx_dump CLI 在 adapter 路径上 0 调用.
# 实际价值 = Owner 手动 `evtx_dump file.evtx | grep flag` (便利, 可被 5 行 Python one-liner 替代).
# 详见 upgrade/v0.5-windows-evtx-dump.md §6 决策记录 + AGENTS.md §5.2 防单题打补丁.
# v0.5+ 实战 ≥3 道同类命中再升架构 (per AGENTS §5.2 标准).

# ---- Python packages (pip install from source) ----
# binwalk: no official Windows prebuilt (ReFirmLabs never published release assets).
#          v3 is Rust rewrite, v2 latest PyPI is 2.1.0 (incompatible with Python 3.12+).
#          -> download v2.3.2 source zip + patch compat.py + pip install from source.
# pyzbar: per v0.5-zbar-windows-install (2026-06-28 Owner 拍板).
#         Win wheel 自带 zbar DLL, 替代 zbarimg subprocess (SourceForge 失效).
# pyc 反编译三件套: per v0.5-pyc-deps-install (2026-07-01 Owner 实战 flag.pyc 触发).
#                   xdis 拿 magic + version, uncompyle6 解 Py2.x, decompyle3 解 Py3.x,
#                   dis fallback 走 builtin. 缺任一, pyc_decompiler decoder 跑不动.
$pip_packages = @(
    @{
        name = "binwalk"
        version = "2.3.2"
        install_method = "source"
        url = "https://github.com/ReFirmLabs/binwalk/archive/refs/tags/v2.3.2.zip"
        notes = "v2.3.2 source + patch (imp -> importlib) for Python 3.12+ compat"
    },
    @{
        name = "pyzbar"
        version = "0.1.9"
        install_method = "pypi"
        # pyzbar 0.1.9 Win wheel 自带 libzbar-64.dll + libiconv.dll (per PyPI 主页)
        # 装完即可 `from pyzbar.pyzbar import decode` 直接用, 无需再 pip 安装 zbar 库.
        notes = "v0.5-zbar-windows-install: 替代 zbarimg.exe subprocess (SourceForge 失效)"
    },
    @{
        name = "xdis"
        version = "6.1.7"
        install_method = "pypi"
        # xdis 6.1.7 (2026-07 PyPI latest in 6.1.x 系列): cross-version dis / load_module.
        # pyc_decompiler 用 xdis.load_module 拿 magic_int + version (Py2.x/Py3.x 路由).
        # 不装 → "xdis load_module failed: No module named 'xdis'" → decoder error.
        #
        # ⚠ 版本锁定原因: uncompyle6 3.9.3 要求 xdis<6.2.0, decompyle3 3.9.3 要求 xdis<6.3.
        #   PyPI latest xdis 6.3.0 跟 uncompyle6 3.9.3 冲突 (ResolutionImpossible).
        #   共同兼容范围是 xdis 6.1.x (6.1.1 ~ 6.1.7).
        #
        # ⚠ Python 3.13+ 兼容性: xdis 6.1.x 的 wheel 标注 Requires-Python<3.13,
        #   实际在 3.13.6 上能跑 (Owner 2026-07-01 实战验证),
        #   Stage 2 pypi 分支会自动加 --ignore-requires-python 跳过 wheel 元数据检查.
        notes = "v0.5-pyc-deps-install: pyc_decompiler decoder 依赖 (锁 6.1.7 兼容 uncompyle6<6.2.0)"
    },
    @{
        name = "uncompyle6"
        version = "3.9.3"
        install_method = "pypi"
        # uncompyle6 3.9.3 (2026-07 PyPI latest): Py2.x .pyc 反编译到源码.
        # 仅 Py2.x 路径走 (per core/decoders/pyc_decompiler.py:137-141)
        # 依赖 xdis<6.2.0 + spark-parser<1.9.2 — 跟 xdis 6.1.7 锁定兼容
        notes = "v0.5-pyc-deps-install: pyc_decompiler Py2.x 反编译 (uncompyle6)"
    },
    @{
        name = "decompyle3"
        version = "3.9.3"
        install_method = "pypi"
        # decompyle3 3.9.3 (2026-07 PyPI latest): Py3.x .pyc 反编译到源码.
        # 仅 Py3.x 路径走 (per core/decoders/pyc_decompiler.py:142-146)
        # 依赖 xdis<6.3 + spark-parser<1.9.2 — 跟 xdis 6.1.7 锁定兼容
        notes = "v0.5-pyc-deps-install: pyc_decompiler Py3.x 反编译 (decompyle3)"
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

# ---- Stage 0: Rust toolchain (optional, per v0.5-windows-evtx-dump) ----
# 装 rustup + rustc + cargo, profile=minimal 跳过 docs 省 ~200MB.
# 失败不阻塞后续 Stage (Rust 是 optional 加固, 不是 Stage 1/2 必需).
Write-Host "--- Stage 0: Rust toolchain (optional) ---" -ForegroundColor Cyan

$rust_installed = $false
try {
    $ver = & rustc --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[skip] rustc already installed: $ver" -ForegroundColor Gray
        $rust_installed = $true
    }
} catch {}

if (-not $rust_installed) {
    try {
        Write-Host "[download] rustup-init.exe ..." -NoNewline
        $rustup = Join-Path $StageDir "rustup-init.exe"
        Download-File -Url "https://win.rustup.rs/x86_64" -Out $rustup
        Write-Host " OK" -ForegroundColor Green

        Write-Host "[install] rustup-init -y --default-toolchain stable --profile minimal ..." -NoNewline
        # rustup-init 输出很长, Out-Null 抑制, 仅在 $LASTEXITCODE 检查
        & $rustup -y --default-toolchain stable --profile minimal | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "rustup-init exit $LASTEXITCODE" }
        Write-Host " OK" -ForegroundColor Green

        # Refresh PATH so cargo / rustc visible to subsequent Stages
        $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
        $cargo_bin = Join-Path $env:USERPROFILE ".cargo\bin"
        Write-Host "[rust] cargo bin: $cargo_bin (PATH refreshed)" -ForegroundColor Gray
    } catch {
        Write-Host " FAILED" -ForegroundColor Yellow
        Write-Host "         warning: $_" -ForegroundColor Yellow
        Write-Host "         Rust not installed; install.ps1 will continue." -ForegroundColor Yellow
    }
}

Write-Host ""

# ---- Stage 1: Download + extract binaries ----
Write-Host "--- Stage 1: Binaries (4 tools) ---" -ForegroundColor Cyan

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
            "sevenz_extract" {
                # 7-Zip 23.01 NSIS 安装器 (/S 静默 + /D=<abs path> 自定义目录).
                # per v0.5-7z-layout-migrate: 完整安装到 extend-tools/bin/win-x64/7-Zip/
                # NSIS 限制: /D= 必须是绝对路径 + 目标目录不存在
                $dest_dir = Join-Path $BinDir "7-Zip"
                Write-Host "[install] $($tool.name) NSIS /S /D=$dest_dir ..." -NoNewline
                # NSIS /D= 不能含尾部反斜杠
                $dest_dir_clean = $dest_dir.TrimEnd('\')
                $proc = Start-Process -FilePath $tmp -ArgumentList "/S", "/D=$dest_dir_clean" -Wait -PassThru -NoNewWindow
                if ($proc.ExitCode -ne 0) {
                    throw "7-Zip NSIS install exit code $($proc.ExitCode)"
                }
                $verify = Join-Path $dest_dir_clean "7z.exe"
                if (-not (Test-Path $verify)) {
                    throw "7-Zip installed but $verify not found (NSIS /D= 失败? 检查路径权限)"
                }
                Remove-Item $tmp -Force -ErrorAction SilentlyContinue
                Write-Host " OK" -ForegroundColor Green
            }
            "file_zip" {
                # nscaife/file-windows zip: file.exe + libgnurx-0.dll + libmagic-1.dll +
                # magic.mgc + COPYING.file + COPYING.libgnurx (all at zip root).
                # libmagic 依赖要求所有 dll + magic.mgc 必须跟 file.exe 在同目录,
                # 所以整体 unzip 到 bindir.
                Write-Host "[extract] $($tool.name) zip -> $BinDir ..." -NoNewline
                Add-Type -AssemblyName System.IO.Compression.FileSystem
                $extract_dir = Join-Path $StageDir "$($tool.name)_extract"
                if (Test-Path $extract_dir) { Remove-Item $extract_dir -Recurse -Force }
                [System.IO.Compression.ZipFile]::ExtractToDirectory($tmp, $extract_dir)
                # 全部复制到 bindir (libmagic 依赖)
                foreach ($f in @("file.exe", "libgnurx-0.dll", "libmagic-1.dll", "magic.mgc", "COPYING.file", "COPYING.libgnurx")) {
                    $src = Join-Path $extract_dir $f
                    if (Test-Path $src) {
                        $dst = Join-Path $BinDir $f
                        # 不强制 overwrite — existing sha256 已固定, idempotent
                        if ((Test-Path $dst) -and (-not $Force)) {
                            Write-Host "[skip] $($tool.name): $f already exists" -ForegroundColor Gray
                        } else {
                            Move-Item $src $dst -Force
                        }
                    } else {
                        Write-Host "[warn] $($tool.name): $f missing in zip (libmagic 依赖可能损坏)" -ForegroundColor Yellow
                    }
                }
                Remove-Item $extract_dir -Recurse -Force
                Remove-Item $tmp -Force -ErrorAction SilentlyContinue
                Write-Host " OK" -ForegroundColor Green
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

# ---- Stage 2: pip install (binwalk source + patch / pyzbar PyPI) ----
Write-Host ""
Write-Host "--- Stage 2: Python packages ($($pip_packages.Count) tool) ---" -ForegroundColor Cyan

foreach ($pkg in $pip_packages) {
    # Quick check: already installed at correct version?
    $installed_ok = $false
    try {
        $ver = & python -c "import $($pkg.name); print($($pkg.name).__version__)" 2>$null
        if ($ver -eq $pkg.version) {
            $installed_ok = $true
            Write-Host "[skip] $($pkg.name): v$($pkg.version) already installed" -ForegroundColor Gray
            $results += [PSCustomObject]@{name=$pkg.name; status="skipped"; path="python -m $($pkg.name) v$($pkg.version)"}
        }
    } catch {}

    if ($installed_ok) { continue }

    try {
        if ($pkg.install_method -eq "source") {
            # binwalk: download source zip + patch + pip install from extracted dir
            Write-Host "[download] $($pkg.name) v$($pkg.version) source ..." -NoNewline
            $src_zip = Join-Path $StageDir "$($pkg.name)-v$($pkg.version).zip"
            Download-File -Url $pkg.url -Out $src_zip | Out-Null

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

        } elseif ($pkg.install_method -eq "pypi") {
            # pyzbar (and future PyPI-only packages): just pip install
            # v0.5-pyc-deps-install: Python 3.13+ 检测 — xdis 6.1.x wheel 标 Requires-Python<3.13,
            # 但 3.13.6 实测能跑 (Owner 2026-07-01 验证). Py 3.13+ 加 --ignore-requires-python.
            $py_ver = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            $ignore_py_arg = ""
            if ($py_ver -and ([version]$py_ver).Major -ge 3 -and ([version]$py_ver).Minor -ge 13) {
                $ignore_py_arg = "--ignore-requires-python"
                Write-Host "[py3.13+] $($pkg.name) v$($pkg.version) (with --ignore-requires-python) ..." -NoNewline
            } else {
                Write-Host "[pip install] $($pkg.name) v$($pkg.version) ..." -NoNewline
            }
            & python -m pip install --proxy $ProxyUrl --quiet $ignore_py_arg "$($pkg.name)==$($pkg.version)"
            if ($LASTEXITCODE -ne 0) {
                throw "pip install failed with exit $LASTEXITCODE"
            }
            Write-Host " OK" -ForegroundColor Green

            $results += [PSCustomObject]@{name=$pkg.name; status="ok"; path="python -m $($pkg.name) v$($pkg.version)"}
        } else {
            throw "unknown install_method: $($pkg.install_method)"
        }

    } catch {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "         error: $_" -ForegroundColor Red
        $results += [PSCustomObject]@{name=$pkg.name; status="failed"; error="$_"}
    }
}

# ---- Stage 3: deploy msvcr120.dll to pyzbar site-packages (per v0.5-zbar-windows-install) ----
# 背景: libzbar-64.dll (pyzbar 自带) 是 VS 2013 编译, 链 MSVCR120.dll.
#       Win ship 默认没装 VS 2013 redist, pyzbar 加载报 "Could not find module 'libiconv.dll' (or one of its dependencies)".
#       解决: 把 extend-tools/bin/win-x64/msvcr120.dll 复制到 pyzbar site-packages.
#       跟 libzbar-64.dll 同目录, LoadLibrary 即可找到.
Write-Host ""
Write-Host "--- Stage 3: deploy msvcr120.dll to pyzbar site-packages ---" -ForegroundColor Cyan

$msvcr_src = Join-Path $BinDir "msvcr120.dll"
if (Test-Path $msvcr_src) {
    try {
        # 找 pyzbar site-packages 路径
        $pyzbar_dir = & python -c "import pyzbar, os; print(os.path.dirname(pyzbar.__file__))" 2>$null
        if ($pyzbar_dir -and (Test-Path $pyzbar_dir)) {
            $msvcr_dst = Join-Path $pyzbar_dir "msvcr120.dll"
            if ((Test-Path $msvcr_dst) -and (-not $Force)) {
                Write-Host "[skip] msvcr120.dll: already at $msvcr_dst" -ForegroundColor Gray
                $results += [PSCustomObject]@{name="msvcr120"; status="skipped"; path=$msvcr_dst}
            } else {
                Write-Host "[deploy] msvcr120.dll -> $msvcr_dst ..." -NoNewline
                Copy-Item $msvcr_src $msvcr_dst -Force
                Write-Host " OK" -ForegroundColor Green
                $results += [PSCustomObject]@{name="msvcr120"; status="ok"; path=$msvcr_dst}
            }
        } else {
            Write-Host "[warn] pyzbar not importable, skip msvcr120.dll deploy (re-run after `pip install pyzbar`)" -ForegroundColor Yellow
        }
    } catch {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "         error: $_" -ForegroundColor Red
        $results += [PSCustomObject]@{name="msvcr120"; status="failed"; error="$_"}
    }
} else {
    Write-Host "[skip] msvcr120.dll: not in $BinDir (Stage 1 download failed? or 手动部署)"
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
Write-Host "Verify: python -m automisc tools list  (should show binwalk / exiftool / 7zr / foremost / pyzbar via msvcr120.dll deploy)"