"""Deterministic intent signals used by NEYAN's hybrid NLU pipeline.

This module is deliberately a bounded fast path, not a second chatbot. It
recognizes high-signal conversational language after shared normalization,
lets actionable requests outrank social wrappers, and leaves every state
transition and side effect to the existing ChatbotEngine and services.
"""

from __future__ import annotations

import re

from backend.nlp.preprocessing import normalize_arabic


GREETING_KEYWORDS = [
    "مرحبا", "اهلا", "اهلين", "هلا", "هلو", "هاي", "مراحب",
    "السلام عليكم", "السلام", "سلام", "صباح الخير", "مساء الخير",
    "صباح النور", "مساء النور", "كيفك", "كيف الحال", "شو الاخبار",
    "ايش الاخبار", "hello", "hi", "hey", "good morning", "good evening",
]
THANKS_KEYWORDS = [
    "شكرا", "يسلمو", "مشكور", "يعطيك العافية", "يسلمك", "thanks", "thank you",
]
GOODBYE_KEYWORDS = [
    "مع السلامة", "الى اللقاء", "في امان الله", "باي", "اشوفك", "goodbye", "see you",
    "الله معك", "تصبح على خير", "خلصنا", "انتهينا", "ما في شي ثاني",
]
BOOKING_KEYWORDS = [
    "حجز", "احجز", "حجزي", "تذكرة", "رحلة", "سفر", "مواصلات",
    "اريد حجز", "اريد اسافر", "اريد تذكرة", "بدي احجز", "بدي رحلة",
    "بدي اسافر", "بدي تذكرة", "بدي اروح", "اريد اروح", "رايح", "مسافر",
    "عاوز احجز", "عايز احجز", "عايز اسافر", "عاوز رحلة", "نفسي اسافر",
    "محتاج رحلة", "ابغى اسافر", "ابغى احجز", "ودي اسافر",
    "book", "booking", "trip", "travel", "ticket", "reserve", "reservation",
    "i need a trip",
]
MAINTENANCE_KEYWORDS = [
    "صيانة", "تصليح", "اصلاح", "عطل", "اعطال", "بدي صيانة", "اريد صيانة",
    "احتاج صيانة", "مشكلة بالمركبة", "مشكلة في السيارة", "السيارة خربانة",
    "عربيتي بتعطل", "عربيتي واقفة", "السيارة مش ماشية", "بنشر", "كوشوك",
    "محرك", "موتور", "تغيير زيت", "بطارية", "maintenance", "repair", "fix",
    "tire", "engine", "oil", "battery", "car problem", "vehicle issue",
]
SEARCH_TRIP_KEYWORDS = [
    "ما هي الرحلات", "عرض الرحلات", "اعرض الرحلات", "الرحلات المتاحة",
    "ابحث عن رحلة", "هل يوجد رحلة", "هل في رحلة", "في رحلة", "في رحلات",
    "وين الرحلات", "شو الرحلات", "search trip", "find trip", "available trips",
    "show trips", "what trips", "list trips",
]
ASK_PRICE_KEYWORDS = [
    "كم السعر", "ما السعر", "كم التكلفة", "كم الثمن", "السعر كم", "بكم التذكرة",
    "بكم", "قديش", "شو سعرها", "price", "cost", "how much", "fare", "ticket price",
]
ASK_SEATS_KEYWORDS = [
    "كم مقعد", "المقاعد المتاحة", "هل يوجد مقاعد", "هل في مقاعد", "في مكان",
    "في مقاعد", "فاضي", "في اماكن فاضية", "كم مكان باقي", "available seats",
    "seats left", "how many seats", "is there space",
]
ASK_COMPANIES_KEYWORDS = [
    "ما هي الشركات", "الشركات المتاحة", "اعرض الشركات", "شركات النقل", "وين الشركات",
    "في شركات", "شو الشركات", "اسماء الشركات", "companies", "transport companies",
    "which companies", "list companies", "show companies",
]
HELP_KEYWORDS = [
    "شو بتقدر تعمل", "شو الخدمات", "ماذا تستطيع ان تفعل", "ماذا تفعل", "ما هي خدماتك",
    "خدماتك", "كيف تستخدم", "كيف بستخدمك", "ممكن تساعدني", "what can you do",
    "what do you do", "services", "guide me", "i need help", "help",
]
COMPLAINT_KEYWORDS = [
    "شكوى", "اريد تقديم شكوى", "اشتكي", "غير راضي", "الخدمة سيئة", "خدمة سيئة",
    "زعلان", "مش عاجبني", "معاملة سيئة", "complaint", "complain", "bad service",
]
GENERAL_CONVERSATION_KEYWORDS = [
    "احكيلي نكتة", "شو رايك", "مين انت", "كيف الطقس", "how are you", "what's up",
    "tell me a joke",
]
CONFIRM_KEYWORDS = [
    "نعم", "اكيد", "تأكيد", "موافق", "اوافق", "صحيح", "بالتاكيد", "طبعا",
    "تمام", "ايوه", "ايه", "اه", "يلا", "ماشي", "اعملها", "انضم", "ok", "okay",
    "yes", "confirm", "sure", "correct", "proceed",
]
CANCEL_KEYWORDS = [
    "لا", "لأ", "لا شكرا", "مش هسا", "مش الان", "الغاء", "الغي", "الغ الطلب",
    "لا اريد", "ما بدي", "ما ابغى", "مش عاوز", "خلاص لا", "رجوع", "ارجع", "وقف",
    "بس", "no", "cancel", "not now", "stop", "nevermind", "go back",
]
CANCEL_BOOKING_KEYWORDS = [
    "الغاء الحجز", "الغي حجزي", "اريد الغاء حجزي", "الغاء التذكرة", "بدي الغي الحجز",
    "cancel booking", "cancel reservation", "cancel my trip",
]


