"""
ناشر فيسبوك: ينشر منشورات مكتبتك (مصنفة: ماجستير، خدمات...) على المجموعات المطابقة.
يختار المنشور المناسب لكل مجموعة حسب فئتها (niche)، وينشر على كل الحسابات بالتناوب.
"""
import asyncio
import random
import time
from core import db
from platforms.facebook import session as fb_session

# محددات قابلة للتحديث من config/selectors.json عند تغيير فيسبوك واجهته
SELECTORS = {
    "post_box": "div[contenteditable='true'][role='textbox']",
    "post_box_alt": "textarea",
    "publish_button": "div[aria-label='نشر'][role='button'], button[type='submit'][name='发表']",
    "publish_button_ar": "div[role='button']:has-text('نشر')",
}


async def publish_to_group(account: dict, group_url: str, text: str, media: list = None) -> tuple[bool, str | None]:
    ctx = await fb_session.get_context(account)
    page = await ctx.new_page()
    try:
        await page.goto(group_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)
        # كتابة النص
        box = await page.query_selector(SELECTORS["post_box"])
        if not box:
            box = await page.query_selector(SELECTORS["post_box_alt"])
        if not box:
            return False, "لم يُعثر على صندوق الكتابة (ربما لم تنضم للمجموعة أو تغيرت الواجهة)"
        await box.click()
        await page.wait_for_timeout(1500)
        for chunk in [text[i:i + 15] for i in range(0, len(text), 15)]:
            await page.keyboard.type(chunk, delay=random.randint(20, 80))
            await page.wait_for_timeout(random.randint(50, 250))
        # رفع الوسائط إن وجدت
        if media:
            try:
                file_input = await page.wait_for_selector(
                    "input[type='file'][accept*='image'], input[type='file']", state="attached", timeout=5000)
                await file_input.set_input_files(media[:4])
                await page.wait_for_timeout(4000)
            except Exception:
                pass
        await page.wait_for_timeout(random.randint(2000, 5000))
        # زر النشر
        btn = await page.query_selector(SELECTORS["publish_button"])
        if not btn:
            btn = await page.query_selector(SELECTORS["publish_button_ar"])
        if not btn:
            return False, "لم يُعثر على زر النشر"
        await btn.click()
        await page.wait_for_timeout(6000)
        return True, None
    except Exception as e:
        return False, str(e)[:300]
    finally:
        await page.close()


async def run_campaign(post_row: dict, accounts: list, groups: list, settings: dict):
    """
    حملة نشر: المنشور على كل مجموعات فئته، بكل الحسابات، بتأخيرات بشرية.
    post_row: صف من جدول posts (niche محدد) - لذلك تختار منشورات ماجستير للمجموعات الماجستير فقط.
    """
    results = []
    delay_acc = settings.get("delay_between_accounts_sec", 20)
    delay_grp = settings.get("delay_between_groups_sec", 90)
    for acc in accounts:
        if not acc.get("enabled"):
            continue
        media = __import__("json").loads(post_row.get("media_paths") or "[]")
        for g in groups:
            ok, err = await publish_to_group(acc, g["url"], post_row["text"], media)
            db.log_publish(acc["id"], g["url"], post_row["id"], ok, err)
            results.append({"account": acc["id"], "group": g["url"], "ok": ok, "error": err})
            await asyncio.sleep(delay_grp + random.randint(0, 60))
        await asyncio.sleep(delay_acc + random.randint(0, 30))
    return results
