# V2 development challenge audit for V3

## Decision


## Summary

- AMBIGUOUS: 26
- CONTEXT_DEPENDENT: 33
- CONTRADICTORY: 1
- UNNATURAL_SYNTHETIC: 90

This 150-row set is retained as a **development diagnostic only**. It must not be relabelled silently, trained on, used for V3 hyperparameter selection, or presented as the final unbiased benchmark. The row-level audit below records why.

Status meanings: `VALID` = plausible standalone label; `AMBIGUOUS` = more than one plausible intent; `CONTRADICTORY` = target conflicts with text; `CONTEXT_DEPENDENT` = server conversation state is required; `UNNATURAL_SYNTHETIC` = generated filler makes the sentence implausible or distorts intent.

| # | Intent | Status | Text | Reason |
|---:|---|---|---|---|
| 1 | `availability_inquiry` | **AMBIGUOUS** | من عمان لإربد: في سعة فاضية؟ شو بتنصح؟ | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 2 | `availability_inquiry` | **UNNATURAL_SYNTHETIC** | Irbid to Amman: الرحلة مليانة ولا؟ بدي أعرف قبل القرار. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 3 | `availability_inquiry` | **CONTEXT_DEPENDENT** | من معان للطفيلة: باقي أماكن؟ هل بتقدر توضح؟ | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 4 | `availability_inquiry` | **UNNATURAL_SYNTHETIC** | من الزرقاء للعقبة: can two people fit؟ هذا استفساري الوحيد. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 5 | `availability_inquiry` | **AMBIGUOUS** | من البلقاء للعاصمة: كم متاح؟ يعني كيف؟ | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 6 | `availability_inquiry` | **UNNATURAL_SYNTHETIC** | من عجلون للمفرق: في سعة فاضية؟ بكلمات بسيطة. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 7 | `availability_inquiry` | **UNNATURAL_SYNTHETIC** | من جرش للسلط: الرحلة مليانة ولا؟ بدون ما أعمل طلب الآن. | Injected suffix ‘بدون ما أعمل طلب الآن.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 8 | `availability_inquiry` | **UNNATURAL_SYNTHETIC** | من الرمثا للبحر الميت: باقي أماكن؟ وأنا بانتظار الرد. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 9 | `availability_inquiry` | **UNNATURAL_SYNTHETIC** | Amman to Aqaba: can two people fit؟ إذا كانت الخدمة متاحة. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 10 | `availability_inquiry` | **UNNATURAL_SYNTHETIC** | من مادبا للكرك: كم متاح؟ للتخطيط للمشوار. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 11 | `book_trip` | **AMBIGUOUS** | من عمان لإربد: حابّة أثبت مقعد؟ شو بتنصح؟ | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 12 | `book_trip` | **UNNATURAL_SYNTHETIC** | Irbid to Amman: بدي أوفر إلي كرسي؟ بدي أعرف قبل القرار. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 13 | `book_trip` | **CONTEXT_DEPENDENT** | من معان للطفيلة: رتبلي سفرة؟ هل بتقدر توضح؟ | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 14 | `book_trip` | **UNNATURAL_SYNTHETIC** | من الزرقاء للعقبة: can you book me؟ هذا استفساري الوحيد. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 15 | `book_trip` | **AMBIGUOUS** | من البلقاء للعاصمة: أريد إصدار تذكرة؟ يعني كيف؟ | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 16 | `book_trip` | **UNNATURAL_SYNTHETIC** | من عجلون للمفرق: حابّة أثبت مقعد؟ بكلمات بسيطة. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 17 | `book_trip` | **CONTRADICTORY** | من جرش للسلط: بدي أوفر إلي كرسي؟ بدون ما أعمل طلب الآن. | The suffix explicitly denies creating a request while the target label requests reservation. |
| 18 | `book_trip` | **UNNATURAL_SYNTHETIC** | من الرمثا للبحر الميت: رتبلي سفرة؟ وأنا بانتظار الرد. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 19 | `book_trip` | **UNNATURAL_SYNTHETIC** | Amman to Aqaba: can you book me؟ إذا كانت الخدمة متاحة. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 20 | `book_trip` | **UNNATURAL_SYNTHETIC** | من مادبا للكرك: أريد إصدار تذكرة؟ للتخطيط للمشوار. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 21 | `cancel_booking` | **AMBIGUOUS** | شو بتنصح؟ شيل الحجز باسمي، بكرا. | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 22 | `cancel_booking` | **UNNATURAL_SYNTHETIC** | بدي أعرف قبل القرار. ما بدي تذكرتي، المساء. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 23 | `cancel_booking` | **CONTEXT_DEPENDENT** | هل بتقدر توضح؟ أرجع الحجز، بكرا. | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 24 | `cancel_booking` | **UNNATURAL_SYNTHETIC** | هذا استفساري الوحيد. withdraw my booked seat، المساء. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 25 | `cancel_booking` | **AMBIGUOUS** | يعني كيف؟ إلغاء سفرتي، بكرا. | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 26 | `cancel_booking` | **UNNATURAL_SYNTHETIC** | بكلمات بسيطة. شيل الحجز باسمي، المساء. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 27 | `cancel_booking` | **UNNATURAL_SYNTHETIC** | بدون ما أعمل طلب الآن. ما بدي تذكرتي، بكرا. | Injected suffix ‘بدون ما أعمل طلب الآن.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 28 | `cancel_booking` | **UNNATURAL_SYNTHETIC** | وأنا بانتظار الرد. أرجع الحجز، المساء. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 29 | `cancel_booking` | **UNNATURAL_SYNTHETIC** | إذا كانت الخدمة متاحة. withdraw my booked seat، بكرا. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 30 | `cancel_booking` | **UNNATURAL_SYNTHETIC** | للتخطيط للمشوار. إلغاء سفرتي، المساء. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 31 | `cancellation` | **CONTEXT_DEPENDENT** | مش مناسب إلي — شو بتنصح؟ | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 32 | `cancellation` | **CONTEXT_DEPENDENT** | خليها لوقت ثاني — بدي أعرف قبل القرار. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 33 | `cancellation` | **CONTEXT_DEPENDENT** | لا تثبت شيء — هل بتقدر توضح؟ | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 34 | `cancellation` | **CONTEXT_DEPENDENT** | abort this — هذا استفساري الوحيد. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 35 | `cancellation` | **CONTEXT_DEPENDENT** | تراجع — يعني كيف؟ | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 36 | `cancellation` | **CONTEXT_DEPENDENT** | مش مناسب إلي — بكلمات بسيطة. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 37 | `cancellation` | **CONTEXT_DEPENDENT** | خليها لوقت ثاني — بدون ما أعمل طلب الآن. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 38 | `cancellation` | **CONTEXT_DEPENDENT** | لا تثبت شيء — وأنا بانتظار الرد. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 39 | `cancellation` | **CONTEXT_DEPENDENT** | abort this — إذا كانت الخدمة متاحة. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 40 | `cancellation` | **CONTEXT_DEPENDENT** | تراجع — للتخطيط للمشوار. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 41 | `company_information` | **AMBIGUOUS** | شو بتنصح؟ من المشغّل لهذه الوجهة، بكرا. | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 42 | `company_information` | **UNNATURAL_SYNTHETIC** | بدي أعرف قبل القرار. أي ناقل متوفر، المساء. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 43 | `company_information` | **CONTEXT_DEPENDENT** | هل بتقدر توضح؟ وين ألاقي جهات النقل، بكرا. | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 44 | `company_information` | **UNNATURAL_SYNTHETIC** | هذا استفساري الوحيد. company list please، المساء. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 45 | `company_information` | **AMBIGUOUS** | يعني كيف؟ شركات الباصات، بكرا. | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 46 | `company_information` | **UNNATURAL_SYNTHETIC** | بكلمات بسيطة. من المشغّل لهذه الوجهة، المساء. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 47 | `company_information` | **UNNATURAL_SYNTHETIC** | بدون ما أعمل طلب الآن. أي ناقل متوفر، بكرا. | Injected suffix ‘بدون ما أعمل طلب الآن.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 48 | `company_information` | **UNNATURAL_SYNTHETIC** | وأنا بانتظار الرد. وين ألاقي جهات النقل، المساء. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 49 | `company_information` | **UNNATURAL_SYNTHETIC** | إذا كانت الخدمة متاحة. company list please، بكرا. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 50 | `company_information` | **UNNATURAL_SYNTHETIC** | للتخطيط للمشوار. شركات الباصات، المساء. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 51 | `complaint` | **AMBIGUOUS** | شو بتنصح؟ التجربة ما كانت عادلة، بكرا. | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 52 | `complaint` | **UNNATURAL_SYNTHETIC** | بدي أعرف قبل القرار. في اعتراض على الرحلة، المساء. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 53 | `complaint` | **CONTEXT_DEPENDENT** | هل بتقدر توضح؟ الالتزام بالمواعيد سيء، بكرا. | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 54 | `complaint` | **UNNATURAL_SYNTHETIC** | هذا استفساري الوحيد. service quality disappointed me، المساء. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 55 | `complaint` | **AMBIGUOUS** | يعني كيف؟ السائق ما احترمنا، بكرا. | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 56 | `complaint` | **UNNATURAL_SYNTHETIC** | بكلمات بسيطة. التجربة ما كانت عادلة، المساء. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 57 | `complaint` | **UNNATURAL_SYNTHETIC** | بدون ما أعمل طلب الآن. في اعتراض على الرحلة، بكرا. | Injected suffix ‘بدون ما أعمل طلب الآن.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 58 | `complaint` | **UNNATURAL_SYNTHETIC** | وأنا بانتظار الرد. الالتزام بالمواعيد سيء، المساء. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 59 | `complaint` | **UNNATURAL_SYNTHETIC** | إذا كانت الخدمة متاحة. service quality disappointed me، بكرا. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 60 | `complaint` | **UNNATURAL_SYNTHETIC** | للتخطيط للمشوار. السائق ما احترمنا، المساء. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 61 | `confirmation` | **CONTEXT_DEPENDENT** | ثبّت الطلب — شو بتنصح؟ | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 62 | `confirmation` | **CONTEXT_DEPENDENT** | توكلنا — بدي أعرف قبل القرار. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 63 | `confirmation` | **CONTEXT_DEPENDENT** | تابع — هل بتقدر توضح؟ | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 64 | `confirmation` | **CONTEXT_DEPENDENT** | confirmed — هذا استفساري الوحيد. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 65 | `confirmation` | **CONTEXT_DEPENDENT** | اختياري نعم — يعني كيف؟ | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 66 | `confirmation` | **CONTEXT_DEPENDENT** | ثبّت الطلب — بكلمات بسيطة. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 67 | `confirmation` | **CONTEXT_DEPENDENT** | توكلنا — بدون ما أعمل طلب الآن. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 68 | `confirmation` | **CONTEXT_DEPENDENT** | تابع — وأنا بانتظار الرد. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 69 | `confirmation` | **CONTEXT_DEPENDENT** | confirmed — إذا كانت الخدمة متاحة. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 70 | `confirmation` | **CONTEXT_DEPENDENT** | اختياري نعم — للتخطيط للمشوار. | Standalone accept/decline requires an active server confirmation state; it is not a reliable standalone intent label. |
| 71 | `general_conversation` | **AMBIGUOUS** | شو جديدك — شو بتنصح؟ | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 72 | `general_conversation` | **UNNATURAL_SYNTHETIC** | كيف الجو عندك — بدي أعرف قبل القرار. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 73 | `general_conversation` | **CONTEXT_DEPENDENT** | خلينا نحكي — هل بتقدر توضح؟ | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 74 | `general_conversation` | **UNNATURAL_SYNTHETIC** | are you well — هذا استفساري الوحيد. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 75 | `general_conversation` | **AMBIGUOUS** | قلي معلومة — يعني كيف؟ | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 76 | `general_conversation` | **UNNATURAL_SYNTHETIC** | شو جديدك — بكلمات بسيطة. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 77 | `general_conversation` | **UNNATURAL_SYNTHETIC** | كيف الجو عندك — بدون ما أعمل طلب الآن. | Injected suffix ‘بدون ما أعمل طلب الآن.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 78 | `general_conversation` | **UNNATURAL_SYNTHETIC** | خلينا نحكي — وأنا بانتظار الرد. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 79 | `general_conversation` | **UNNATURAL_SYNTHETIC** | are you well — إذا كانت الخدمة متاحة. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 80 | `general_conversation` | **UNNATURAL_SYNTHETIC** | قلي معلومة — للتخطيط للمشوار. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 81 | `goodbye` | **AMBIGUOUS** | خلص شكراً — شو بتنصح؟ | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 82 | `goodbye` | **UNNATURAL_SYNTHETIC** | نهارك سعيد — بدي أعرف قبل القرار. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 83 | `goodbye` | **CONTEXT_DEPENDENT** | باي باي — هل بتقدر توضح؟ | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 84 | `goodbye` | **UNNATURAL_SYNTHETIC** | talk later — هذا استفساري الوحيد. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 85 | `goodbye` | **AMBIGUOUS** | وداعاً — يعني كيف؟ | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 86 | `goodbye` | **UNNATURAL_SYNTHETIC** | خلص شكراً — بكلمات بسيطة. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 87 | `goodbye` | **UNNATURAL_SYNTHETIC** | نهارك سعيد — بدون ما أعمل طلب الآن. | Injected suffix ‘بدون ما أعمل طلب الآن.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 88 | `goodbye` | **UNNATURAL_SYNTHETIC** | باي باي — وأنا بانتظار الرد. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 89 | `goodbye` | **UNNATURAL_SYNTHETIC** | talk later — إذا كانت الخدمة متاحة. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 90 | `goodbye` | **UNNATURAL_SYNTHETIC** | وداعاً — للتخطيط للمشوار. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 91 | `greeting` | **AMBIGUOUS** | يا هلا — شو بتنصح؟ | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 92 | `greeting` | **UNNATURAL_SYNTHETIC** | يسعد صباحك — بدي أعرف قبل القرار. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 93 | `greeting` | **CONTEXT_DEPENDENT** | أهلين — هل بتقدر توضح؟ | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 94 | `greeting` | **UNNATURAL_SYNTHETIC** | hey there — هذا استفساري الوحيد. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 95 | `greeting` | **AMBIGUOUS** | السلام عليكم — يعني كيف؟ | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 96 | `greeting` | **UNNATURAL_SYNTHETIC** | يا هلا — بكلمات بسيطة. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 97 | `greeting` | **UNNATURAL_SYNTHETIC** | يسعد صباحك — بدون ما أعمل طلب الآن. | Injected suffix ‘بدون ما أعمل طلب الآن.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 98 | `greeting` | **UNNATURAL_SYNTHETIC** | أهلين — وأنا بانتظار الرد. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 99 | `greeting` | **UNNATURAL_SYNTHETIC** | hey there — إذا كانت الخدمة متاحة. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 100 | `greeting` | **UNNATURAL_SYNTHETIC** | السلام عليكم — للتخطيط للمشوار. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 101 | `help` | **AMBIGUOUS** | شو بتنصح؟ وضحلي شو أعمل، بكرا. | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 102 | `help` | **UNNATURAL_SYNTHETIC** | بدي أعرف قبل القرار. بدّي مساعدة عامة، المساء. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 103 | `help` | **CONTEXT_DEPENDENT** | هل بتقدر توضح؟ دليل الحجز وين، بكرا. | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 104 | `help` | **UNNATURAL_SYNTHETIC** | هذا استفساري الوحيد. what can NEYAN do، المساء. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 105 | `help` | **AMBIGUOUS** | يعني كيف؟ مش عارف أبدأ، بكرا. | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 106 | `help` | **UNNATURAL_SYNTHETIC** | بكلمات بسيطة. وضحلي شو أعمل، المساء. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 107 | `help` | **UNNATURAL_SYNTHETIC** | بدون ما أعمل طلب الآن. بدّي مساعدة عامة، بكرا. | Injected suffix ‘بدون ما أعمل طلب الآن.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 108 | `help` | **UNNATURAL_SYNTHETIC** | وأنا بانتظار الرد. دليل الحجز وين، المساء. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 109 | `help` | **UNNATURAL_SYNTHETIC** | إذا كانت الخدمة متاحة. what can NEYAN do، بكرا. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 110 | `help` | **UNNATURAL_SYNTHETIC** | للتخطيط للمشوار. مش عارف أبدأ، المساء. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 111 | `maintenance_request` | **AMBIGUOUS** | شو بتنصح؟ فرامل السيارة مش طبيعية، بكرا. | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 112 | `maintenance_request` | **UNNATURAL_SYNTHETIC** | بدي أعرف قبل القرار. المكيف خربان بالباص، المساء. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 113 | `maintenance_request` | **CONTEXT_DEPENDENT** | هل بتقدر توضح؟ بدّي فحص للإطارات، بكرا. | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 114 | `maintenance_request` | **UNNATURAL_SYNTHETIC** | هذا استفساري الوحيد. engine warning appeared، المساء. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 115 | `maintenance_request` | **AMBIGUOUS** | يعني كيف؟ المركبة ما بتدور، بكرا. | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 116 | `maintenance_request` | **UNNATURAL_SYNTHETIC** | بكلمات بسيطة. فرامل السيارة مش طبيعية، المساء. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 117 | `maintenance_request` | **UNNATURAL_SYNTHETIC** | بدون ما أعمل طلب الآن. المكيف خربان بالباص، بكرا. | Injected suffix ‘بدون ما أعمل طلب الآن.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 118 | `maintenance_request` | **UNNATURAL_SYNTHETIC** | وأنا بانتظار الرد. بدّي فحص للإطارات، المساء. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 119 | `maintenance_request` | **UNNATURAL_SYNTHETIC** | إذا كانت الخدمة متاحة. engine warning appeared، بكرا. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 120 | `maintenance_request` | **UNNATURAL_SYNTHETIC** | للتخطيط للمشوار. المركبة ما بتدور، المساء. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 121 | `price_inquiry` | **AMBIGUOUS** | من عمان لإربد: قديش بدفع؟ شو بتنصح؟ | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 122 | `price_inquiry` | **UNNATURAL_SYNTHETIC** | Irbid to Amman: شو الكلفة النهائية؟ بدي أعرف قبل القرار. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 123 | `price_inquiry` | **CONTEXT_DEPENDENT** | من معان للطفيلة: السعر شامل شو؟ هل بتقدر توضح؟ | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 124 | `price_inquiry` | **UNNATURAL_SYNTHETIC** | من الزرقاء للعقبة: ticket cost please؟ هذا استفساري الوحيد. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 125 | `price_inquiry` | **AMBIGUOUS** | من البلقاء للعاصمة: بكم المشوار؟ يعني كيف؟ | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 126 | `price_inquiry` | **UNNATURAL_SYNTHETIC** | من عجلون للمفرق: قديش بدفع؟ بكلمات بسيطة. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 127 | `price_inquiry` | **UNNATURAL_SYNTHETIC** | من جرش للسلط: شو الكلفة النهائية؟ بدون ما أعمل طلب الآن. | Injected suffix ‘بدون ما أعمل طلب الآن.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 128 | `price_inquiry` | **UNNATURAL_SYNTHETIC** | من الرمثا للبحر الميت: السعر شامل شو؟ وأنا بانتظار الرد. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 129 | `price_inquiry` | **UNNATURAL_SYNTHETIC** | Amman to Aqaba: ticket cost please؟ إذا كانت الخدمة متاحة. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 130 | `price_inquiry` | **UNNATURAL_SYNTHETIC** | من مادبا للكرك: بكم المشوار؟ للتخطيط للمشوار. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 131 | `trip_information` | **AMBIGUOUS** | من عمان لإربد: وين نقطة التجمع؟ شو بتنصح؟ | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 132 | `trip_information` | **UNNATURAL_SYNTHETIC** | Irbid to Amman: على أي ساعة الوصول؟ بدي أعرف قبل القرار. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 133 | `trip_information` | **CONTEXT_DEPENDENT** | من معان للطفيلة: ما خط السير؟ هل بتقدر توضح؟ | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 134 | `trip_information` | **UNNATURAL_SYNTHETIC** | من الزرقاء للعقبة: is it direct؟ هذا استفساري الوحيد. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 135 | `trip_information` | **AMBIGUOUS** | من البلقاء للعاصمة: تفاصيل المغادرة؟ يعني كيف؟ | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 136 | `trip_information` | **UNNATURAL_SYNTHETIC** | من عجلون للمفرق: وين نقطة التجمع؟ بكلمات بسيطة. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 137 | `trip_information` | **UNNATURAL_SYNTHETIC** | من جرش للسلط: على أي ساعة الوصول؟ بدون ما أعمل طلب الآن. | Injected suffix ‘بدون ما أعمل طلب الآن.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 138 | `trip_information` | **UNNATURAL_SYNTHETIC** | من الرمثا للبحر الميت: ما خط السير؟ وأنا بانتظار الرد. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 139 | `trip_information` | **UNNATURAL_SYNTHETIC** | Amman to Aqaba: is it direct؟ إذا كانت الخدمة متاحة. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 140 | `trip_information` | **UNNATURAL_SYNTHETIC** | من مادبا للكرك: تفاصيل المغادرة؟ للتخطيط للمشوار. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 141 | `trip_search` | **AMBIGUOUS** | من عمان لإربد: في شي طالع؟ شو بتنصح؟ | Injected suffix ‘شو بتنصح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 142 | `trip_search` | **UNNATURAL_SYNTHETIC** | Irbid to Amman: بدي أتصفح رحلات؟ بدي أعرف قبل القرار. | Injected suffix ‘بدي أعرف قبل القرار.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 143 | `trip_search` | **CONTEXT_DEPENDENT** | من معان للطفيلة: ما الخيارات المتجهة؟ هل بتقدر توضح؟ | Injected suffix ‘هل بتقدر توضح؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 144 | `trip_search` | **UNNATURAL_SYNTHETIC** | من الزرقاء للعقبة: browse departures؟ هذا استفساري الوحيد. | Injected suffix ‘هذا استفساري الوحيد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 145 | `trip_search` | **AMBIGUOUS** | من البلقاء للعاصمة: هل في مواصلات؟ يعني كيف؟ | Injected suffix ‘يعني كيف؟’ is not required by the target intent and changes or obscures the natural user meaning. |
| 146 | `trip_search` | **UNNATURAL_SYNTHETIC** | من عجلون للمفرق: في شي طالع؟ بكلمات بسيطة. | Injected suffix ‘بكلمات بسيطة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 147 | `trip_search` | **UNNATURAL_SYNTHETIC** | من جرش للسلط: بدي أتصفح رحلات؟ بدون ما أعمل طلب الآن. | Injected suffix ‘بدون ما أعمل طلب الآن.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 148 | `trip_search` | **UNNATURAL_SYNTHETIC** | من الرمثا للبحر الميت: ما الخيارات المتجهة؟ وأنا بانتظار الرد. | Injected suffix ‘وأنا بانتظار الرد.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 149 | `trip_search` | **UNNATURAL_SYNTHETIC** | Amman to Aqaba: browse departures؟ إذا كانت الخدمة متاحة. | Injected suffix ‘إذا كانت الخدمة متاحة.’ is not required by the target intent and changes or obscures the natural user meaning. |
| 150 | `trip_search` | **UNNATURAL_SYNTHETIC** | من مادبا للكرك: هل في مواصلات؟ للتخطيط للمشوار. | Injected suffix ‘للتخطيط للمشوار.’ is not required by the target intent and changes or obscures the natural user meaning. |
