@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente nao encontrado. Execute instalar.bat primeiro.
  pause
  exit /b 1
)
start "DECIP Certificados" http://127.0.0.1:8765
".venv\Scripts\python.exe" run.py

