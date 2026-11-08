#!/bin/bash
set -e
pkg update -y && pkg upgrade -y
pkg install -y python git
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
echo "تم! شغّل: python3 run.py"
