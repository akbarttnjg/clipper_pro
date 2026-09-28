@echo off
setlocal
cd /d "%~dp0."
echo Tutup Steezy sebelum memulihkan file lama.
".venv\Scripts\python.exe" steezy_pro_installer.py --target "%~dp0." --rollback
pause
