"""
جلسات فيسبوك: متصفح معزول لكل حساب (Playwright + كوكيز + بروكسي خاص).
بدون Graph API - نشر حقيقي عبر الواجهة كما يفعل المستخدم.
"""
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
SESSIONS = ROOT / "data" / "sessions"

_pw = None
_contexts = {}


async def get_playwright():
    global _pw
    if _pw is None:
        _pw = await async_playwright().start()
    return _pw


def import_cookies(account_id: str, cookies_json: str):
    data = json.loads(cookies_json)
    if isinstance(data, dict) and "cookies" in data:
        data = data["cookies"]
    d = SESSIONS / account_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "cookies.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cookies(account_id: str):
    f = SESSIONS / account_id / "cookies.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


async def get_context(account: dict):
    acc_id = account["id"]
    if acc_id in _contexts:
        return _contexts[acc_id]
    pw = await get_playwright()
    proxy = None
    if account.get("proxy"):
        p = account["proxy"]
        scheme, rest = p.split("://", 1)
        proxy = {"server": f"{scheme}://{rest.split('@')[-1]}"}
        if "@" in rest:
            creds = rest.split("@")[0]
            if ":" in creds:
                proxy["username"], proxy["password"] = creds.split(":", 1)
    ctx = await pw.chromium.launch_persistent_context(
        str(SESSIONS / acc_id / "browser_profile"), headless=True, proxy=proxy,
        viewport={"width": 1280, "height": 800},
        user_agent="Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        locale="ar")
    cookies = load_cookies(acc_id)
    if cookies:
        await ctx.add_cookies(cookies)
    _contexts[acc_id] = ctx
    return ctx


async def check_login(account: dict) -> bool:
    ctx = await get_context(account)
    page = await ctx.new_page()
    try:
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(4000)
        # إذا طُلب تسجيل الدخول فالجلسة منتهية
        return await page.query_selector("input[name='email']") is None
    finally:
        await page.close()
