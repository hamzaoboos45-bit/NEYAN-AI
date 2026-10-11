"""Build the safe, reviewed chat-intent supervision set.

The source examples below are synthetic and contain no customer data.  Each
utterance is assigned to one of the *existing* canonical intent labels used
by ``backend.nlp.intent_classifier``.  ``split`` is explicit rather than
random: wording families are kept together, so a close template variant can
never appear in both training and held-out evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path


# The three lists for each label deliberately use different wording families.
# This provides a reproducible 8/2/3 split without template leakage.
EXAMPLES: dict[str, dict[str, list[str]]] = {
    "greeting": {
        "train": ["مرحبا", "اهلا وسهلا", "هلا كيفك", "السلام عليكم", "صباح الخير", "مساء الخير", "hello", "good morning"],
        "validation": ["اهلين نيان", "هاي"],
        "test": ["سلام عليكم", "هلو", "good evening"],
    },
    "goodbye": {
        "train": ["مع السلامة", "الى اللقاء", "باي", "الله معك", "تصبح على خير", "خلصنا شكرا", "goodbye", "see you"],
        "validation": ["اشوفك بعدين", "في امان الله"],
        "test": ["يلا سلام", "ما في شي ثاني", "have a nice day"],
    },
    "book_trip": {
        "train": ["بدي احجز رحلة", "اريد تذكرة سفر", "نفسي اسافر بكرا", "محتاج مواصلات للعقبة", "احجزلي رحلة من عمان", "اريد اروح اربد", "book a trip", "i need a ticket"],
        "validation": ["بدي اسافر من جرش", "reserve a seat for me"],
        "test": ["حابب اعمل حجز", "بدي رحلة للطفيلة", "i want to travel"],
    },
    "cancel_booking": {
        "train": ["بدي الغي حجزي", "اريد الغاء التذكرة", "الغاء الحجز الحالي", "ممكن تلغي الحجز", "بدي اكنسل الرحلة", "الغ طلب السفر", "cancel my booking", "cancel my reservation"],
        "validation": ["اريد الغاء حجزي السابق", "please cancel the ticket"],
        "test": ["كيف الغي حجز قائم", "الغاء تذكرتي", "i need to cancel a booking"],
    },
    "trip_search": {
        "train": ["ورجيني الرحلات بس لا تحجز", "هل في رحلة من عمان للعقبة", "اعرض المتاح بكرا", "بدي اشوف رحلات اربد", "دورلي على باص للزرقاء", "شو الموجود يوم الجمعة", "show me available trips", "find trips to Aqaba"],
        "validation": ["ما بدي احجز بس بدي اشوف", "في trip من Amman ل Aqaba"],
        "test": ["وين بلاقي رحلات لمعان", "اعرض خيارات السفر", "list trips for tomorrow"],
    },
    "trip_information": {
        "train": ["كم مدة الرحلة", "شو تفاصيل هالرحلة", "متى بتوصل الرحلة", "من وين بتنطلق", "هل الرحلة مباشرة", "شو وقت الوصول", "how long is the trip", "what are the trip details"],
        "validation": ["بدي معلومات عن الرحلة", "هل في توقفات بالطريق"],
        "test": ["متى موعد الانطلاق", "احكيلي عن مسار الرحلة", "does it stop on the way"],
    },
    "company_information": {
        "train": ["شو شركات النقل الموجودة", "اعرض الشركات", "مين الشركات المتاحة", "بدي اسماء شركات الباصات", "هل في شركة للعقبة", "وين الاقي شركات سفر", "show transport companies", "which companies operate trips"],
        "validation": ["ما هي شركات النقل", "list the companies"],
        "test": ["مين مشغل الرحلات", "اعرضلي شركات السفر", "company options please"],
    },
    "maintenance_request": {
        "train": ["السيارة بدها صيانة", "عندي عطل بالمحرك", "بدي اغير زيت", "البطارية خربانة", "عندي بنشر", "السيارة مش ماشية", "i need vehicle maintenance", "the engine needs repair"],
        "validation": ["بدي تصليح كوشوك", "my car has a problem"],
        "test": ["في مشكلة بالسيارة", "موتور الباص معطل", "need an oil change"],
    },
    "complaint": {
        "train": ["عندي شكوى", "الخدمة سيئة", "الرحلة تأخرت كثير", "الموظف تعامل بطريقة سيئة", "مش راضي عن التجربة", "بدي اشتكي", "this is a complaint", "the service was terrible"],
        "validation": ["صار معي موقف مزعج", "i am unhappy with the service"],
        "test": ["بدي اقدم اعتراض", "السائق كان غير مهذب", "i want to complain"],
    },
    "help": {
        "train": ["شو بتقدر تعمل", "كيف بستخدم التطبيق", "محتاج مساعدة", "اشرحلي الخدمات", "كيف بقدر ألغي الحجز؟", "ممكن تساعدني", "what can you do", "i need help"],
        "validation": ["كيف احجز من خلالك", "guide me please"],
        "test": ["بدّي شرح", "شو الخدمات المتوفرة", "how does this work"],
    },
    "price_inquiry": {
        "train": ["كم سعر الرحلة", "قديش التذكرة", "بكم السفر للعقبة", "شو التكلفة", "كم الثمن", "بدي اعرف السعر فقط", "what is the price", "how much is a ticket"],
        "validation": ["السعر شامل شو", "fare to Irbid"],
        "test": ["قديش بدفع", "بدي أعرف سعر الرحلة", "what does it cost"],
    },
    "availability_inquiry": {
        "train": ["كم مقعد باقي", "هل في اماكن فاضية", "في مقاعد للرحلة", "قديش ضل كراسي", "هل بتتسع لشخصين", "شو المتوفر من المقاعد", "how many seats are left", "is there space"],
        "validation": ["في مكان على الباص", "available seats please"],
        "test": ["هل في كرسي فاضي", "كم راكب بقدر احجز", "are seats available"],
    },
    "confirmation": {
        "train": ["نعم", "اكيد", "موافق", "تمام", "اعملها", "يلا", "yes", "confirm"],
        "validation": ["بالتاكيد", "proceed"],
        "test": ["اوافق", "sure", "صحيح"],
    },
    "cancellation": {
        "train": ["لا", "مش هسا", "ما بدي", "وقف", "ارجع", "خلص لا", "no", "not now"],
        "validation": ["لا تلغي الحجز", "nevermind"],
        "test": ["ما ابغى اكمل", "stop", "مش موافق"],
    },
    "general_conversation": {
        "train": ["كيف حالك", "شو الاخبار", "احكيلي نكتة", "شو رايك بالطقس", "مين انت", "خبرني اشي لطيف", "how are you", "tell me a joke"],
        "validation": ["شو بتعمل اليوم", "what is up"],
        "test": ["بدّي نحكي شوي", "شو رأيك بالسفر", "tell me something interesting"],
    },
}


def build(destination: Path | None = None) -> Path:
    destination = destination or Path(__file__).with_name("chat_intents.jsonl")
    rows = []
    for label, partitions in EXAMPLES.items():
        for split, texts in partitions.items():
            rows.extend({"text": text, "intent": label, "split": split} for text in texts)
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return destination


if __name__ == "__main__":
    print(build())
