@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo AttendX has not been set up yet.
  echo Double-click Setup_AttendX_Windows.bat first.
  pause
  exit /b 2
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
  echo.
  echo AttendX closed with an error. Check the terminal message and docs\TEST_RESULTS.md.
  pause
)
