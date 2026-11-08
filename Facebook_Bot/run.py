#!/usr/bin/env python3
"""تشغيل واجهة فيسبوك: python3 run.py ثم افتح http://127.0.0.1:8081"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import json
import uvicorn
from core import db

db.init_db()
s = json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))["system"]
print(f"📘 فيسبوك: http://{s['web_host']}:{s['web_port']}")
uvicorn.run("web.app:app", host=s["web_host"], port=int(s["web_port"]), log_level="warning")
