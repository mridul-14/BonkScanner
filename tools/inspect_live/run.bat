@echo off
setlocal
cd /d "%~dp0"
if exist "..\..\.venv\Scripts\python.exe" (
    "..\..\.venv\Scripts\python.exe" inspect_live.py %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" inspect_live.py %*
) else (
    python inspect_live.py %*
)
pause
