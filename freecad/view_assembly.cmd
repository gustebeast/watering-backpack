@echo off
REM Shared FreeCAD viewer launcher, reused by every project's one-line
REM "View Assembly.cmd" forwarder. Opens a project's assembly.step in the shared
REM FreeCAD hub -- no rebuild, no build-counter bump, just what's on disk.
REM
REM   %1     = the calling project's folder (with trailing backslash). The
REM            forwarder passes its own %~dp0; if run directly, defaults to cwd.
REM   %~dp0  = THIS file's folder (3D/freecad), so freecad_view.py sits beside it.
setlocal
set "PROJ=%~1"
if "%PROJ%"=="" set "PROJ=%CD%\"
py -3.12 "%~dp0freecad_view.py" --step "%PROJ%assembly.step"
if errorlevel 1 (
  echo.
  echo Could not open the viewer -- see the message above.
  pause
)
