@echo off
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python nao foi encontrado. Instale o Python e tente novamente.
  pause
  exit /b 1
)

curl.exe -fsS "http://127.0.0.1:8000/" >nul 2>nul
if errorlevel 1 (
  start "Vela - servidor" cmd /k "cd /d ""%~dp0"" && python server.py"
  timeout /t 2 /nobreak >nul
)
start "" "http://127.0.0.1:8000"
