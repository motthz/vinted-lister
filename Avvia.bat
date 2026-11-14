@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto errore
fc /b requirements.txt ".venv\requirements.installed" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto errore
  copy /y requirements.txt ".venv\requirements.installed" >nul
)
".venv\Scripts\python.exe" app.py
pause
exit /b
:errore
echo Installazione dipendenze fallita.
pause
exit /b 1
