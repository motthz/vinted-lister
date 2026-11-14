@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto errore
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto errore
".venv\Scripts\python.exe" app.py
pause
exit /b
:errore
echo Installazione dipendenze fallita.
pause
exit /b 1
