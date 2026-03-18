param(
    [string]$Python = "python",
    [string]$SpecPath = "packaging/pyinstaller.spec"
)

$ErrorActionPreference = "Stop"

Write-Host "Building Lake Lot Manager Windows executable..."
& $Python -m PyInstaller --noconfirm --clean $SpecPath

Write-Host "Build complete. Output should be under dist/LakeLotManager/"
