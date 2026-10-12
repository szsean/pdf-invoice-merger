@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+ 并勾选 "Add to PATH"。
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo 首次运行，正在创建虚拟环境...
    python -m venv .venv
)

".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt pyinstaller

".venv\Scripts\python.exe" -m PyInstaller -F -w --noconfirm --name "发票PDF合并工具" pdf_merger.py --collect-all tkinterdnd2 --collect-all pymupdf

echo.
echo 打包完成：%~dp0dist\发票PDF合并工具.exe
pause
