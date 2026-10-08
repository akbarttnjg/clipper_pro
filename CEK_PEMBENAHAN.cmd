@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
 echo Python aplikasi tidak ditemukan. Jalankan dari folder mesin Clipper.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" tools\verify_complete.py %*
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
