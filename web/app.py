"""
واجهة فيسبوك - إدارة الحسابات والمجموعات ومكتبة المنشورات والحملات.
"""
import json
import secrets
import time
import uuid
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, UploadFile, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from core import db
from platforms.facebook import groups_discovery, publisher
from platforms.facebook.session import import_cookies
from core.ai import rewrite_for_group

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="AdMan Facebook", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "web" / "static"), name="static")
_sessions = set()


def _auth(request: Request):
    token = request.headers.get("X-Auth-Token") or request.query_params.get("token")
    if token not in _sessions:
        raise HTTPException(401)


@app.post("/api/login")
async def login(payload: dict):
    import json as _j
    pw = _j.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))["system"]["web_password"]
    if payload.get("password") == pw:
        t = secrets.token_hex(16)
        _sessions.add(t)
        return {"ok": True, "token": t}
    raise HTTPException(401)


@app.get("/", response_class=HTMLResponse)
async def index():
    return (ROOT / "web" / "static" / "index.html").read_text(encoding="utf-8")


def _settings():
    return json.loads((ROOT / "config" / "settings.json").read_text(encoding="utf-8"))


@app.get("/api/accounts")
async def get_accounts(request: Request):
    _auth(request)
    return db.get_accounts()


@app.post("/api/accounts")
async def save_account(acc: dict, request: Request):
    _auth(request)
    if not acc.get("id"):
        acc["id"] = "fb_" + uuid.uuid4().hex[:8]
    db.save_account(acc)
    return {"ok": True, "id": acc["id"]}


@app.delete("/api/accounts/{acc_id}")
async def del_account(acc_id: str, request: Request):
    _auth(request)
    db.q("DELETE FROM accounts WHERE id=?", (acc_id,))
    return {"ok": True}


@app.post("/api/accounts/{acc_id}/cookies")
async def upload_cookies(acc_id: str, request: Request, file: UploadFile):
    """رفع كوكيز فيسبوك (ملف JSON مستخرج من المتصفح)."""
    _auth(request)
    import_cookies(acc_id, (await file.read()).decode("utf-8", "ignore"))
    return {"ok": True}


@app.post("/api/accounts/{acc_id}/discover")
async def discover(acc_id: str, request: Request, keywords: dict = None):
    """اكتشاف مجموعات جديدة - تُحفظ في الذاكرة ولا تتكرر."""
    _auth(request)
    acc = next((a for a in db.get_accounts() if a["id"] == acc_id), None)
    if not acc:
        raise HTTPException(404)
    kw = (keywords or {}).get("keywords") or None
    n = await groups_discovery.discover(acc, kw)
    return {"ok": True, "new_groups": n}


@app.get("/api/groups")
async def get_groups(request: Request, niche: str = "", status: str = ""):
    _auth(request)
    sql, params = "SELECT * FROM groups", []
    conds = []
    if niche:
        conds.append("niche=?"); params.append(niche)
    if status:
        conds.append("status=?"); params.append(status)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY members DESC LIMIT 500"
    return [dict(r) for r in db.q(sql, tuple(params))]


@app.post("/api/groups/{gid}/{action}")
async def group_action(gid: int, action: str, request: Request, payload: dict = None):
    """approve | exclude | set_niche"""
    _auth(request)
    if action == "approve":
        db.q("UPDATE groups SET status='approved' WHERE id=?", (gid,))
    elif action == "exclude":
        db.q("UPDATE groups SET status='excluded' WHERE id=?", (gid,))
    elif action == "set_niche" and payload:
        db.q("UPDATE groups SET niche=? WHERE id=?", (payload.get("niche", "general"), gid))
    return {"ok": True}


@app.get("/api/posts")
async def get_posts(request: Request, niche: str = ""):
    _auth(request)
    rows = db.q("SELECT * FROM posts WHERE niche=? ORDER BY id DESC", (niche,)) if niche \
        else db.q("SELECT * FROM posts ORDER BY id DESC LIMIT 200")
    out = []
    for r in rows:
        d = dict(r)
        d["media_paths"] = json.loads(d.get("media_paths") or "[]")
        out.append(d)
    return out


@app.post("/api/posts")
async def save_post(post: dict, request: Request):
    """إضافة/تعديل منشور في المكتبة - مصنف حسب الفئة (ماجستير...)."""
    _auth(request)
    key = post.get("key") or f"{post.get('niche','general')}_{uuid.uuid4().hex[:8]}"
    db.add_post(key, post.get("niche", "general"), post.get("title", ""), post.get("text", ""),
                post.get("media_paths"))
    return {"ok": True, "key": key}


@app.delete("/api/posts/{pid}")
async def del_post(pid: int, request: Request):
    _auth(request)
    db.q("DELETE FROM posts WHERE id=?", (pid,))
    return {"ok": True}


@app.post("/api/campaign/run")
async def run_campaign(payload: dict, request: Request):
    """
    تشغيل حملة: ينشر منشورات فئة معينة (مثلاً ماجستير) على كل مجموعاتها المعتمدة،
    بكل الحسابات المفعّلة، مع إعادة صياغة ذكية لكل مجموعة.
    """
    _auth(request)
    niche = payload.get("niche", "general")
    import asyncio
    posts = db.q("SELECT * FROM posts WHERE niche=? AND enabled=1", (niche,))
    groups = [dict(r) for r in db.q("SELECT * FROM groups WHERE niche=? AND status='approved'", (niche,))]
    accounts = db.get_accounts()
    if not posts or not groups or not accounts:
        return {"ok": False, "error": "تحتاج منشورًا معتمدًا + مجموعات معتمدة + حسابًا مفعّلاً بهذه الفئة"}
    s = _settings()["system"]

    async def _go():
        results = []
        for post in posts[:5]:
            for g in groups[:30]:
                for acc in accounts:
                    if not acc.get("enabled"):
                        continue
                    # إعادة صياغة النص لكل مجموعة لتجنب فلتر السبام
                    text = await asyncio.to_thread(rewrite_for_group, post["text"], g.get("name") or "", niche)
                    ok, err = await publisher.publish_to_group(acc, g["url"], text)
                    db.log_publish(acc["id"], g["url"], post["id"], ok, err)
                    results.append({"group": g.get("name"), "account": acc["label"], "ok": ok})
                    await asyncio.sleep(s.get("delay_between_groups_sec", 90))
        return results

    task = asyncio.create_task(_go())
    return {"ok": True, "message": "الحملة تعمل في الخلفية - راقب سجل النشر"}


@app.get("/api/logs")
async def get_logs(request: Request, limit: int = 100):
    _auth(request)
    return [dict(r) for r in db.q("SELECT * FROM publish_log ORDER BY id DESC LIMIT ?", (limit,))]
