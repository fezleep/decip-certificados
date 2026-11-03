@echo off
setlocal
cd /d "%~dp0"

echo [DECIP] Verificando o ambiente...
if not exist ".venv\Scripts\python.exe" (
  echo [ERRO] Ambiente virtual nao encontrado.
  echo Execute instalar.bat e tente novamente.
  echo.
  echo Pressione uma tecla para continuar...
  pause >nul
  exit /b 1
)

".venv\Scripts\python.exe" -m app.launcher --host 127.0.0.1 --port 8766
set "DECIP_PROBE_CODE=%ERRORLEVEL%"

if "%DECIP_PROBE_CODE%"=="10" (
  echo [DECIP] Abrindo a instancia existente no navegador...
  start "DECIP Certificados" http://127.0.0.1:8766
  exit /b 0
)

if "%DECIP_PROBE_CODE%"=="20" (
  echo [ERRO] O DECIP nao foi iniciado porque a porta pertence a outro programa.
  echo Feche o programa somente se voce o reconhecer e tente novamente.
  echo.
  echo Pressione uma tecla para continuar...
  pause >nul
  exit /b 1
)

if not "%DECIP_PROBE_CODE%"=="0" (
  echo [ERRO] Nao foi possivel verificar a porta 8766 ^(codigo %DECIP_PROBE_CODE%^).
  echo Nenhum processo foi encerrado. Verifique as mensagens exibidas acima.
  echo.
  echo Pressione uma tecla para continuar...
  pause >nul
  exit /b %DECIP_PROBE_CODE%
)

echo [DECIP] Iniciando em http://127.0.0.1:8766 ...
".venv\Scripts\python.exe" run.py
set "DECIP_EXIT_CODE=%ERRORLEVEL%"

if not "%DECIP_EXIT_CODE%"=="0" (
  echo.
  echo [ERRO] O aplicativo foi encerrado com o codigo %DECIP_EXIT_CODE%.
  echo Verifique a mensagem de erro exibida acima.
  echo.
  echo Pressione uma tecla para continuar...
  pause >nul
)

exit /b %DECIP_EXIT_CODE%

