"""Build V3 corpora with split-owned semantic families and no filler suffixes."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from dataset_v2 import LABELS, normalize_for_overlap, read_jsonl, token_similarity

ROOT = Path(__file__).parent
TRAIN_VALID = ROOT / "chat_intents_v3.jsonl"
FINAL = ROOT / "chat_intents_final_holdout_v3.jsonl"
V2_CHALLENGE = ROOT / "chat_intents_challenge_test.jsonl"

ROUTES = ["من عمان إلى إربد", "من الزرقاء إلى العقبة", "من جرش إلى السلط", "من مادبا إلى الكرك", "من عجلون إلى المفرق", "من معان إلى الطفيلة", "من الرمثا إلى البحر الميت", "Amman to Aqaba", "Irbid to Amman", "من البلقاء إلى العاصمة"]
WHEN = ["بكرا", "اليوم", "يوم الجمعة", "الصبح", "المساء"]
COUNTS = ["لمقعد واحد", "لشخصين", "لثلاثة ركاب", "لمقعدين", "لعائلتي"]
SOCIAL = ["يا نيان", "يا فريق نيان", "لأول مرة", "هذا الصباح", "هذا المساء", "في بداية استخدامي", "قبل ما أبدأ", "من التطبيق", "من الأردن", "اليوم"]
ISSUES = ["فرامل السيارة ضعيفة", "مكيف الباص لا يعمل", "المحرك يصدر صوتاً", "الإطار يحتاج فحصاً", "البطارية لا تشحن", "السيارة لا تدور", "هناك اهتزاز أثناء القيادة", "لمبة المحرك مضيئة", "الباص يحتاج تغيير زيت", "الباب لا يغلق جيداً"]
REFERENCES = ["الحجز السابق", "التذكرة الموجودة", "العرض الحالي", "هذه الخطوة", "الطلب الذي بدأته", "الخيار الظاهر", "الرحلة الأخيرة", "حجزي من التطبيق", "الطلب المعروض", "العملية الحالية"]
REFERENCE_CONTEXTS = ["في التطبيق", "من اليوم", "الذي أراه الآن", "قبل قليل", "لهذا المسار"]
ISSUE_CONTEXTS = ["منذ الصباح", "أثناء القيادة", "بعد آخر رحلة", "في المركبة الآن", "من يومين"]

# Each entry is an independent semantic family. Train and validation families
# are deliberately different; final-holdout families are never used elsewhere.
FAMILIES = {
"book_trip": {"train": ["أريد حجز مقعد {route} {when}", "بدي أثبّت {count} {route} {when}", "احجزلي تذكرة سفر {route} {when}", "I need to reserve a seat {route} {when}"], "validation": ["ممكن تعمل حجز {route} {when} {count}"], "holdout": ["بدي أعمل حجز فعلي {route} {when}", "please book {count} {route} {when}"]},
"availability_inquiry": {"train": ["هل بقي مقعد متاح {route} {when}", "في كراسي فاضية {route} {when}", "كم مقعد باقي {route} {when}", "are seats available {route} {when}"], "validation": ["هل الرحلة ممتلئة أم فيها مكان {route} {when}"], "holdout": ["لسا في محل {route} {when}", "can {count} fit {route} {when}"]},
"trip_search": {"train": ["شو في رحلات {route} {when}", "دورلي على رحلة {route} {when}", "اعرض خيارات السفر {route} {when}", "show departures {route} {when}"], "validation": ["هل يوجد باص {route} {when}"], "holdout": ["بدي أتصفح رحلات {route} {when}", "find available trips {route} {when}"]},
"trip_information": {"train": ["متى موعد الانطلاق {route} {when}", "كم مدة الطريق {route} {when}", "من أين نقطة التجمع {route} {when}", "does this trip stop on the way {route} {when}"], "validation": ["ما تفاصيل المغادرة والوصول {route} {when}"], "holdout": ["على أي ساعة الوصول {route} {when}", "هل الرحلة مباشرة {route} {when}"]},
"price_inquiry": {"train": ["كم سعر التذكرة {route} {when}", "قديش بتكلف الرحلة {route} {when}", "شو أجرة السفر {route} {when}", "what is the fare {route} {when}"], "validation": ["بكم المشوار {route} {when}"], "holdout": ["كم بدفع {route} {when}", "ticket cost for {route} {when}"]},
"cancel_booking": {"train": ["بدي ألغي {reference}", "أريد إلغاء {reference}", "شيل {reference} من حسابي", "cancel {reference}"], "validation": ["كيف ألغي {reference} باسمي"], "holdout": ["ألغِ {reference}", "I want to cancel {reference}"]},
"cancellation": {"train": ["لا أريد إكمال {reference}", "تراجع عن {reference}", "مش هسا، أوقف {reference}", "abort {reference}"], "validation": ["لا تثبّت {reference} الآن"], "holdout": ["خلينا نلغي {reference}", "do not continue {reference}"]},
"confirmation": {"train": ["نعم تابع {reference}", "موافق، ثبّت {reference}", "أكيد كمل {reference}", "yes, proceed with {reference}"], "validation": ["توكلنا، أكمل {reference}"], "holdout": ["ثبت {reference}", "confirmed, go ahead with {reference}"]},
"maintenance_request": {"train": ["{issue} وبدي صيانة", "محتاج فحص لأن {issue}", "بدي أفتح طلب صيانة: {issue}", "the vehicle needs repair because {issue}"], "validation": ["عندي عطل بالمركبة: {issue}"], "holdout": ["أحتاج تصليح، {issue}", "please schedule maintenance, {issue}"]},
"complaint": {"train": ["عندي شكوى لأن {reference} تأخر", "بدي أقدّم اعتراض على تعامل السائق في {reference}", "الخدمة في {reference} كانت سيئة وأريد شكوى", "I want to complain about {reference}"], "validation": ["غير راضٍ عن {reference} وأريد متابعة شكوى"], "holdout": ["سجّل شكوى بخصوص {reference}", "the experience with {reference} was unacceptable"]},
"company_information": {"train": ["مين شركات النقل المتاحة {route} {when}", "أي شركة تشغّل رحلات {route} {when}", "أعطيني أسماء مشغلي الباصات {route} {when}", "which transport companies operate {route} {when}"], "validation": ["شو شركات السفر الموجودة للوجهة {route} {when}"], "holdout": ["من هو الناقل لهذه الوجهة {route} {when}", "list companies serving {route} {when}"]},
"help": {"train": ["كيف أستخدم {reference} في نيان", "شو بتقدر تعمل إلي بخصوص {reference}", "بدي مساعدة في {reference}", "how does {reference} work"], "validation": ["اشرحلي خطوات {reference}"], "holdout": ["وين أبدأ مع {reference}", "help me understand {reference}"]},
"greeting": {"train": ["مرحبا {social}", "أهلا وسهلا {social}", "صباح الخير {social}", "hello {social}"], "validation": ["يا هلا {social}"], "holdout": ["مساء الخير {social}", "hi NEYAN {social}"]},
"goodbye": {"train": ["شكراً، مع السلامة {social}", "يعطيك العافية، إلى اللقاء {social}", "خلصنا، باي {social}", "thanks, goodbye {social}"], "validation": ["أشوفك لاحقاً {social}"], "holdout": ["نهارك سعيد، سلام {social}", "talk to you later {social}"]},
"general_conversation": {"train": ["كيف حالك {social}", "شو الأخبار {social}", "احكيلي نكتة {social}", "tell me something interesting {social}"], "validation": ["شو رأيك بالسفر {social}"], "holdout": ["خلينا نحكي شوي {social}", "how are you today {social}"]},
}


def values(index: int) -> dict:
    when = WHEN[(index // len(ROUTES)) % len(WHEN)]
    cycle = index // len(ROUTES)
    return {"route": ROUTES[index % len(ROUTES)], "when": when, "count": COUNTS[index % len(COUNTS)], "social": f"{SOCIAL[index % len(SOCIAL)]} {when}", "issue": f"{ISSUES[index % len(ISSUES)]} {ISSUE_CONTEXTS[cycle]}", "reference": f"{REFERENCES[index % len(REFERENCES)]} {REFERENCE_CONTEXTS[cycle]}"}


def generate(split: str, examples_per_family: int) -> list[dict]:
    rows = []
    for intent in LABELS:
        for family_index, template in enumerate(FAMILIES[intent][split]):
            for item_index in range(examples_per_family):
                rows.append({"text": template.format(**values(item_index)), "intent": intent, "split": split if split != "holdout" else "final_holdout", "family": f"v3-{split}-{intent}-{family_index}", "source": "synthetic_curated_v3"})
    return rows


def validate(train_valid: list[dict], holdout: list[dict]) -> dict:
    all_rows = train_valid + holdout
    normalized = {}
    families = {}
    for row in all_rows:
        key = normalize_for_overlap(row["text"])
        if key in normalized: raise ValueError(f"normalized duplicate: {row['text']}")
        normalized[key] = row
        families.setdefault(row["family"], set()).add(row["split"])
    if any(len(splits) != 1 for splits in families.values()): raise ValueError("family split leakage")
    v2_challenge = [json.loads(line) for line in V2_CHALLENGE.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in holdout:
        for old in v2_challenge:
            if token_similarity(row["text"], old["text"]) >= 0.92: raise ValueError(f"holdout overlaps retired challenge: {row['text']}")
    counts = {split: Counter(row["intent"] for row in all_rows if row["split"] == split) for split in ("train", "validation", "final_holdout")}
    if any(set(counts[split].values()) != {expected} for split, expected in (("train", 200), ("validation", 30), ("final_holdout", 20))): raise ValueError("unexpected class balance")
    return {"train": sum(counts["train"].values()), "validation": sum(counts["validation"].values()), "final_holdout": sum(counts["final_holdout"].values()), "families": len(families)}


def build():
    train = generate("train", 50)       # 4 groups x 50 = 200 per intent
    validation = generate("validation", 30)
    holdout = generate("holdout", 10)   # 2 groups x 10 = 20 per intent
    for path, rows in ((TRAIN_VALID, train + validation), (FINAL, holdout)):
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows: handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return validate(train + validation, holdout)


if __name__ == "__main__": print(json.dumps(build(), ensure_ascii=False, indent=2))
