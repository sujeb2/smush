#!/bin/sh
echo smush runner
pip install -r requirements.txt
sudo sh ./venv312/bin/activate
./venv312/bin/python main.py