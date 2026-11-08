@echo off
powershell.exe -NoProfile -File "%~dp0Restaurar-Wanbo.ps1" -Pause
exit /b %errorlevel%
