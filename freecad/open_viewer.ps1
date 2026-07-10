<#
  Thin convenience shim for humans — the real logic lives in freecad_view.py
  (so builds and people share one implementation). Opens a project in the shared
  FreeCAD hub window as a tab; starts the hub if it isn't running.

  Usage:
    & "<this>\open_viewer.ps1"                                  # current folder
    & "<this>\open_viewer.ps1" -Project "C:\...\3D\servo-steel"
    & "<this>\open_viewer.ps1" -Step    "C:\...\servo-steel\assembly.step"
    & "<this>\open_viewer.ps1" -FreeCAD "D:\FreeCAD\bin\freecad.exe"

  STEP auto-detection (no -Step): prefers assembly.step, else the single
  top-level *.step in the project.
#>
param(
    [string]$Project = (Get-Location).Path,
    [string]$Step,
    [string]$FreeCAD
)
$ErrorActionPreference = "Stop"

$helper = Join-Path $PSScriptRoot "freecad_view.py"
if (-not (Test-Path $helper)) { throw "freecad_view.py not found at $helper" }

$cliArgs = @("-3.12", $helper)
if ($Step)    { $cliArgs += @("--step", $Step) } else { $cliArgs += @("--project", $Project) }
if ($FreeCAD) { $cliArgs += @("--freecad", $FreeCAD) }

& py @cliArgs
exit $LASTEXITCODE
