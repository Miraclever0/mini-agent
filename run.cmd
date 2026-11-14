@echo off
rem Launcher for mini-agent. Bypasses PowerShell execution policy for this process only.
rem Usage:  run.cmd --mock      run.cmd      run.cmd "your task here"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
exit /b %ERRORLEVEL%
