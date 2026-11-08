"""
ذكاء فيسبوك: يعيد صياغة منشوراتك لكل مجموعة لتجنب تكرار النص (فلتر فيسبوك ضد السبام).
يستخدم نفس نمط مفاتيح hcnsec/apinex - ملف ai.json مستقل داخل هذا المشروع.
"""
import requests
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_ai():
    import json
    f = ROOT / "config" / "ai.json"
    if not f.exists():
        return {"providers": [], "model": "glm-5.3-flash"}
    return json.loads(f.read_text(encoding="utf-8"))


def rewrite_for_group(text: str, group_name: str, niche: str) -> str:
    """إعادة صياغة الذكي - تفشل بأمان (ترجع النص الأصلي) إن تعطل الـ AI."""
    cfg = _load_ai()
    providers = sorted([p for p in cfg.get("providers", []) if p.get("enabled") and p.get("api_key")],
                       key=lambda x: x.get("priority", 99))
    prompt = (f"أعد صياغة هذا المنشور بأسلوب مختلف مع الحفاظ على كل المعلومات والأرقام والروابط حرفيًا. "
              f"لا تضف أو تحذف معلومات. المجموعة: {group_name} (الفئة: {niche}).\n\nالمنشور:\n{text}")
    for p in providers:
        try:
            r = requests.post(p["base_url"].rstrip("/") + "/chat/completions",
                              headers={"Authorization": f"Bearer {p['api_key']}",
                                       "Content-Type": "application/json"},
                              json={"model": cfg.get("model", "glm-5.3-flash"),
                                    "messages": [{"role": "user", "content": prompt}],
                                    "temperature": 0.6, "max_tokens": 1500}, timeout=90)
            if r.status_code == 200:
                out = r.json()["choices"][0]["message"]["content"].strip()
                if len(out) > len(text) * 0.5:
                    return out
        except Exception:
            time.sleep(1)
    return text  # آمن: النص الأصلي
