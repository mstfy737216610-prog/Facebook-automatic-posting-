"""
اكتشاف مجموعات فيسبوك: بحث بالكلمات المفتاحية (ماجستير، خدمات طلابية...)
وجمع روابط المجموعات مع عدد الأعضاء، ثم تصنيفها حسب الفئة المستهدفة.
النتيجة تُحفظ في قاعدة البيانات ولا تُعاد إعادة البحث عنها (ذاكرة).
"""
from core import db
from platforms.facebook import session as fb_session

DEFAULT_KEYWORDS = {
    "masters": ["ماجستير", "MASTERS", "دراسات عليا"],
    "phd": ["دكتوراه", "PhD", "أطروحة"],
    "services": ["خدمات طلابية", "جامعة", "طلبة", "كلية"],
}


async def discover(account: dict, keywords: dict = None) -> int:
    keywords = keywords or DEFAULT_KEYWORDS
    ctx = await fb_session.get_context(account)
    page = await ctx.new_page()
    found = 0
    try:
        for niche, words in keywords.items():
            for word in words[:3]:
                try:
                    await page.goto("https://www.facebook.com/search/groups/?q=" +
                                    __import__("urllib.parse", fromlist=["quote"]).quote(word),
                                    wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_timeout(5000)
                    for _ in range(4):
                        await page.mouse.wheel(0, 2000)
                        await page.wait_for_timeout(1500)
                    # استخراج روابط المجموعات من الصفحة
                    hrefs = await page.eval_on_selector_all(
                        "a[href*='/groups/']", "els => els.map(e => ({href: e.href, text: e.innerText}))")
                    for h in hrefs:
                        href = h.get("href", "").split("?")[0].rstrip("/")
                        if "/groups/" not in href or href.endswith("/groups"):
                            continue
                        gid = href.split("/groups/")[-1]
                        if not gid or gid in ("discover", "feed", "search"):
                            continue
                        name = (h.get("text") or "").strip().split("\n")[0][:120]
                        if db.add_group(href, name=name, niche=niche, account_id=account["id"], group_id=gid):
                            found += 1
                except Exception:
                    continue
        return found
    finally:
        await page.close()
