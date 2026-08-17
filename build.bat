@echo off
title smush builder
pyenv shell 3.11.9
python -m pip install -r requirements.txt
pyinstaller --clean --noconfirm build.spec
pause
exit