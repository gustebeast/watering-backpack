@echo off
REM Double-click to open this project's assembly.step in the FreeCAD viewer hub.
REM All logic lives in the shared launcher; this just forwards our own folder.
call "%~dp0cadkit\freecad\view_assembly.cmd" "%~dp0"
