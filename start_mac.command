#!/bin/bash
# Double-click this file to open Human Typer on a Mac.
cd "$(dirname "$0")"

# Prefer the Python from python.org: Apple's built-in one has an old window
# library that can show a blank window.
PY=""
for p in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c "import tkinter" >/dev/null 2>&1; then
        PY="$p"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "Python isn't installed yet (or it's missing its window part)."
    echo "Install it free from https://www.python.org/downloads/ and then double-click this file again."
    open "https://www.python.org/downloads/"
    read -n 1 -s -r -p "Press any key to close."
    exit 1
fi

echo "Getting things ready (only slow the first time)..."
"$PY" -m pip install --quiet --user --disable-pip-version-check -r requirements.txt 2>/dev/null \
    || "$PY" -m pip install --quiet --user --break-system-packages --disable-pip-version-check -r requirements.txt

"$PY" human_typer.py
