#!/bin/zsh
set -eu
cd -- "${0:A:h}"
"${PYTHON:-python3}" -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10 이상을 설치하세요."'
"${PYTHON:-python3}" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
printf '\nZotero → 도구 → PDF Common Crop: Python 설정에 다음 경로를 입력하세요:\n%s/.venv/bin/python\n' "$PWD"
