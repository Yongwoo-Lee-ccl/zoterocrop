#!/bin/zsh
set -eu
cd -- "${0:A:h}"
"${PYTHON:-python3}" -c 'import sys; assert sys.version_info >= (3,10), "Please install Python 3.10 or later."'
"${PYTHON:-python3}" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
printf '\nEnter the following path in Zotero → Tools → Crop Margins: Settings → Configure and verify Python:\n%s/.venv/bin/python\n' "$PWD"
