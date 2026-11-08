@echo off
powershell.exe -NoProfile -File "%~dp0Restaurar-Wanbo.ps1" -Apply -Pause
exit /b %errorlevel%
