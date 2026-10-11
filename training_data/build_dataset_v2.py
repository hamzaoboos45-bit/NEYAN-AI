"""Create V2 supervision and an external challenge test from disjoint families.

The corpus is synthetic and no-PII.  Training-family and challenge-family
phrases are intentionally separate; the validator rejects overlap.
"""
from __future__ import annotations

import json
from pathlib import Path

from dataset_v2 import LABELS, read_jsonl, validate_isolation

ROOT = Path(__file__).parent
V2 = ROOT / "chat_intents_v2.jsonl"
CHALLENGE = ROOT / "chat_intents_challenge_test.jsonl"

# Separate lexical families are used for V2 vs challenge, especially for the
# easily-confused route, price, availability, and booking intents.
TRAIN_STEMS = {
 "book_trip": ["بدي أحجز", "بقدر أعمل حجز", "احجزلي", "نفسي أسافر", "I want to reserve"],
 "trip_search": ["شو في رحلات", "ورجيني الخيارات", "دورلي على رحلة", "هل يوجد باص", "show trips"],
 "availability_inquiry": ["في مقاعد", "لسا في محل", "كم كرسي ضايل", "هل يوجد مكان", "are seats left"],
 "price_inquiry": ["قديش السعر", "كم بتكلف", "شو أجرة", "كم ثمن التذكرة", "what is the fare"],
 "trip_information": ["متى موعد الانطلاق", "كم مدة الطريق", "من وين بتنطلق", "هل فيها توقفات", "what time does it leave"],
 "cancel_booking": ["بدي ألغي حجزي", "كيف ألغي التذكرة", "أوقف الحجز الحالي", "إلغاء المقعد المحجوز", "cancel my reservation"],
 "maintenance_request": ["السيارة بدها صيانة", "الباص فيه عطل", "المحرك بحاجة تصليح", "بدي تغيير زيت", "the vehicle needs repair"],
 "complaint": ["عندي مشكلة بالخدمة", "بدي أقدم شكوى", "السائق تعامل بشكل سيء", "التأخير أزعجني", "I need to complain"],
 "company_information": ["مين شركات النقل", "شو الشركات المتاحة", "أعطيني أسماء المشغلين", "أي شركة بتخدم", "which operator runs trips"],
 "help": ["كيف بستخدم نيان", "شو بتقدر تساعدني", "بدي إرشاد", "اشرحلي الخطوات", "help me use the service"],
 "confirmation": ["نعم أكمل", "تمام اعملها", "موافق على الحجز", "أكيد تابع", "yes go ahead"],
 "cancellation": ["لا ما بدي أكمل", "وقف العملية", "غيرت رأيي", "مش هسا", "no do not continue"],
 "greeting": ["مرحبا نيان", "أهلا", "صباح الخير", "مساء النور", "hello NEYAN"],
 "goodbye": ["يعطيك العافية سلام", "شكرا مع السلامة", "إلى اللقاء", "تصبح على خير", "see you later"],
 "general_conversation": ["كيفك اليوم", "شو الأخبار", "احكيلي شيء لطيف", "شو رأيك بالسفر", "tell me a joke"],
}
CHALLENGE_STEMS = {
 "book_trip": ["حابّة أثبت مقعد", "بدي أوفر إلي كرسي", "رتبلي سفرة", "can you book me", "أريد إصدار تذكرة"],
 "trip_search": ["في شي طالع", "بدي أتصفح رحلات", "ما الخيارات المتجهة", "browse departures", "هل في مواصلات"],
 "availability_inquiry": ["في سعة فاضية", "الرحلة مليانة ولا", "باقي أماكن", "can two people fit", "كم متاح"],
 "price_inquiry": ["قديش بدفع", "شو الكلفة النهائية", "السعر شامل شو", "ticket cost please", "بكم المشوار"],
 "trip_information": ["وين نقطة التجمع", "على أي ساعة الوصول", "ما خط السير", "is it direct", "تفاصيل المغادرة"],
 "cancel_booking": ["شيل الحجز باسمي", "ما بدي تذكرتي", "أرجع الحجز", "withdraw my booked seat", "إلغاء سفرتي"],
 "maintenance_request": ["فرامل السيارة مش طبيعية", "المكيف خربان بالباص", "بدّي فحص للإطارات", "engine warning appeared", "المركبة ما بتدور"],
 "complaint": ["التجربة ما كانت عادلة", "في اعتراض على الرحلة", "الالتزام بالمواعيد سيء", "service quality disappointed me", "السائق ما احترمنا"],
 "company_information": ["من المشغّل لهذه الوجهة", "أي ناقل متوفر", "وين ألاقي جهات النقل", "company list please", "شركات الباصات"],
 "help": ["وضحلي شو أعمل", "بدّي مساعدة عامة", "دليل الحجز وين", "what can NEYAN do", "مش عارف أبدأ"],
 "confirmation": ["ثبّت الطلب", "توكلنا", "تابع", "confirmed", "اختياري نعم"],
 "cancellation": ["مش مناسب إلي", "خليها لوقت ثاني", "لا تثبت شيء", "abort this", "تراجع"],
 "greeting": ["يا هلا", "يسعد صباحك", "أهلين", "hey there", "السلام عليكم"],
 "goodbye": ["خلص شكراً", "نهارك سعيد", "باي باي", "talk later", "وداعاً"],
 "general_conversation": ["شو جديدك", "كيف الجو عندك", "خلينا نحكي", "are you well", "قلي معلومة"],
}
ROUTES = ["من عمان لإربد", "من الزرقاء للعقبة", "من جرش للسلط", "من مادبا للكرك", "من معان للطفيلة", "من عجلون للمفرق", "Amman to Aqaba", "Irbid to Amman", "من البلقاء للعاصمة", "من الرمثا للبحر الميت"]
TIMES = ["بكرا", "اليوم", "يوم الجمعة", "الصبح", "بعد الظهر", "المساء", "الأسبوع الجاي", "بتاريخ 12/10", "حوالي الساعة 8", "لشخصين"]
STYLE_TAILS = ["لو سمحت", "إذا ممكن", "بشكل واضح", "من غير تعقيد", "لأني مستعجل", "قبل ما أقرر", "حسب المتاح", "وبدي جواب دقيق"]
VALIDATION_OPENERS = ["ممكن", "بالمناسبة", "بخصوص مشواري", "عندي استفسار", "قبل ما أتابع", "بدي أعرف", "لو تكرمت", "للتأكد"]
SOCIAL_DETAILS = ["هسا", "بهذا الوقت", "بهالموضوع", "عن المشوار", "مع نيان", "اليوم", "بكل وضوح", "إلي", "بهالمرحلة", "من فضلك"]

