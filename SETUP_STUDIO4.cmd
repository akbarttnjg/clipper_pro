@echo off
setlocal
cd /d "%~dp0."
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher tidak ditemukan. Pasang Python 3.10+ dahulu.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 goto gagal
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto gagal
".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-pro.txt
if errorlevel 1 goto gagal
echo Selesai. Siapkan FFmpeg dan Ollama, lalu jalankan CEK_PRO.cmd.
echo Setelah pemeriksaan, jalankan JALANKAN_PRO.cmd.
pause
exit /b 0
:gagal
echo Setup belum selesai. Periksa pesan kesalahan di atas.
pause
exit /b 1
