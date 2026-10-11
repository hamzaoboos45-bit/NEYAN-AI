"""
backend/responses.py — Bilingual response templates.

Keeps all user-facing text in one place so translations,
tone changes, and A/B testing are trivially easy.
"""

RESPONSES = {
    # ─── Greetings ───────────────────────────────────────
    "greeting": "أهلًا! كيف أقدر أساعدك اليوم؟ أقدر أساعدك في حجز رحلة أو طلب صيانة.",
    "greeting_short": "أهلًا! نكمل من حيث توقفنا — أجب على السؤال الأخير عندما تكون جاهزًا.",
    "thanks": "على الرحب والسعة!",
    "help": (
        "أقدر أساعدك في البحث عن الرحلات وحجزها، وطلبات الرحلات قيد الاكتمال، وطلب الصيانة. "
        "اكتب ما تحتاجه بطريقتك."
    ),
    "unknown": "ممكن توضّح لي أكثر؟ أقدر أساعدك في الرحلات والحجوزات والصيانة.",

    # ─── Global escape / small-talk responses ─────────────
    # (bug fix: these keys were already referenced by chatbot.py's
    # _check_global_escape / _handle_idle but never defined in this dict —
    # responses.get() silently fell back to "unknown" for all of them.)
    "help_mid_flow": (
        "لا مشكلة، إليك المساعدة:\n"
        "• للمتابعة، أجب على سؤالي الأخير.\n"
        "• اكتب 'إلغاء' للخروج من هذه الخطوة في أي وقت."
    ),
    "flow_cancelled":  "تم إلغاء العملية الحالية. كيف يمكنني مساعدتك؟",
    "cancel_booking":  "لإلغاء حجز موجود، يرجى تزويدي برقم الحجز أو التواصل مع خدمة العملاء.",
    "confirm_nothing": "لا يوجد طلب معلّق لتأكيده حالياً. هل تريد حجز رحلة أم طلب صيانة؟",
    "cancel_nothing":  "لا يوجد طلب معلّق لإلغائه حالياً. هل تريد حجز رحلة أم طلب صيانة؟",
    "ask_price_first": "يسعدني إخبارك بالسعر — من أي مدينة وإلى أي مدينة؟",
    "ask_seats_first": "يسعدني التحقق من المقاعد المتاحة — من أي مدينة وإلى أي مدينة؟",
    "no_trips_found":  "عذراً، لا توجد رحلات متاحة تطابق هذا الطلب حالياً.",

    # ─── New intents (Arabic NLP Intelligence phase) ──────
    # Purely additive — "complaint" and "general_conversation" are new
    # canonical intents from the AraBERT layer that the rule-based system
    # never had labels for. No existing intent/response was touched.
    "complaint_ack": (
        "يؤسفني سماع ذلك، وأعتذر عن أي إزعاج. 🙏\n"
        "هل يمكنك وصف المشكلة بمزيد من التفاصيل حتى أقوم بتوثيقها ومتابعتها؟"
    ),
    "general_chat": "حسناً 🙂 يمكنني مساعدتك في حجز رحلة أو طلب صيانة — فقط أخبرني بما تحتاج.",

    # ─── Booking flow prompts ─────────────────────────────
    "booking_start":    "ممتاز! لنبدأ حجز رحلتك. 🚌\nمن أي مدينة ستسافر؟",
    "booking_to":       "شكراً. وإلى أي مدينة تريد الوصول؟",
    "booking_date":     "ما هو تاريخ سفرك؟ (مثال: 2025-06-15)",
    "invalid_date":     "لم أفهم التاريخ. استخدم مثلاً 2025-06-15 أو اكتب بكرا.",
    "invalid_travel_date": "التاريخ غير صحيح. من فضلك أدخل تاريخاً صالحاً للرحلة.",
    "past_travel_date": "هذا التاريخ مضى أو ليس تاريخاً مستقبلياً. من فضلك اختر تاريخاً قادماً للرحلة.",
    "invalid_travel_date_en": "That date is invalid. Please enter a valid travel date.",
    "past_travel_date_en": "That date has already passed. Please choose a future travel date.",
    "booking_seats":    "كم عدد المقاعد المطلوبة؟",
    "invalid_seats":    "لم أفهم عدد المقاعد. الرجاء إدخال رقم (مثال: 2).",
    "booking_class": (
        "ما هي درجة الرحلة المطلوبة؟\n"
        "1. اقتصادي\n"
        "2. أعمال\n"
        "3. VIP"
    ),
    "invalid_class":    "لم أفهم درجة الرحلة. الرجاء الاختيار: اقتصادي / أعمال / VIP.",
    "booking_company":  "إليك الرحلات المتاحة المطابقة لطلبك، اختر الرقم المناسب:\n\n{companies}",
    "invalid_company":  "لم أتعرف على هذا الاختيار. الرجاء اختيار رقم من القائمة:\n\n{companies}",
    "booking_confirm":  (
        "✅ ملخص حجزك:\n"
        "من: {from_city}\n"
        "إلى: {to_city}\n"
        "التاريخ: {date}\n"
        "المقاعد: {seats}\n"
        "الدرجة: {trip_class}\n"
        "الشركة: {company}\n"
        "السعر: سعر المقعد الحالي {unit_price} د.أ\n"
        "الإجمالي الحالي لعدد المقاعد: {total_price} د.أ\n"
        "سيعيد الخادم التحقق من السعر عند التأكيد.\n"
        "هل تريد تأكيد الحجز؟ (نعم / لا)"
    ),
    "booking_done":     "✅ تم تأكيد حجزك بنجاح! رقم الحجز: #{booking_id}\nالمبلغ النهائي المحفوظ: {total_price} د.أ",
    "booking_cancelled": "تم إلغاء الحجز. هل تريد البدء من جديد؟",
    "booking_confirm_repeat": "هل تريد تأكيد الحجز؟ أجب بنعم أو لا.",
    "booking_owner_required": "تعذر تأكيد الحجز لأن جلسة المستخدم غير صالحة. يرجى تسجيل الدخول ثم المحاولة.",

    # ─── Maintenance flow prompts ─────────────────────────
    "maint_start": (
        "سأساعدك في طلب الصيانة. 🔧\n"
        "ما نوع الخدمة المطلوبة؟\n"
        "1. تصليح إطارات\n"
        "2. تبديل إطارات\n"
        "3. صيانة محرك\n"
        "4. تغيير زيت\n"
        "5. صيانة بطارية"
    ),
    "invalid_service_type": "لم أفهم نوع خدمة الصيانة. اختر إحدى الخدمات المعروضة.",
    "maint_details":  "صِف المشكلة بمزيد من التفاصيل:",
    "maint_location": "ما هو موقعك أو عنوانك؟",
    "maint_date":     "ما هو التاريخ المفضل لك للخدمة؟ (مثال: 2025-06-15)",
    "maint_confirm":  (
        "✅ ملخص طلب الصيانة:\n"
        "الخدمة: {service_type}\n"
        "التفاصيل: {details}\n"
        "الموقع: {location}\n"
        "التاريخ: {date}\n"
        "هل تريد تأكيد الطلب؟ (نعم / لا)"
    ),
    "maint_done": "✅ تم استلام طلب الصيانة! رقم الطلب: #{request_id}",
    "maint_cancelled": "تم إلغاء طلب الصيانة. هل تريد البدء من جديد؟",
    "maint_confirm_repeat": "هل تريد تأكيد طلب الصيانة؟ أجب بنعم أو لا.",
    "maintenance_owner_required": "تعذر إرسال طلب الصيانة لأن جلسة المستخدم غير صالحة. يرجى تسجيل الدخول ثم المحاولة.",
}


def get(key: str, **kwargs) -> str:
    """
    Retrieve a response template and format it with kwargs.

    Example:
        get("booking_confirm", from_city="عمان", to_city="إربد",
            date="2025-06-01", seats=2)
    """
    template = RESPONSES.get(key, RESPONSES["unknown"])
    try:
        return template.format(**kwargs)
    except KeyError:
        return template
