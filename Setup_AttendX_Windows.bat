@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup_AttendX_Windows.ps1"
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" (
  echo Setup did not finish. Read the error above and START_HERE.md.
) else (
  echo Setup finished. You can now run Run_AttendX.bat.
)
pause
exit /b %RC%
