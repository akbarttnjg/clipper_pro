@echo off
setlocal
cd /d "%~dp0."
".venv\Scripts\python.exe" doctor_pro.py
pause
