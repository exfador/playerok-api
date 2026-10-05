@echo off
title CXH_Playerok
cd /d "%~dp0"
set CXH_LAUNCHER=bat
set PYTHON_EXE=python
if exist ".venv\Scripts\python.exe" set PYTHON_EXE=.venv\Scripts\python.exe
:run
"%PYTHON_EXE%" main.py
if %errorlevel%==75 goto run
pause
