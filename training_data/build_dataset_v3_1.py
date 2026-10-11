"""Build V3.1 with broad, split-owned intent families; never opens V3 holdout."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from dataset_v2 import LABELS, normalize_for_overlap

ROOT = Path(__file__).parent
OUTPUT = ROOT / "chat_intents_v3_1.jsonl"
ROUTES = ["من عمان إلى إربد", "من الزرقاء إلى العقبة", "من جرش إلى السلط", "من مادبا إلى الكرك", "من عجلون إلى المفرق", "من معان إلى الطفيلة", "من الرمثا إلى البحر الميت", "Amman to Aqaba", "Irbid to Amman", "من البلقاء إلى العاصمة"]
WHEN = ["بكرا", "اليوم"]
REF = ["الطلب الحالي", "العرض الظاهر", "الخطوة الأخيرة", "الحجز المعروض", "الخيار الذي اخترته", "هذه العملية", "الطلب الذي بدأته", "الرحلة المختارة", "الحجز في حسابي", "المقعد الذي حجزته"]
ISSUE = ["فرامل السيارة ضعيفة", "مكيف الباص لا يعمل", "المحرك يصدر صوتاً", "الإطار يحتاج فحصاً", "البطارية لا تشحن", "السيارة لا تدور", "هناك اهتزاز أثناء القيادة", "لمبة المحرك مضيئة", "الباص يحتاج تغيير زيت", "الباب لا يغلق جيداً"]
SOCIAL = ["يا نيان", "يا فريق نيان", "أنا مستخدم جديد", "من التطبيق", "هذا الصباح", "هذا المساء", "من الأردن", "قبل ما أبدأ", "اليوم", "بدايةً"]

TRAIN = {
"availability_inquiry": ["هل يوجد مقعد متاح {route} {when}", "في كراسي فاضية {route} {when}", "كم مقعد بقي {route} {when}", "هل السعة تكفي لشخصين {route} {when}", "هل الرحلة ممتلئة {route} {when}", "لسا في محل {route} {when}", "هل أجد مكاناً في الباص {route} {when}", "are seats left {route} {when}", "available seats for {route} {when}", "في مجال أركب {route} {when}"],
"book_trip": ["بدي أحجز مقعد {route} {when}", "احجزلي تذكرة {route} {when}", "أريد تثبيت حجز {route} {when}", "ممكن تحفظ إلي مقعد {route} {when}", "بدي أعمل booking {route} {when}", "reserve a seat {route} {when}", "I want to book {route} {when}", "أحتاج حجز فعلي {route} {when}", "ثبّت إلي مكان {route} {when}", "أصدر لي تذكرة {route} {when}"],
"trip_search": ["شو في رحلات {route} {when}", "دورلي على باص {route} {when}", "اعرض خيارات السفر {route} {when}", "هل يوجد نقل {route} {when}", "وين بلاقي رحلات {route} {when}", "بدي أشوف المتاح {route} {when}", "find trips {route} {when}", "show departures {route} {when}", "في رحلة رايحة {route} {when}", "ما الخيارات الموجودة {route} {when}"],
"trip_information": ["متى موعد الرحلة {route} {when}", "على أي ساعة الانطلاق {route} {when}", "كم مدة الطريق {route} {when}", "من أين التجمع {route} {when}", "متى الوصول {route} {when}", "هل الرحلة مباشرة {route} {when}", "هل فيها توقفات {route} {when}", "what time does it leave {route} {when}", "what are trip details {route} {when}", "ما خط السير {route} {when}"],
"price_inquiry": ["كم سعر التذكرة {route} {when}", "شو السعر {route} {when}", "قديش الأجرة {route} {when}", "كم تكلفة الرحلة {route} {when}", "كم بدفع {route} {when}", "ما قيمة المقعد {route} {when}", "what is the fare {route} {when}", "how much is the ticket {route} {when}", "price before booking {route} {when}", "هل السعر معروف {route} {when}"],
"cancel_booking": ["بدي ألغي {ref}", "أريد إلغاء {ref}", "شيل {ref} من حسابي", "لا أحتاج {ref} المحفوظ", "كيف أوقف {ref}", "cancel {ref}", "remove my {ref}", "الغِ التذكرة ضمن {ref}", "ألغِ المقعد في {ref}", "أريد استرداد {ref}"],
"cancellation": ["لا أريد إكمال {ref}", "تراجع عن {ref}", "مش هسا، أوقف {ref}", "لا تثبّت {ref}", "غيّرت رأيي في {ref}", "abort {ref}", "do not continue {ref}", "اترك {ref} بدون تنفيذ", "أنهي {ref} الآن", "ما بدي أكمل {ref}"],
"confirmation": ["نعم أكمل {ref}", "موافق، ثبّت {ref}", "أكيد تابع {ref}", "توكلنا نفّذ {ref}", "ثبت {ref}", "yes proceed with {ref}", "confirmed {ref}", "أعتمد {ref}", "كمل الخطوة الخاصة بـ {ref}", "تمام نفذ {ref}"],
"maintenance_request": ["{issue} وبدي صيانة", "محتاج فحص لأن {issue}", "سجّل طلب صيانة: {issue}", "بدي تصليح، {issue}", "the vehicle needs repair: {issue}", "عندي عطل: {issue}", "افحص المركبة لأن {issue}", "بدي موعد صيانة، {issue}", "السيارة فيها مشكلة: {issue}", "repair request بسبب أن {issue}"],
"complaint": ["عندي شكوى عن {ref}", "الخدمة في {ref} كانت سيئة", "أريد اعتراضاً بخصوص {ref}", "التأخير في {ref} أزعجني", "السائق في {ref} لم يكن محترماً", "I want to complain about {ref}", "سجّل شكوى على {ref}", "غير راضٍ عن {ref}", "تجربتي مع {ref} غير مقبولة", "بدي متابعة شكوى عن {ref}"],
"company_information": ["مين شركات النقل {route} {when}", "أي شركة تشغل {route} {when}", "أعطيني أسماء الناقلين {route} {when}", "ما الشركات المتاحة {route} {when}", "من هو المشغّل {route} {when}", "which company runs {route} {when}", "list transport companies {route} {when}", "هل في شركات باصات {route} {when}", "شركات السفر لهذه الوجهة {route} {when}", "أي ناقل موجود {route} {when}"],
"help": ["كيف أستخدم {ref}", "بدي مساعدة في {ref}", "اشرحلي {ref}", "شو بتقدر تعمل بخصوص {ref}", "وين أبدأ مع {ref}", "help me with {ref}", "guide me through {ref}", "ممكن توضح خطوات {ref}", "كيف أتعامل مع {ref}", "أحتاج إرشاداً حول {ref}"],
"greeting": ["مرحبا {social}", "أهلا {social}", "السلام عليكم {social}", "صباح الخير {social}", "مساء الخير {social}", "هلا {social}", "أهلين {social}", "hello {social}", "hi {social}", "يسعد صباحك {social}"],
"goodbye": ["شكراً مع السلامة {social}", "يعطيك العافية إلى اللقاء {social}", "باي {social}", "خلصنا سلام {social}", "نهارك سعيد {social}", "تصبح على خير {social}", "أشوفك لاحقاً {social}", "goodbye {social}", "see you {social}", "thanks, bye {social}"],
"general_conversation": ["كيفك {social}", "شو الأخبار {social}", "احكيلي نكتة {social}", "شو رأيك بالسفر {social}", "كيف الجو {social}", "tell me something interesting {social}", "how are you {social}", "خلينا نحكي شوي {social}", "قلي معلومة {social}", "شو جديدك {social}"],
}

VALIDATION = {
"availability_inquiry": ["هل بقي مكان شاغر {route} {when}", "هل أستطيع إيجاد كرسي {route} {when}", "is there capacity {route} {when}"],
"book_trip": ["رتّب لي حجزاً {route} {when}", "أود إنشاء تذكرة {route} {when}", "hold a seat for me {route} {when}"],
"trip_search": ["هل هناك مواصلات {route} {when}", "أبحث عن departures {route} {when}", "اقترح رحلة {route} {when}"],
"trip_information": ["ما تفاصيل المغادرة والوصول {route} {when}", "أين ينتهي المسار {route} {when}", "give me schedule details {route} {when}"],
"price_inquiry": ["بكم بتطلع الرحلة {route} {when}", "شو تكلفة المشوار {route} {when}", "what does this trip cost {route} {when}"],
"cancel_booking": ["أوقف تذكرتي السابقة {ref}", "هل يمكن حذف الحجز {ref}", "please cancel the saved {ref}"],
"cancellation": ["ما رح أمشي في {ref}", "خلي {ref} لوقت ثاني", "I decline {ref}"],
"confirmation": ["يعني اعتمد {ref}", "تفضل نفذ {ref}", "I approve {ref}"],
"maintenance_request": ["المركبة تحتاج ورشة لأن {issue}", "رتب فني لـ {issue}", "maintenance needed: {issue}"],
"complaint": ["أريد تصعيد مشكلة {ref}", "تجربة {ref} غير مرضية", "file a service complaint for {ref}"],
"company_information": ["من مقدمو النقل {route} {when}", "أي operators متوفرون {route} {when}", "who provides service {route} {when}"],
"help": ["دلّني على طريقة {ref}", "ما التعليمات الخاصة بـ {ref}", "I need assistance with {ref}"],
"greeting": ["يا هلا {social}", "صباح النور {social}", "good morning {social}"],
"goodbye": ["الله معك {social}", "وداعاً {social}", "talk later {social}"],
"general_conversation": ["خلينا ندردش {social}", "شو بتعمل {social}", "tell me a story {social}"],
}


def values(index: int) -> dict:
    route_index = index % len(ROUTES); cycle = index // len(ROUTES)
    return {"route": ROUTES[route_index], "when": WHEN[cycle % len(WHEN)], "ref": f"{REF[route_index]} {WHEN[cycle % len(WHEN)]}", "issue": f"{ISSUE[route_index]} {WHEN[cycle % len(WHEN)]}", "social": f"{SOCIAL[route_index]} {WHEN[cycle % len(WHEN)]}"}


def build_rows(templates: dict[str, list[str]], split: str, per_family: int) -> list[dict]:
    rows = []
    for intent in LABELS:
        for family, template in enumerate(templates[intent]):
            for index in range(per_family):
                rows.append({"text": template.format(**values(index)), "intent": intent, "split": split, "family": f"v3_1-{split}-{intent}-{family}", "source": "synthetic_curated_v3_1"})
    return rows


def validate(rows: list[dict]) -> dict:
    normalized, family_splits = set(), {}
    for row in rows:
        text = normalize_for_overlap(row["text"])
        if text in normalized: raise ValueError(f"duplicate normalized text: {row['text']}")
        normalized.add(text); family_splits.setdefault(row["family"], set()).add(row["split"])
    train, validation = [row for row in rows if row["split"] == "train"], [row for row in rows if row["split"] == "validation"]
    train_families = {label: {row["family"] for row in train if row["intent"] == label} for label in LABELS}
    validation_families = {label: {row["family"] for row in validation if row["intent"] == label} for label in LABELS}
    if len(train) != 3000 or len(validation) != 450: raise ValueError("unexpected split total")
    if any(len(train_families[label]) < 10 or len(validation_families[label]) < 3 or train_families[label] & validation_families[label] for label in LABELS): raise ValueError("family diversity or isolation failure")
    if any(Counter(row["intent"] for row in train)[label] != 200 or Counter(row["intent"] for row in validation)[label] != 30 for label in LABELS): raise ValueError("class balance failure")
    return {"train_rows": len(train), "validation_rows": len(validation), "train_families_per_intent": {label: len(train_families[label]) for label in LABELS}, "validation_families_per_intent": {label: len(validation_families[label]) for label in LABELS}}


def build() -> dict:
    rows = build_rows(TRAIN, "train", 20) + build_rows(VALIDATION, "validation", 10)
    report = validate(rows)
    with OUTPUT.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows: handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return report


if __name__ == "__main__": print(json.dumps(build(), ensure_ascii=False, indent=2))
