@echo off
setlocal
title smush cx_Freeze builder
cd /d "%~dp0"

python -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)"
if errorlevel 1 (
    echo Python 3.11 is required to build smush.
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

python setup.py build_exe --build-exe dist\smush %*
if errorlevel 1 exit /b 1

echo Build complete: dist\smush
endlocal
