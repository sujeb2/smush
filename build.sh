#!/bin/sh
echo "smush builder"

if ! command -v pyenv >/dev/null 2>&1; then
    echo "pyenv is required to run this command."
    exit 1
fi

if pyenv versions | grep -q "3.11.15"; then
    export PYENV_ROOT="$HOME/.pyenv"
    [[ -d $PYENV_ROOT/bin ]] && export PATH="$PYENV_ROOT/bin:$PATH"
    eval "$(pyenv init - bash)"
    export PYENV_VERSION="3.11.15"
    python -m pip install -r requirements.txt
    python -m nuitka --standalone --include-data-dir=files=files --include-data-dir=game=game --include-data-files=requirements.txt=requirements.txt --static-libpython=no main.py
	echo "build done."
else
    echo "Python 3.11.15 is required to run this program, please install by running: pyenv install 3.11.15"
    exit 1
fi
