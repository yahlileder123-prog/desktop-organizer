@echo off
cd /d "%~dp0"
where pythonw >nul 2>&1
if errorlevel 1 (
  start "" python "%~dp0main.py"
) else (
  start "" pythonw "%~dp0main.py"
)
