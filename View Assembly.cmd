@echo off
REM Double-click to open this project's last-built model in the web viewer.
cd /d "%~dp0"
py -3.12 -m cadkit.web.view
