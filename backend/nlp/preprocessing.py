"""
backend/nlp/preprocessing.py — Arabic text preprocessing (Part Four).

Pure functions, no model/network dependency, so this stage always runs —
even if AraBERT/MARBERT are unavailable. Both the AI layer and the
existing rule-based layer benefit from a clean, normalized string.

Pipeline (see preprocess()):
    raw text
      -> strip control chars / excess whitespace
      -> normalize Hamza forms      (أ إ آ ؤ ئ ء -> ا/و/ي variants unified)
      -> normalize Alef forms       (أ إ آ -> ا)
      -> normalize Alef Maqsura     (ى -> ي)
      -> normalize Taa Marbuta      (optional, kept OFF by default — it
         changes word meaning in Arabic, unlike the other normalizations,
         so we only fold it when explicitly requested)
      -> remove Tashkeel (diacritics)
      -> remove Tatweel / elongation (ـــ, and repeated-letter stretching
         like "اهلااااا" -> "اهلا")
      -> normalize digits (Arabic-Indic + Extended Arabic-Indic -> Western)
      -> normalize punctuation (strip most, keep sentence-relevant ones)
      -> collapse whitespace

This module intentionally has ZERO knowledge of intents/entities/business
logic — it only cleans text. backend/intents.py's own lightweight
_normalize() is untouched (kept for the rule-based system's independence);
this module is the shared, fuller preprocessing used by the AI layer and
by entity_extractor.py.
"""

import re
import unicodedata

# ─── Character maps ─────────────────────────────────────────────────────────

_ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"           # U+0660–U+0669
_EXTENDED_ARABIC_INDIC_DIGITS = "۰۱۲۳۴۵۶۷۸۹"   # U+06F0–U+06F9 (Persian/Urdu forms seen in some dialects)
_WESTERN_DIGITS = "0123456789"

_DIGIT_TRANSLATION = str.maketrans(
    _ARABIC_INDIC_DIGITS + _EXTENDED_ARABIC_INDIC_DIGITS,
    _WESTERN_DIGITS + _WESTERN_DIGITS,
)

# Hamza / Alef family -> bare Alef. This intentionally mirrors
# backend/intents.py's _normalize() so both layers agree on the same
# canonical spelling, but is applied more broadly here (also covers
# hamza-on-waw/yaa and standalone hamza).
_ALEF_HAMZA_TRANSLATION = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ؤ": "و",
    "ئ": "ي",
    "ء": "",   # standalone hamza carries little matching value; drop it
})

_ALEF_MAQSURA_TRANSLATION = str.maketrans({"ى": "ي"})

# Arabic diacritics (Tashkeel) — Unicode combining marks U+064B–U+0652,
# plus Tatweel/Kashida (U+0640) used for word elongation.
_TASHKEEL_PATTERN = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]")
_TATWEEL_PATTERN = re.compile(r"\u0640+")

# Repeated-letter elongation common in informal Arabic chat, e.g.
# "هلاااا" -> "هلا", "يييي" -> "ي". Collapse any letter repeated 3+ times
# down to a single occurrence (2 is often legitimate, e.g. "مجلّة" already
# handled by tashkeel removal; Arabic rarely doubles a bare letter 3x+
# on purpose in normal text).
_ELONGATION_PATTERN = re.compile(r"(.)\1{2,}", re.UNICODE)

# Punctuation to strip entirely (keeps digits, Arabic/Latin letters, and
# whitespace). Question marks are kept since "؟"/"?" affects downstream
# intent cues in some setups; kept out here to stay conservative and match
# what intents.py already tolerates (it just substring-matches, so
# punctuation presence never broke it — we mainly want it gone for the
# embedding-based classifier which is punctuation-sensitive).
_PUNCTUATION_PATTERN = re.compile(
    r"[!\"#$%&'()*+,\-./:;<=>@\[\\\]^_`{|}~"
    r"،؛؟٪ـ«»…“”‘’]"
)

_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_digits(text: str) -> str:
    """Arabic-Indic and Extended Arabic-Indic digits -> Western digits."""
    return text.translate(_DIGIT_TRANSLATION)


def normalize_hamza_alef(text: str) -> str:
    """Fold all Hamza/Alef variants to their bare forms."""
    return text.translate(_ALEF_HAMZA_TRANSLATION)


def normalize_alef_maqsura(text: str) -> str:
    """Alef Maqsura (ى) -> Yaa (ي)."""
    return text.translate(_ALEF_MAQSURA_TRANSLATION)


def remove_tashkeel(text: str) -> str:
    """Strip Arabic diacritics (Fatha, Damma, Kasra, Shadda, Sukun, etc.)."""
    return _TASHKEEL_PATTERN.sub("", text)


def remove_elongation(text: str) -> str:
    """Collapse Tatweel (ـ) and stretched repeated letters ('هلاااا')."""
    text = _TATWEEL_PATTERN.sub("", text)
    return _ELONGATION_PATTERN.sub(r"\1", text)


def strip_punctuation(text: str) -> str:
    """Remove Arabic + Latin punctuation that adds no matching value."""
    return _PUNCTUATION_PATTERN.sub(" ", text)


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace (including newlines/tabs) to one space."""
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


def clean_control_chars(text: str) -> str:
    """Strip non-printable/control Unicode characters (e.g. from copy-paste)."""
    return "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in "\n\t ")


def normalize_arabic(text: str) -> str:
    """
    Full normalization pass used by the AI layer (AraBERT/MARBERT input)
    and by entity_extractor's gazetteer matching. Order matters: digits
    and hamza/alef must run before elongation collapsing, otherwise a
    legitimately-doubled letter created by folding hamza variants could
    be mis-collapsed.
    """
    if not text:
        return ""
    text = clean_control_chars(text)
    text = text.strip()
    text = normalize_digits(text)
    text = normalize_hamza_alef(text)
    text = normalize_alef_maqsura(text)
    text = remove_tashkeel(text)
    text = remove_elongation(text)
    text = strip_punctuation(text)
    text = normalize_whitespace(text)
    return text.lower()


def preprocess(text: str) -> dict:
    """
    Public entry point for the hybrid pipeline.

    Returns:
        {
            "raw": original text (unchanged, for logging/audit),
            "cleaned": whitespace/control-char cleaned, otherwise untouched
                       (kept for entity extraction where original casing/
                       punctuation of e.g. an email address matters),
            "normalized": fully normalized text (for AraBERT + rule-based
                       matching),
        }
    """
    text = text or ""
    cleaned = normalize_whitespace(clean_control_chars(text))
    normalized = normalize_arabic(text)
    return {"raw": text, "cleaned": cleaned, "normalized": normalized}
