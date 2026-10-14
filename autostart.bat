@echo off
setlocal
title smush launcher

pushd "%~dp0"
if errorlevel 1 exit /b 1
nvidia-smi
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
set "smushExitCode=%ERRORLEVEL%"

popd
exit /b %smushExitCode%
