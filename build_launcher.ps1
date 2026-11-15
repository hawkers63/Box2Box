# Copyright (c) 2026 onwards Mark Hawksworth (hawkers63). All rights reserved.
# Not to be copied or altered without express permission. See LICENSE.
#
# Builds Box2Box.exe, a small launcher that carries the Box2Box icon, from launcher\Box2Box.cs with
# the C# compiler that comes with Windows (.NET Framework 4.8), then puts a shortcut to it on the
# desktop. Run it from PowerShell in the Box2Box folder:
#
#     .\build_launcher.ps1                # build, and add the desktop shortcut
#     .\build_launcher.ps1 -NoShortcut    # build only
param([switch]$NoShortcut)
$ErrorActionPreference = 'Stop'

$folder = $PSScriptRoot
$compiler = @('Framework64', 'Framework') |
    ForEach-Object { Join-Path $env:WINDIR "Microsoft.NET\$_\v4.0.30319\csc.exe" } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
if (-not $compiler) {
    throw 'The C# compiler that comes with Windows (.NET Framework 4.8) was not found.'
}

$icon = Join-Path $folder 'icon\football-64-sky-blue.ico'
$source = Join-Path $folder 'launcher\Box2Box.cs'
$exe = Join-Path $folder 'Box2Box.exe'
& $compiler /nologo /target:winexe /optimize+ "/win32icon:$icon" /reference:System.Windows.Forms.dll "/out:$exe" $source
if ($LASTEXITCODE -ne 0) {
    throw "The compiler stopped with exit code $LASTEXITCODE."
}
Write-Host "Built $exe"

if (-not $NoShortcut) {
    $link = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Box2Box.lnk'
    $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
    $shortcut.TargetPath = $exe
    $shortcut.WorkingDirectory = $folder
    $shortcut.IconLocation = "$exe,0"
    $shortcut.Description = 'Box2Box: fixtures, results and tables from a Football Manager save'
    $shortcut.Save()
    Write-Host "Added the shortcut $link"
}