def _rows(stems: dict[str, list[str]], split: str, count: int, family_prefix: str):
    rows = []
    for label in LABELS:
        for index in range(count):
            stem = stems[label][index % len(stems[label])]
            detail = ROUTES[index % len(ROUTES)] if label in {"book_trip", "trip_search", "availability_inquiry", "price_inquiry", "trip_information"} else TIMES[index % len(TIMES)]
            # Social and state replies remain naturally short; business intents
            # receive route/time context without changing their semantic label.
            tail = STYLE_TAILS[index // 10]
            text = f"{stem} {SOCIAL_DETAILS[index % len(SOCIAL_DETAILS)]} {tail}" if label in {"greeting", "goodbye", "confirmation", "cancellation", "general_conversation"} else f"{stem} {detail} {TIMES[(index * 3) % len(TIMES)]} {tail}".strip()
            if split == "validation":
                text = f"{VALIDATION_OPENERS[index % len(VALIDATION_OPENERS)]}، {text}"
            rows.append({"text": text, "intent": label, "split": split, "family": f"{family_prefix}-{label}-{index // len(stems[label])}", "source": "synthetic_curated_v2"})
    return rows


def _challenge_rows():
    """Independent grammar from the training/validation construction.

    This avoids merely paraphrasing the V2 template while retaining realistic
    route, code-switching, and colloquial coverage.
    """
    rows = []
    route_intents = {"book_trip", "trip_search", "availability_inquiry", "price_inquiry", "trip_information"}
    social_intents = {"greeting", "goodbye", "confirmation", "cancellation", "general_conversation"}
    prompts = ["شو بتنصح؟", "بدي أعرف قبل القرار.", "هل بتقدر توضح؟", "هذا استفساري الوحيد.", "يعني كيف؟", "بكلمات بسيطة.", "بدون ما أعمل طلب الآن.", "وأنا بانتظار الرد.", "إذا كانت الخدمة متاحة.", "للتخطيط للمشوار."]
    for label in LABELS:
        for index, stem in enumerate(CHALLENGE_STEMS[label] * 2):
            if label in route_intents:
                text = f"{ROUTES[(index * 7) % len(ROUTES)]}: {stem}؟ {prompts[index]}"
            elif label in social_intents:
                text = f"{stem} — {prompts[index]}"
            else:
                text = f"{prompts[index]} {stem}، {TIMES[(index * 5) % len(TIMES)]}."
            rows.append({"text": text, "intent": label, "split": "challenge", "family": f"challenge-{label}-{index // 5}", "source": "synthetic_curated_v2"})
    return rows

def build():
    # 80/20 stratified V2: exactly 80 train + 20 validation per intent.
    train = _rows(TRAIN_STEMS, "train", 80, "train")
    validation = _rows(TRAIN_STEMS, "validation", 20, "validation")
    challenge = _challenge_rows()
    for path, rows in ((V2, train + validation), (CHALLENGE, challenge)):
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    result = validate_isolation(read_jsonl(V2, {"train", "validation"}), read_jsonl(CHALLENGE, {"challenge"}))
    return result

if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))
