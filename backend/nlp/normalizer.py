"""
backend/nlp/normalizer.py — Entity value normalization (Part Two continued).

Turns a raw extracted span ("عمّان", "عمان", "Amman", "٢", "اثنين") into the
canonical value the REST of the app already expects.

Important design decision: cities are canonicalized to the SAME Arabic
strings already used in config.SUPPORTED_CITIES and stored in the `trips`
table (e.g. "عمان", not "Amman"). This is deliberate — booking search in
chatbot.py does `WHERE from_city=? AND to_city=?` against those exact
Arabic values, so normalizing to anything else (like the English name used
in this project's own spec example) would silently break trip lookup.
English/alias input is still accepted and mapped IN, it's just mapped back
OUT to the Arabic form the database understands.

This module has no model/network dependency and is reused by:
    - backend/nlp/entity_extractor.py (the NER layer)
    - backend/chatbot.py (refactored _parse_number / _parse_trip_class now
      delegate here instead of keeping their own copies — "never duplicate
      existing code")
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import config
from backend.nlp.preprocessing import normalize_arabic

# ═══════════════════════════════════════════════════════════════════════════
# CITY NORMALIZATION
# ═══════════════════════════════════════════════════════════════════════════

# Only aliases live here. Canonical identities, display labels, and storage
# values are declared once in config.JORDAN_GOVERNORATES.
_GOVERNORATE_ALIASES = {
    "amman": ("العاصمة", "طبربور", "تبربور", "tabarbour"),
    "irbid": ("اربد",),
    "zarqa": ("زرقاء", "الزرقا", "زرقا"),
    # Salt remains a safe historical input alias for Balqa, not a second
    # governorate identity.
    "balqa": ("بلقاء", "السلط", "سلط", "salt", "as-salt"),
    "mafraq": ("مفرق",),
    "jerash": ("جرَش",),
    "madaba": ("مأدبا",),
    "karak": ("كرك",),
    "tafilah": ("طفيلة", "الطفيله", "طفيله"),
    "maan": ("ma'an", "maan"),
    "aqaba": ("عقبة", "العقبه", "عقبه"),
}

_CITY_ALIAS_RAW = {
    governorate["storage"]: [
        governorate["storage"], governorate["ar"], governorate["en"], governorate["key"],
        *_GOVERNORATE_ALIASES.get(governorate["key"], ()),
    ]
    for governorate in config.JORDAN_GOVERNORATES
}

# Build a normalized-alias -> canonical lookup once at import time.
# Keys are run through the same normalize_arabic() used on user input, so
# diacritics/hamza/tatweel variants collapse automatically and don't need
# to be listed by hand.
_CITY_LOOKUP: dict[str, str] = {}
for _canonical, _aliases in _CITY_ALIAS_RAW.items():
    assert _canonical in config.SUPPORTED_CITIES, (
        f"normalizer.py city '{_canonical}' is missing from "
        f"config.SUPPORTED_CITIES — keep these in sync."
    )
    for _alias in _aliases + [_canonical]:
        _CITY_LOOKUP[normalize_arabic(_alias)] = _canonical
        # Also index the alias with the Arabic definite article ("ال")
        # stripped/added, since "الزرقاء" and "زرقاء" are the same city.
        _norm_alias = normalize_arabic(_alias)
        if _norm_alias.startswith("ال") and len(_norm_alias) > 2:
            _CITY_LOOKUP[_norm_alias[2:]] = _canonical
        else:
            _CITY_LOOKUP["ال" + _norm_alias] = _canonical


def normalize_city(text: str) -> str | None:
    """
    Map any known spelling/alias of a supported city to its canonical
    Arabic name (matching config.SUPPORTED_CITIES / the `trips` table).
    Returns None if the text doesn't match any known city.
    """
    if not text:
        return None
    return _CITY_LOOKUP.get(normalize_arabic(text))


def find_cities_in_text(text: str) -> list[str]:
    """
    Scan free-form text for every city mention (in the order they appear),
    returning canonical Arabic names. Used by entity_extractor for
    sentences like 'من عمان الى اربد' that mention multiple cities at once.
    """
    if not text:
        return []
    normalized = normalize_arabic(text)
    found = []
    # Sort candidate aliases by length (desc) so multi-word aliases like
    # "الزرقاء" are matched before any shorter accidental substring.
    for alias_norm in sorted(_CITY_LOOKUP.keys(), key=len, reverse=True):
        if not alias_norm:
            continue
        for match in re.finditer(rf"(?<![\w]){re.escape(alias_norm)}(?![\w])", normalized):
            found.append((match.start(), _CITY_LOOKUP[alias_norm]))
    # De-duplicate while preserving left-to-right order of first mention.
    seen = set()
    ordered = []
    for _pos, city in sorted(found, key=lambda x: x[0]):
        if city not in seen:
            seen.add(city)
            ordered.append(city)
    return ordered


# ═══════════════════════════════════════════════════════════════════════════
# NUMBERS (digits + Arabic number words)
# ═══════════════════════════════════════════════════════════════════════════

_NUMBER_WORDS = {
    "واحد": 1, "احد": 1, "اثنين": 2, "اتنين": 2, "ثنين": 2,
    "ثلاثة": 3, "تلاتة": 3, "ثلاث": 3,
    "اربعة": 4, "اربع": 4, "خمسة": 5, "خمس": 5,
    "ستة": 6, "ست": 6, "سبعة": 7, "سبع": 7,
    "ثمانية": 8, "تمانية": 8, "ثمان": 8,
    "تسعة": 9, "تسع": 9, "عشرة": 10, "عشر": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def parse_number(text: str) -> int | None:
    """
    Extract an integer from user input — Arabic-Indic digits, Western
    digits, or Arabic/English number words. Returns None if not parseable.

    This is the single canonical implementation; backend/chatbot.py's
    _parse_number() now delegates here instead of keeping its own copy.
    """
    if not text:
        return None
    normalized = normalize_arabic(text)  # folds Arabic-Indic digits too
    for word, val in _NUMBER_WORDS.items():
        if normalize_arabic(word) in normalized:
            return val
    digits = re.search(r"\d+", normalized)
    if digits:
        try:
            return int(digits.group())
        except ValueError:
            return None
    return None


# ═══════════════════════════════════════════════════════════════════════════
# TRIP CLASS
# ═══════════════════════════════════════════════════════════════════════════

_TRIP_CLASS_WORDS = {
    "economy":  ["اقتصادي", "اقتصاديه", "عادي", "economy", "الاول", "1"],
    "business": ["اعمال", "بيزنس", "business", "2"],
    "vip":      ["vip", "في اي بي", "فاخر", "3"],
}
assert set(_TRIP_CLASS_WORDS) <= set(config.TRIP_CLASSES)


def parse_trip_class(text: str) -> str | None:
    """Map free text to 'economy' / 'business' / 'vip'. None if no match.
    Canonical implementation — backend/chatbot.py's _parse_trip_class()
    now delegates here."""
    if not text:
        return None
    normalized = normalize_arabic(text)
    for key, words in _TRIP_CLASS_WORDS.items():
        for word in words:
            normalized_word = normalize_arabic(word)
            # Numeric menu choices are valid only as the whole reply. A
            # substring match would classify dates such as 2025-07-01 as
            # economy merely because they contain the digit "1".
            if normalized_word.isdigit():
                if normalized == normalized_word:
                    return key
            elif normalized_word in normalized:
                return key
    return None


# ═══════════════════════════════════════════════════════════════════════════
# MAINTENANCE SERVICE TYPE
# ═══════════════════════════════════════════════════════════════════════════

_SERVICE_TYPE_WORDS = {
    "tire_repair":  ["تصليح اطار", "تصليح اطارات", "بنشر", "تصليح كوشوك"],
    "tire_replace": ["تبديل اطار", "تبديل اطارات", "تغيير اطار", "تغيير كوشوك", "كاوتش"],
    "oil_change":   ["تغيير زيت", "زيت المحرك", "زيت"],
    "battery":      ["بطارية", "كهرباء البطارية"],
    "engine":       ["محرك", "موتور", "عطل محرك"],
}
assert set(_SERVICE_TYPE_WORDS) <= set(config.MAINTENANCE_SERVICES)


def parse_service_type(text: str) -> str | None:
    """Map free text describing a maintenance need to a canonical
    service_type key from config.MAINTENANCE_SERVICES. None if no match
    (a genuinely novel complaint should fall through to 'other')."""
    if not text:
        return None
    normalized = normalize_arabic(text)
    for key, words in _SERVICE_TYPE_WORDS.items():
        if any(normalize_arabic(w) in normalized for w in words):
            return key
    return None


# ═══════════════════════════════════════════════════════════════════════════
# VEHICLE TYPE
# ═══════════════════════════════════════════════════════════════════════════

_VEHICLE_TYPE_WORDS = {
    "bus": ["باص", "حافلة", "bus"],
    "car": ["سيارة", "عربية", "car"],
    "van": ["فان", "van", "ميكروباص"],
}
assert set(_VEHICLE_TYPE_WORDS) <= set(config.VEHICLE_TYPES)


def parse_vehicle_type(text: str) -> str | None:
    if not text:
        return None
    normalized = normalize_arabic(text)
    for key, words in _VEHICLE_TYPE_WORDS.items():
        if any(normalize_arabic(w) in normalized for w in words):
            return key
    return None


# ═══════════════════════════════════════════════════════════════════════════
# CONTACT INFO — phone / email
# ═══════════════════════════════════════════════════════════════════════════

# Jordanian mobile numbers (+962 7X XXXXXXX) and generic 8-15 digit phone
# numbers, so the pattern is useful beyond just Jordan.
_PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:0\d{1,2}[\s-]?)?\d{7,10}")
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def extract_phone(text: str) -> str | None:
    if not text:
        return None
    # Normalize digits only (keep '+' and spacing) so Arabic-Indic phone
    # numbers are recognized too.
    from backend.nlp.preprocessing import normalize_digits
    candidate_text = normalize_digits(text)
    match = _PHONE_PATTERN.search(candidate_text)
    if not match:
        return None
    digits_only = re.sub(r"\D", "", match.group())
    if len(digits_only) < 7:
        return None
    return match.group().strip()


def extract_email(text: str) -> str | None:
    if not text:
        return None
    match = _EMAIL_PATTERN.search(text)
    return match.group() if match else None


# ═══════════════════════════════════════════════════════════════════════════
# DATE / TIME (lightweight — pattern based, no external date library)
# ═══════════════════════════════════════════════════════════════════════════

_DATE_PATTERN = re.compile(
    r"\b(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{2,4})\b"
)
_TIME_PATTERN = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_HOUR_CUE_PATTERN = re.compile(r"(?:الساعة|الساعه|at)\s*([01]?\d|2[0-3])\b", re.IGNORECASE)

_RELATIVE_DATE_WORDS = {
    "اليوم": "today", "بكرا": "tomorrow", "غدا": "tomorrow", "غداً": "tomorrow",
    "بعد بكرا": "day_after_tomorrow", "بعد غد": "day_after_tomorrow",
}


def extract_date(text: str) -> str | None:
    """Returns an explicit date string if found (YYYY-MM-DD etc.), or a
    normalized relative-date keyword ('today' / 'tomorrow' /
    'day_after_tomorrow') for common colloquial phrasing. None otherwise —
    callers should keep asking rather than guess."""
    if not text:
        return None
    from backend.nlp.preprocessing import normalize_digits
    match = _DATE_PATTERN.search(normalize_digits(text))
    if match:
        return match.group()
    normalized = normalize_arabic(text)
    for word, key in _RELATIVE_DATE_WORDS.items():
        if normalize_arabic(word) in normalized:
            return key
    return None


@dataclass(frozen=True)
class TravelDate:
    status: str
    value: str | None = None


def classify_future_travel_date(text: str | None, *, today: date | None = None) -> TravelDate:
    """Classify supported travel text without guessing or silently changing it."""
    from backend.nlp.preprocessing import normalize_digits

    # ``extract_date`` returns these canonical tokens and entity extraction
    # can persist them between turns.  Accept the stored representation too;
    # otherwise a valid "tomorrow" entity would be mistaken for missing when
    # a later booking step validates the restored context.
    value = (text or "").strip()
    raw = value if value in {"today", "tomorrow", "day_after_tomorrow"} else extract_date(value)
    if not raw:
        return TravelDate("missing")
    current = today or date.today()
    if raw in {"today", "tomorrow", "day_after_tomorrow"}:
        candidate = current + {"today": timedelta(), "tomorrow": timedelta(days=1), "day_after_tomorrow": timedelta(days=2)}[raw]
    else:
        candidate_text = normalize_digits(raw)
        try:
            if "-" in candidate_text and len(candidate_text.split("-", 1)[0]) == 4:
                candidate = date.fromisoformat(candidate_text)
            else:
                separator = "/" if "/" in candidate_text else "-"
                day, month, year = candidate_text.split(separator)
                candidate = datetime.strptime(f"{int(day):02d}/{int(month):02d}/{year}", "%d/%m/%Y" if len(year) == 4 else "%d/%m/%y").date()
        except (TypeError, ValueError):
            return TravelDate("invalid")
    if candidate <= current:
        return TravelDate("past")
    return TravelDate("valid", candidate.isoformat())


def extract_time(text: str) -> str | None:
    if not text:
        return None
    from backend.nlp.preprocessing import normalize_digits
    match = _TIME_PATTERN.search(normalize_digits(text))
    if match:
        return match.group()
    hour_match = _HOUR_CUE_PATTERN.search(normalize_digits(text))
    if hour_match:
        return f"{int(hour_match.group(1)):02d}:00"
    return None
