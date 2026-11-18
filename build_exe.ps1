# Build the standalone Box2Box.exe folder with PyInstaller.
#
# Usage:
#   .\build_exe.ps1              # clean previous build output, then build
#   .\build_exe.ps1 -Clean       # also wipe PyInstaller's own caches first
#   .\build_exe.ps1 -OneFile     # build the single-file dist\Box2Box.exe instead; the one-folder build is left alone
#
# The output folder dist\Box2Box\ holds Box2Box.exe, every bundled library and
# the app icon. Settings and the error log are written next to Box2Box.exe at
# first launch, as the roadmap asks. See notes/plan_standalone_exe.md.

param(
    [switch]$Clean,
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Definition
$python = Join-Path $here ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Project virtual environment not found at $python. Create it with 'py -3.14 -m venv .venv' first, then 'pip install -r requirements.txt -r requirements-build.txt'."
}

$build = Join-Path $here "build"
$dist = Join-Path $here "dist"
if ($OneFile) {
    # Only the one-file output is replaced; dist\Box2Box\ (the one-folder build) stays as it is.
    foreach ($item in @((Join-Path $build "onefile"), (Join-Path $dist "Box2Box.exe"))) {
        if (Test-Path $item) {
            Write-Host "Removing $item"
            Remove-Item -LiteralPath $item -Recurse -Force
        }
    }
} else {
    foreach ($folder in @($build, $dist)) {
        if (Test-Path $folder) {
            Write-Host "Removing $folder"
            Remove-Item -LiteralPath $folder -Recurse -Force
        }
    }
}

if ($Clean) {
    $cache = Join-Path $env:LOCALAPPDATA "pyinstaller"
    if (Test-Path $cache) {
        Write-Host "Wiping PyInstaller cache at $cache"
        Remove-Item -LiteralPath $cache -Recurse -Force
    }
}

Write-Host "Building with PyInstaller..."
if ($OneFile) {
    & $python -m PyInstaller Box2Box-onefile.spec --noconfirm --log-level WARN --workpath (Join-Path $build "onefile")
} else {
    & $python -m PyInstaller Box2Box.spec --noconfirm --log-level WARN
}
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed (exit code $LASTEXITCODE)"
}

if ($OneFile) {
    $single = Join-Path $dist "Box2Box.exe"
    if (-not (Test-Path $single)) {
        throw "Build finished but Box2Box.exe is missing at $single"
    }
    Write-Host ""
    Write-Host "Built the single file at $single"
    Write-Host ("  size: {0:N1} MB" -f ((Get-Item -LiteralPath $single).Length / 1MB))
    return
}

$out = Join-Path $dist "Box2Box"
$exe = Join-Path $out "Box2Box.exe"
if (-not (Test-Path $exe)) {
    throw "Build finished but Box2Box.exe is missing at $exe"
}

$sizeMB = (Get-ChildItem -LiteralPath $out -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB
$files = (Get-ChildItem -LiteralPath $out -Recurse -File | Measure-Object).Count
Write-Host ""
Write-Host "Built Box2Box at $exe"
Write-Host ("  folder size: {0:N1} MB" -f $sizeMB)
Write-Host ("  file count:  {0}" -f $files)