# Actionable requests intentionally outrank greetings/thanks in mixed messages.
INTENT_MAP = [
    ("cancel_booking", CANCEL_BOOKING_KEYWORDS),
    ("maintenance", MAINTENANCE_KEYWORDS),
    ("search_trip", SEARCH_TRIP_KEYWORDS),
    ("booking", BOOKING_KEYWORDS),
    ("complaint", COMPLAINT_KEYWORDS),
    ("ask_price", ASK_PRICE_KEYWORDS),
    ("ask_available_seats", ASK_SEATS_KEYWORDS),
    ("ask_companies", ASK_COMPANIES_KEYWORDS),
    ("help", HELP_KEYWORDS),
    ("goodbye", GOODBYE_KEYWORDS),
    ("thanks", THANKS_KEYWORDS),
    ("greeting", GREETING_KEYWORDS),
    ("general_conversation", GENERAL_CONVERSATION_KEYWORDS),
]


def classify(user_message: str) -> str:
    """Return the highest-priority deterministic intent or ``unknown``.

    Matching is phrase/token bounded. Confirmation and cancellation only
    qualify when the whole message is an acknowledgement, so they cannot
    accidentally authorize a side effect from an unrelated sentence.
    """
    msg = _normalize(user_message)
    if not msg:
        return "unknown"
    if _is_exact_signal(msg, CANCEL_KEYWORDS):
        return "cancel"
    if _is_exact_signal(msg, CONFIRM_KEYWORDS):
        return "confirm"
    for intent, keywords in INTENT_MAP:
        if _matches(msg, keywords):
            return intent
    # Controlled tolerance is limited to one-word entry requests. It can only
    # begin a flow; it is never used for a confirmation, cancellation, or write.
    if len(msg.split()) == 1:
        if _edit_distance_at_most_one(msg, "حجز") or _edit_distance_at_most_one(msg, "احجز"):
            return "booking"
        if _edit_distance_at_most_one(msg, "مرحبا") or msg == "مرحب":
            return "greeting"
    return "unknown"


def is_confirmation(user_message: str) -> bool:
    """True only for a standalone affirmative acknowledgement."""
    return _is_exact_signal(_normalize(user_message), CONFIRM_KEYWORDS)


def is_cancellation(user_message: str) -> bool:
    """True only for a standalone negative/decline acknowledgement."""
    return _is_exact_signal(_normalize(user_message), CANCEL_KEYWORDS)


def _normalize(text: str) -> str:
    return normalize_arabic(text or "")


def _matches(normalized_msg: str, keywords: list[str]) -> bool:
    return any(_contains_phrase(normalized_msg, _normalize(keyword)) for keyword in keywords if keyword)


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) is not None


def _is_exact_signal(normalized_msg: str, keywords: list[str]) -> bool:
    return any(normalized_msg == _normalize(keyword) for keyword in keywords if keyword)


def _edit_distance_at_most_one(left: str, right: str) -> bool:
    """Bounded Levenshtein for safe one-word tolerance."""
    if abs(len(left) - len(right)) > 1:
        return False
    if left == right:
        return True
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) <= 1
    if len(left) > len(right):
        left, right = right, left
    left_index = right_index = edits = 0
    while left_index < len(left) and right_index < len(right):
        if left[left_index] != right[right_index]:
            edits += 1
            right_index += 1
            if edits > 1:
                return False
        else:
            left_index += 1
            right_index += 1
    return True
