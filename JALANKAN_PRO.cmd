@echo off
setlocal
cd /d "%~dp0."
if not exist ".venv\Scripts\python.exe" (
  echo Python .venv tidak ditemukan. Jalankan setup Steezy dahulu.
  pause
  exit /b 1
)
echo Buka http://localhost:8765 setelah server siap. Tutup dengan Ctrl+C.
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
