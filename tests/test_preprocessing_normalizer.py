"""
tests/test_preprocessing_normalizer.py — Part Four/Part Two unit tests.

Runs with zero model dependency (pure functions), so these always run
regardless of whether transformers/torch/network access are available.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.nlp import preprocessing, normalizer


class TestPreprocessing:
    def test_normalize_digits_arabic_indic(self):
        assert preprocessing.normalize_digits("٢٠٢٥") == "2025"

    def test_normalize_digits_extended_arabic_indic(self):
        assert preprocessing.normalize_digits("۲۰۲۵") == "2025"

    def test_normalize_hamza_alef_variants(self):
        assert preprocessing.normalize_hamza_alef("أحمد") == "احمد"
        assert preprocessing.normalize_hamza_alef("إربد") == "اربد"
        assert preprocessing.normalize_hamza_alef("آمنة") == "امنة"

    def test_remove_tashkeel(self):
        assert preprocessing.remove_tashkeel("مَرْحَبًا") == "مرحبا"

    def test_remove_elongation(self):
        assert preprocessing.remove_elongation("هلاااااا") == "هلا"
        assert preprocessing.remove_elongation("ـــمرحباـــ") == "مرحبا"

    def test_normalize_arabic_full_pipeline_city_variants_collapse(self):
        # "عمّان" (with shadda) and "عمان" must normalize identically —
        # this is the core guarantee Part Two's city normalization relies on.
        assert preprocessing.normalize_arabic("عمّان") == preprocessing.normalize_arabic("عمان")

    def test_preprocess_returns_all_three_keys(self):
        result = preprocessing.preprocess("مرحبا  ")
        assert set(result.keys()) == {"raw", "cleaned", "normalized"}
        assert result["raw"] == "مرحبا  "

    def test_preprocess_empty_input_never_raises(self):
        result = preprocessing.preprocess("")
        assert result["normalized"] == ""
        result = preprocessing.preprocess(None)
        assert result["normalized"] == ""


class TestCityNormalization:
    def test_diacritic_variant(self):
        assert normalizer.normalize_city("عمّان") == "عمان"

    def test_english_alias(self):
        assert normalizer.normalize_city("Amman") == "عمان"
        assert normalizer.normalize_city("amman") == "عمان"

    def test_missing_hamza_variant(self):
        assert normalizer.normalize_city("اربد") == "إربد"

    def test_definite_article_variant(self):
        assert normalizer.normalize_city("زرقاء") == "الزرقاء"
        assert normalizer.normalize_city("الزرقاء") == "الزرقاء"

    def test_unknown_city_returns_none(self):
        assert normalizer.normalize_city("باريس") is None

    def test_find_cities_in_text_order_preserved(self):
        cities = normalizer.find_cities_in_text("من عمان الى اربد")
        assert cities == ["عمان", "إربد"]

    def test_find_cities_deduplicates(self):
        cities = normalizer.find_cities_in_text("عمان جميلة، احب عمان")
        assert cities == ["عمان"]


class TestNumberParsing:
    def test_arabic_indic_digit(self):
        assert normalizer.parse_number("٢") == 2

    def test_western_digit(self):
        assert normalizer.parse_number("2") == 2

    def test_arabic_word(self):
        assert normalizer.parse_number("اثنين") == 2
        assert normalizer.parse_number("ثلاثة") == 3

    def test_no_number_returns_none(self):
        assert normalizer.parse_number("مرحبا") is None

    def test_empty_returns_none(self):
        assert normalizer.parse_number("") is None


class TestTripClassParsing:
    def test_economy_variants(self):
        assert normalizer.parse_trip_class("اقتصادي") == "economy"
        assert normalizer.parse_trip_class("economy") == "economy"

    def test_business_variants(self):
        assert normalizer.parse_trip_class("اعمال") == "business"
        assert normalizer.parse_trip_class("بيزنس") == "business"

    def test_vip(self):
        assert normalizer.parse_trip_class("vip") == "vip"

    def test_no_match(self):
        assert normalizer.parse_trip_class("لا أعرف") is None


class TestServiceTypeParsing:
    def test_oil_change(self):
        assert normalizer.parse_service_type("تغيير زيت") == "oil_change"

    def test_tire_repair(self):
        assert normalizer.parse_service_type("بنشر") == "tire_repair"

    def test_no_match(self):
        assert normalizer.parse_service_type("شيء غريب تماما") is None


class TestPhoneEmailExtraction:
    def test_extract_email(self):
        assert normalizer.extract_email("راسلني على test@example.com من فضلك") == "test@example.com"

    def test_extract_email_none(self):
        assert normalizer.extract_email("لا يوجد بريد هنا") is None

    def test_extract_phone(self):
        phone = normalizer.extract_phone("رقمي 0791234567")
        assert phone is not None
        assert "0791234567" in phone.replace(" ", "")

    def test_extract_phone_arabic_indic_digits(self):
        phone = normalizer.extract_phone("٠٧٩١٢٣٤٥٦٧")
        assert phone is not None


class TestDateTimeExtraction:
    def test_explicit_date(self):
        assert normalizer.extract_date("موعدي 2025-08-01 بالضبط") == "2025-08-01"

    def test_relative_date_tomorrow(self):
        assert normalizer.extract_date("بدي احجز بكرا") == "tomorrow"

    def test_relative_date_today(self):
        assert normalizer.extract_date("اليوم لو سمحت") == "today"

    def test_no_date_returns_none(self):
        assert normalizer.extract_date("مرحبا كيفك") is None

    def test_extract_time(self):
        assert normalizer.extract_time("الساعة 14:30 تماما") == "14:30"
