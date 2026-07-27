$ErrorActionPreference = "Stop"

$desktopRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$bootstrap = Join-Path $desktopRoot "bootstrap"
$binaryDirectory = Join-Path $desktopRoot "src-tauri\binaries"
$distDirectory = Join-Path $desktopRoot "dist"
$pyInstallerWorkDirectory = Join-Path $desktopRoot ".build\pyinstaller"
$pyInstallerSpecDirectory = Join-Path $desktopRoot ".build"
$toolsDirectory = Join-Path $desktopRoot ".build\tools"
$sevenZipExecutable = Join-Path $toolsDirectory "7zr.exe"

$python = $env:VOCAVID_BUILD_PYTHON
if (-not $python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $python = $pythonCommand.Source
    }
}
if (-not $python -or -not (Test-Path -LiteralPath $python)) {
    throw "Python wurde nicht gefunden. Setze VOCAVID_BUILD_PYTHON auf eine Python-3.11+-EXE."
}
$pythonLibraryBin = Join-Path (Split-Path -Parent $python) "Library\bin"
if (Test-Path -LiteralPath $pythonLibraryBin) {
    $env:Path = "$pythonLibraryBin;$env:Path"
}

$packageManager = Get-Command npm -ErrorAction SilentlyContinue
if (-not $packageManager) {
    $packageManager = Get-Command pnpm -ErrorAction SilentlyContinue
}
if (-not $packageManager) {
    throw "npm oder pnpm wurde nicht gefunden."
}

$env:CARGO_BUILD_JOBS = if ($env:CARGO_BUILD_JOBS) { $env:CARGO_BUILD_JOBS } else { "1" }
$env:CARGO_PROFILE_RELEASE_DEBUG = "0"
$env:CARGO_PROFILE_DEV_DEBUG = "0"

& (Join-Path $PSScriptRoot "prepare-payload.ps1")

& $python -m pip install --disable-pip-version-check -r (Join-Path $bootstrap "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Python dependency installation failed"
}
& $python (Join-Path $PSScriptRoot "prepare_sevenzip.py") $sevenZipExecutable
if ($LASTEXITCODE -ne 0) {
    throw "7-Zip preparation failed"
}
& $python -m PyInstaller --noconfirm --clean --onefile --name vocavid-bootstrap --distpath $distDirectory --workpath $pyInstallerWorkDirectory --specpath $pyInstallerSpecDirectory --add-binary "$sevenZipExecutable;." (Join-Path $bootstrap "vocavid_bootstrap.py")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed"
}
& (Join-Path $distDirectory "vocavid-bootstrap.exe") --help | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Built bootstrap executable failed its smoke test"
}

New-Item -ItemType Directory -Path $binaryDirectory -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $distDirectory "vocavid-bootstrap.exe") -Destination (Join-Path $binaryDirectory "vocavid-bootstrap-x86_64-pc-windows-msvc.exe") -Force

Push-Location $desktopRoot
try {
    & $packageManager.Source run build
    if ($LASTEXITCODE -ne 0) {
        throw "Tauri build failed"
    }
}
finally {
    Pop-Location
}
