@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+ 并勾选 "Add to PATH"。
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo 首次运行，正在创建虚拟环境...
    python -m venv .venv
)

".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt

".venv\Scripts\python.exe" pdf_merger.py
if errorlevel 1 pause
