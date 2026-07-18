#!/bin/sh
echo smush runner
if ! command -v pyenv >/dev/null 2>&1
then
    echo "pyenv is required to run this command, please install it by document. (https://github.com/pyenv/pyenv)"
    exit 1
fi
if pyenv versions | grep -q "3.11.15"; then
    export PYENV_ROOT="$HOME/.pyenv"
    [[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init - zsh)"
    pyenv shell 3.11.15
    pip install -r requirements.txt
    python main.py
else
    echo "Python 3.11.15 is not installed, please install by running: pyenv install 3.11.15"
    exit 1
fi