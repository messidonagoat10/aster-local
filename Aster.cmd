@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-aster.ps1"
if errorlevel 1 (
  echo.
  echo Aster could not start. Review the message above and the QUICKSTART.md troubleshooting section.
  pause
)
