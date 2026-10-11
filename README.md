# منصة النقل الذكية — AI-Based Arabic Transportation Platform

مشروع تخرج: نظام دعم عملاء ذكي لخدمات النقل

---

## هيكل المشروع

```
transport_platform/
├── app.py                          # نقطة تشغيل التطبيق
├── config.py                       # الإعدادات المركزية
├── requirements.txt
│
├── backend/
│   ├── chatbot.py                  # محرك المحادثة (state machine)
│   ├── states.py                   # تعريف حالات المحادثة
│   ├── intents.py                  # كشف النية (rule-based)
│   ├── responses.py                # قوالب الردود
│   └── ai/
│       └── arabert_placeholder.py  # هيكل الذكاء الاصطناعي المستقبلي
│
├── database/
│   ├── db.py                       # اتصال SQLite
│   ├── init_db.py                  # Schema + بيانات تجريبية
│   └── transport.db                # قاعدة البيانات (تُنشأ تلقائياً)
│
├── routes/
│   ├── chat_routes.py              # /api/chat
│   ├── booking_routes.py           # /trips, /bookings
│   ├── maintenance_routes.py       # /maintenance
│   └── admin_routes.py             # /admin, /api/analytics
│
└── frontend/
    ├── templates/
    │   ├── base.html               # الهيكل العام + Sidebar
    │   ├── chat.html
    │   ├── trips.html
    │   ├── bookings.html
    │   ├── maintenance.html
    │   └── admin.html
    └── static/
        ├── css/main.css
        └── js/
            ├── chat.js
            └── admin.js
```

---

## تشغيل المشروع

### Windows / PowerShell / PyCharm: مسار تشغيل إداري رسمي

نفّذ الأوامر التالية من **جذر المشروع** (`transport_platform`). لا يتطلب هذا
المسار أي تعديل يدوي لقاعدة SQLite أو لحقول الدور أو كلمة المرور.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

في PyCharm اختر المفسّر `.venv\Scripts\python.exe` ثم نفّذ الأوامر نفسها من
نافذة Terminal. تقوم أوامر التطبيق أدناه بتهيئة قاعدة البيانات إذا كانت جديدة؛
ولا تحذف قاعدة بيانات قائمة أو بياناتها.

### إنشاء أول مدير عام (مرة واحدة فقط)

لا توجد بيانات دخول إدارية افتراضية. بعد إعداد قاعدة بيانات جديدة، ينفّذ
المشغّل الموثوق هذا الأمر محلياً من جذر المشروع:

```bash
python scripts/bootstrap_super_admin.py --name "Platform Owner" --email owner@example.com
```

سيُطلب منك إدخال كلمة المرور مرتين من دون طباعتها. يرفض الأمر إنشاء حساب
إضافي أو تغيير كلمة مرور مدير عام صالح موجود. لا يوجد مسار HTTP عام لهذه
العملية.

### استعادة وصول مدير قائم محلياً

لا توجد نقطة HTTP عامة لإعادة تعيين مدير المنصة. من جهاز موثوق، يمكن تحديد
بريد المدير العام المفعّل فقط ثم إعادة تعيين كلمة مروره دون SQL يدوي أو طباعة
أي كلمة مرور:

```bash
python scripts/manage_super_admin.py --list
python scripts/manage_super_admin.py --reset-password --email owner@example.com
```

الأمر الثاني يطلب كلمة المرور الجديدة مرتين بشكل مخفي ويلغي جلسات “Remember
Me” لذلك المدير. استخدم `--password-stdin` فقط من مدير أسرار موثوق؛ لا تمرر
كلمة المرور كوسيط في سطر الأوامر.

في قاعدة بيانات قائمة: إذا وُجد حساب Super Admin حقيقي (`role=admin` ومن دون
`company_id`) فإن bootstrap يرفض بأمان ولا يغيّر الحساب أو ينشئ حساب منصة
ثانياً. استخدم أمر الإدارة أعلاه للاستعلام عن الحسابات المفعّلة أو لإعادة تعيين
كلمة مرور حساب منصة معروف. إعادة التعيين لا تعيد تنشيط حساب معطّل ولا تغيّر
دوره أو نطاق شركته؛ تبقى حالة الحساب تحت مسار الإدارة الموثوق.

### تشغيل الخادم بعد الإعداد

```powershell
python app.py
```

ثم افتح `http://127.0.0.1:5000/login` وسجّل الدخول ببريد المدير الذي أدخله
المشغّل وكلمة المرور التي اختارها. الحساب الإداري الأول لا يملك `company_id`
لذلك يصل إلى نطاق المنصة؛ أما Company Admin فينشئه Super Admin من واجهة الإدارة
ويرتبط بشركته على الخادم.

### فتح المتصفح
```
http://localhost:5000
```

---

## الصفحات المتاحة

| الصفحة | الرابط | الوصف |
|--------|--------|-------|
| المحادثة | `/chat` | الشات بوت الذكي |
| الرحلات | `/trips` | البحث عن رحلات |
| الحجوزات | `/bookings` | قائمة الحجوزات |
| الصيانة | `/maintenance` | طلب خدمة صيانة |
| الإدارة | `/admin` | لوحة التحليلات |

---

## API Endpoints

| Endpoint | Method | الوصف |
|----------|--------|-------|
| `/api/chat` | POST | إرسال رسالة للبوت |
| `/api/chat/reset` | POST | إعادة تشغيل المحادثة |
| `/api/trips` | GET | البحث عن رحلات |
| `/api/bookings` | GET | قائمة الحجوزات |
| `/api/maintenance/requests` | GET/POST | طلبات الصيانة |
| `/api/analytics/summary` | GET | ملخص الإحصائيات |
| `/api/analytics/bookings-per-company` | GET | حجوزات حسب شركة |
| `/api/analytics/maintenance-per-company` | GET | صيانة حسب شركة |

---

## مراحل التطوير المستقبلية

- [ ] تكامل AraBERT لتحسين كشف النية
- [ ] تكامل MARBERT لاستخراج الكيانات (مدن، تواريخ)
- [x] تكامل Whisper للتعرف على الصوت العربي (Version 3 — انظر أدناه)
- [x] نظام تسجيل دخول المستخدمين
- [ ] إشعارات البريد الإلكتروني
- [ ] لوحة تحكم الشركات

---

## Version 3 — المساعد الصوتي (Voice Assistant)

يضيف صفحة `/chat` القدرة على التحدث مع البوت بدلاً من الكتابة فقط، مع رد
صوتي (TTS) اختياري، دون أي تعديل على منطق البوت الحالي (`backend/chatbot.py`).

### التثبيت

```bash
pip install -r requirements.txt

# نظام التشغيل يحتاج أيضاً:
#   Ubuntu/Debian:  sudo apt-get install ffmpeg espeak-ng
#   macOS:          brew install ffmpeg
#   Windows:        نزّل ffmpeg وأضِفه إلى PATH
```

عند أول تشغيل، Whisper سيقوم بتنزيل نموذج "base" تلقائياً (يحتاج اتصال
بالإنترنت لمرة واحدة فقط، ثم يُخزَّن محلياً ويُعاد استخدامه من دون إعادة تحميل).

### المعمارية

```
backend/speech/
    whisper_engine.py   نموذج Whisper — يُحمَّل مرة واحدة عند إقلاع السيرفر
    tts_engine.py        محرك pyttsx3 للنطق (يعمل بدون إنترنت)
    vad.py               كشف الصمت/الكلام لرفض التسجيلات الفارغة
    audio_utils.py        التحقق من الملفات، الحفظ المؤقت، والحذف الآمن
    recorder.py           يربط الخطوات الأربع السابقة في خط أنابيب واحد

routes/voice_routes.py    POST /api/voice · POST /api/tts · التاريخ والإعدادات
database/voice_db.py      قراءة/كتابة voice_history و voice_settings
frontend/static/js/voice.js   التسجيل، الموجة الصوتية، المراجعة، الإعدادات
frontend/static/css/voice.css زجاجية (glassmorphism) + رسوم متحركة + وضع داكن
```

### API

| Endpoint | Method | الوصف |
|----------|--------|-------|
| `/api/voice` | POST | رفع/تسجيل صوت → نص (Whisper) |
| `/api/tts` | POST | تحويل نص إلى صوت (pyttsx3) |
| `/api/voice/voices` | GET | قائمة الأصوات المتاحة على الجهاز |
| `/api/voice/settings` | GET/POST | إعدادات المستخدم الصوتية |
| `/api/voice/history` | GET | سجل التسجيلات السابقة |
| `/api/voice/history/<id>/audio` | GET | إعادة تشغيل تسجيل سابق |
| `/api/voice/history/<id>` | DELETE | حذف تسجيل من السجل |

### ملاحظة مهمة

لم يتم اختبار هذا الكود فعلياً بتشغيله (بيئة التطوير التي أنشأته لا تملك
اتصال إنترنت لتثبيت `openai-whisper`/`pyttsx3` أو تنزيل نموذج Whisper).
تم فحص كل شيء آخر (بنية Flask، الاستيراد، قاعدة البيانات، حالات الأخطاء،
تنظيف الملفات المؤقتة) عبر اختبارات آلية فعلية. يُرجى تشغيل
`pip install -r requirements.txt` ثم تجربة التسجيل الصوتي فعلياً والتبليغ
عن أي خلل في مكتبة `pyttsx3` الخاصة بنظام تشغيلك (جودة الصوت العربي تعتمد
على الأصوات المثبتة في نظامك).

---

## إعداد البريد واستعادة كلمة المرور

يحمّل التطبيق ملف `.env` المحلي من جذر المشروع قبل قراءة الإعدادات؛ متغيرات
بيئة نظام التشغيل لها أولوية عليه. انسخ `.env.example` إلى `.env` خارج التحكم
بالمصادر، واختر مزوّدًا واحدًا (`smtp` أو `sendgrid`). عند استخدام Gmail يجب
استخدام **Gmail App Password** بعد تفعيل التحقق بخطوتين، وليس كلمة مرور الحساب.

يدعم SMTP وضعين صريحين: `SMTP_SECURITY=starttls` مع المنفذ 587 (EHLO ثم
STARTTLS)، أو `SMTP_SECURITY=ssl` مع المنفذ 465 للـ implicit TLS/SMTPS. لا
تغيّر المنفذ إلى 465 مع ترك `starttls`: اختر `ssl` أيضًا. مثال شبكة تحجب 587:

```env
EMAIL_PROVIDER=smtp
SMTP_HOST=smtp.gmail.com
SMTP_PORT=465
SMTP_SECURITY=ssl
SMTP_USERNAME=your-address@gmail.com
SMTP_PASSWORD=<gmail-app-password>
EMAIL_FROM=your-address@gmail.com
```

لا يطبع التطبيق روابط الاستعادة أو الرموز في السجل. وضع `console` مخصص للتطوير
فقط، ولا تُعرض وصلة إعادة التعيين في الإنتاج مهما كان مزوّد البريد غير مكتمل.
يمكن للمشغّل فحص وجود الإعدادات من دون كشف قيمها:

```powershell
python scripts/check_email_delivery.py
# اختياري، بعد إكمال الإعدادات فقط؛ يرسل رسالة اختبار غير مرتبطة بحساب:
python scripts/check_email_delivery.py --send-test-to operator@example.com
```

## الإدخال الصوتي المتقدم

يستخدم زر الميكروفون `SpeechRecognition` في المتصفح أولاً. عند تعطل خدمة
المتصفح بسبب خطأ شبكة فقط، يسجل العميل مقاطع متتابعة ويعرض نصًا جزئيًا داخل
حقل المحادثة الحالي كل 2.5 ثانية افتراضيًا، ثم يجري تحويلًا نهائيًا واحدًا
ويرسله مرة واحدة عبر مسار Chat المعتاد. التحويل المرحلي مؤقت: لا ينشئ حجزًا أو
رحلة أو سجل صوت. يمكن ضبط `VOICE_PARTIAL_INTERVAL_MS` (حد أدنى 1500) و
`VOICE_CLIENT_MAX_RECORDING_SECONDS` من البيئة.

المسار البديل يحتاج `openai-whisper` و`ffmpeg` ونموذج Whisper محليًا؛ النموذج
والتسجيلات التشغيلية لا تدخل في حزمة التسليم. لا يُعد الإدخال الصوتي الفعلي
متحققًا على جهاز جديد حتى يتم اختبار الميكروفون والنموذج عليه.

---

## Project Two — Phase One (Authentication · RBAC · AI Memory Manager)

يضيف هذا الإصدار طبقة إنتاجية كاملة فوق الكود القائم (V1 + V2 + V3) دون
حذف أو إعادة تصميم أي شيء — كل شيء أدناه إضافي (additive) ومتوافق للخلف.

### 1) نظام المصادقة (Authentication)

- تسجيل دخول/خروج، تجزئة كلمات المرور (bcrypt) — كما كان.
- **Remember Me**: كوكي منفصل بنمط selector/verifier (`backend/security/remember_me.py`)
  يُعيد تسجيل الدخول تلقائياً لمدة 30 يوماً، ويُدار (rotate) في كل استخدام.
- **Forgot / Reset Password**: `/forgot-password` و `/reset-password/<token>`
  (`backend/security/password_reset.py`). لا يوجد مزوّد بريد إلكتروني مُفعّل
  بعد، لذا يظهر رابط إعادة التعيين مباشرة على الصفحة تحت عنوان "Development
  mode" — لتفعيل الإرسال الحقيقي لاحقاً يكفي استبدال تلك السطر بإرسال بريد،
  دون تغيير في التوكنات نفسها.
- **CSRF Protection**: توكن واحد لكل جلسة (`backend/security/csrf.py`)، يُتحقق
  منه تلقائياً على كل POST/PUT/PATCH/DELETE. النماذج تحمله كحقل مخفي، وطلبات
  fetch تحمله تلقائياً عبر `frontend/static/js/csrf.js` (لم يلزم تعديل كل
  ملفات JS الموجودة يدوياً).
- **Brute-Force Protection**: `backend/security/brute_force.py` — 5 محاولات
  فاشلة لنفس البريد أو 20 لنفس الـ IP خلال 15 دقيقة يوقف الدخول مؤقتاً.
- **Secure Cookies**: `HttpOnly` + `SameSite=Lax` دائماً، و `Secure` عند تفعيل
  `FORCE_SECURE_COOKIES=1` (بعد تشغيل الموقع خلف HTTPS).

### 2) الصلاحيات (Role-Based Access Control)

ثلاثة أدوار منفصلة تماماً: **super_admin**، **company_admin**، **customer**.
لا تعديل على جدول `users` — يُشتق الدور الفعلي من العمودين الموجودين
(`role`, `company_id`) في `routes/auth_helpers.py::effective_role()`.
Decorators جاهزة: `@super_admin_required`, `@company_admin_required`,
`@customer_required`, و `@roles_required(...)` العامة تحتها جميعاً — لا تكرار
لمنطق الصلاحيات في أي ملف.

- **customer**: حجز رحلات، محادثة، طلبات صيانة، سجل خاص به فقط.
- **company_admin**: يرى فقط رحلات/حجوزات/صيانة/تحليلات شركته
  (`/admin`، `/api/analytics/summary`، `/api/analytics/my-trips`، إلخ)،
  ويمكنه تحديث حالة حجوزات وطلبات صيانة شركته فقط (403 لأي شركة أخرى).
- **super_admin**: كل شيء — إدارة المستخدمين، الموافقة على حسابات الشركات
  الجديدة، سجل النشاط، مقارنات بين الشركات.

### 3) ذاكرة المساعد الذكي (AI Assistant Memory)

`backend/memory/` — طبقة جديدة توثّق وتُنظّم الذاكرة التي كان
`backend/chatbot.py` يديرها ضمنياً، دون تغيير أي منطق محادثة:

```
Conversation → Intent → Entities → Context Memory → Chatbot
                              session_context.py (typed entities)
                              conversation_memory.py (DB persistence)
                              memory_manager.py (public API + auto-expire)
```

- الذاكرة تنجو عبر عدة رسائل (كما كانت)، ويمكن تصفيرها (`/api/chat/reset`).
- **جديد**: انتهاء صلاحية تلقائي — إن تجاوزت آخر رسالة `SESSION_TIMEOUT_MINUTES`
  (افتراضياً 30 دقيقة، من `config.py`) تُصفَّر المحادثة تلقائياً بدل تفسير
  رسالة جديدة كإجابة على سؤال قديم.

### 4) تكامل الصوت (Integration)

لا تغيير مطلوب — `frontend/static/js/voice.js` كان يمرر النص المُفرَّغ عبر
نفس `sendMessage()` المستخدم للكتابة، أي عبر نفس مسار `/api/chat` بالضبط.
تم التحقق من ذلك ولم يُكتشف أي منطق مكرر.

### 5) قاعدة البيانات

جداول جديدة فقط (لا تعديل على الجداول القديمة): `login_attempts`،
`password_resets`، `remember_tokens`. راجع `database/init_db.py`.

### متغيرات البيئة (محلية)

| المتغير | الوصف |
|---|---|
| `FLASK_SECRET_KEY` | مطلوب في الإنتاج. في بيئة التطوير فقط يولّد التطبيق مفتاحاً عشوائياً معزولاً عند غيابه. |
| `FORCE_SECURE_COOKIES` | اضبطه على `1` بعد تشغيل الموقع خلف HTTPS. |
| `NGROK_AUTH_TOKEN` | اختياري — لتفعيل نفق ngrok العام عند التشغيل المباشر (`python app.py`). |

### حسابات الإدارة

لا تتضمن البيانات التجريبية أي حساب مدير أو كلمة مرور إدارية معروفة. أنشئ
أول مدير عام عبر أمر bootstrap أعلاه، ثم استخدم لوحة الإدارة لإنشاء مديري
الشركات عند الحاجة.

### ملاحظة أمنية مهمة

كان مفتاح Flask السري (`app.secret_key`) ورمز مصادقة ngrok مكتوبَين مباشرة
في `app.py` بنص صريح في النسخة السابقة — تم نقلهما إلى متغيرات بيئة
(`FLASK_SECRET_KEY`, `NGROK_AUTH_TOKEN`) لأن أي شخص يطّلع على الكود المصدري
كان يستطيع تزوير جلسات المستخدمين. **يُنصح بإبطال (revoke) رمز ngrok القديم**
إن كان لا يزال هذا المستودع أو نسخة سابقة منه متاحة لأي طرف آخر.

---

# Production / Deployment Readiness

## What production requires

Neyan AI is verified with **Python 3.10.11**. Production uses the same
repository and `requirements.txt`, but it must run with a WSGI server rather
than `python app.py`. The portable documented server is Waitress; Gunicorn may
also serve `wsgi:app` on Linux if an operator chooses it.

A production host must provide:

- a Python web-service runtime and the declared dependencies;
- persistent, writable storage for SQLite and voice uploads;
- HTTPS termination, environment-secret management, and a configurable start
  command;
- enough memory/CPU for the selected NLP/voice runtime. Exact sizing has not
  been measured; Whisper and optional Transformer models are the major
  consumers.

SQLite is appropriate for a graduation demo or controlled low-write deployment.
It is a single persistent file and serializes writes, so it is not a substitute
for a multi-writer database at scale. Do not deploy it on an ephemeral
filesystem; mount persistent storage and plan backups.

## Environment contract

Copy `.env.example` as an operator reference only; do **not** commit a real
`.env`. In `APP_ENV=production`, startup fails closed unless the following are
configured safely:

| Variable | Production purpose |
|---|---|
| `APP_ENV=production` | Enables production validation and disables debug. |
| `FLASK_SECRET_KEY` (or `SECRET_KEY`) | A secret of at least 32 non-default characters. Never print or commit it. |
| `DATABASE_PATH` | Absolute path to the persistent SQLite file. |
| `UPLOAD_DIR` | Absolute writable persistent path for voice runtime files. |
| `SESSION_COOKIE_SECURE=1` | Required when HTTPS is used (and required by production validation). |
| `TRUSTED_PROXY_COUNT` | `0` unless a known reverse proxy is in front; set the exact number, e.g. `1`. |
| `HOST`, `PORT`, `LOG_LEVEL` | Optional server bind and log controls. |
| `ENABLE_AI_NLP` | Set to `0` for the rule-based fallback, or prepare model weights/cache before setting `1`. |
| `TRAINED_CHAT_MODEL_VERSION` | `v1` by default. Set to `v2` only after the local V2 artifact, independent evaluation, and regression gates pass; an invalid/missing V2 safely falls back. |

Production does not trust forwarded headers unless `TRUSTED_PROXY_COUNT` is
explicitly configured. The hosting proxy remains responsible for normal host
validation and HTTPS termination. No permissive CORS layer is added because
the frontend and backend are same-origin. CSRF, chat rate limiting, and request
serialization remain enabled.

### PowerShell example

```powershell
$env:APP_ENV="production"
$env:FLASK_SECRET_KEY="<generate-and-store-a-strong-random-secret>"
$env:DATABASE_PATH="D:\neyan-data\transport.db"
$env:UPLOAD_DIR="D:\neyan-data\uploads"
$env:SESSION_COOKIE_SECURE="1"
$env:TRUSTED_PROXY_COUNT="1"
waitress-serve --listen=0.0.0.0:5000 wsgi:app
```

### Generic Linux example

```bash
export APP_ENV=production
export FLASK_SECRET_KEY='<generate-and-store-a-strong-random-secret>'
export DATABASE_PATH=/srv/neyan-ai/data/transport.db
export UPLOAD_DIR=/srv/neyan-ai/uploads
export SESSION_COOKIE_SECURE=1
export TRUSTED_PROXY_COUNT=1
waitress-serve --listen=0.0.0.0:5000 wsgi:app
```

The configured database and upload parents are created at startup when their
filesystem permissions permit it; permission errors intentionally stop startup.
The database initialization is idempotent and never resets an existing database.
The official trusted-shell bootstrap and reset scripts import the same
environment-driven configuration, so they operate on the same database as the
web app:

```bash
python scripts/bootstrap_super_admin.py --name "Platform Owner" --email owner@example.com
python scripts/manage_super_admin.py --list
python scripts/manage_super_admin.py --reset-password --email owner@example.com
```

There is no HTTP bootstrap endpoint. Email delivery remains optional: if a real
mail provider is not configured, do not treat console/reset-link development
behavior as production delivery; use trusted-shell administrator recovery.

## Startup, health, and HTTPS

Production order:

1. Install `requirements.txt` and any required system dependency such as
   `ffmpeg` for server-side audio handling.
2. Configure the environment and persistent directories.
3. Start the WSGI server; it initializes a new schema safely if needed.
4. Bootstrap the first Super Admin from a trusted shell only.
5. Verify `GET /health` returns HTTP 200 with `{"status":"ok"}`.
6. Perform an authenticated operator smoke test.

`/health` verifies the process and a minimal SQLite connection; it does not
prove every business workflow. Production must run behind HTTPS. Secure cookies
and browser voice recognition both depend on that context in normal browsers.
Logs go to the hosting process/platform; configure retention there. Application
logging avoids passwords, hashes, cookies, CSRF tokens, secret keys, and raw
sensitive request bodies.

## Backup and restore

For SQLite, either stop the application before copying the database or use
SQLite's supported backup mechanism; do not rely on copying a file mid-write.
Store backups outside the runtime volume and test restoration periodically.

To restore: stop the application, preserve the failed database for forensics,
replace the configured persistent database with the chosen backup using trusted
operator action, start the WSGI service, check `/health`, then verify an admin
login. Restoration is intentionally not automated by the application.

## Deployment checklist (for the later actual-deployment phase)

- [ ] HTTPS active and `SESSION_COOKIE_SECURE=1`
- [ ] `/health` returns 200
- [ ] SQLite and uploads are on persistent storage with a tested backup
- [ ] Super Admin and customer login work
- [ ] Dashboard, Transportation, Booking, Forming Trips, Maintenance, Reviews,
  Notifications, Admin pricing, Arabic/English, and Dark/Light work
- [ ] Mobile layout is checked
- [ ] Voice microphone behavior is checked in a supported HTTPS browser

Voice browser/microphone behavior is not guaranteed by server startup alone:
it requires browser SpeechRecognition support, a secure context, and a real
device test after actual deployment. Optional AraBERT/MARBERT models load at
startup when enabled and may download/cache weights on first use; prepare/cache
them during deployment if the host cannot access Hugging Face. Failure falls
back to rule-based chat. Whisper similarly degrades to a clear unavailable
response when its package/model or `ffmpeg` is unavailable.

### Voice latency configuration

Browser `SpeechRecognition` remains the primary low-latency path and updates
the existing chat composer with interim text. The authenticated transient STT
fallback uses `VOICE_PARTIAL_INTERVAL_MS=2000` by default, coalesces at most
one in-flight partial request, and performs one authoritative final
transcription before the normal Chat sender runs once. `VOICE_STT_ENGINE`
defaults to `whisper`; an operator may explicitly select `faster-whisper`
with `WHISPER_DEVICE=cpu` and `WHISPER_COMPUTE_TYPE=int8` only after validating
the optional runtime dependency and transcript quality on their deployment
machine. Downloaded model caches are runtime-only and are never release assets.

## Jordan governorate route contract

Governorate-level transportation routes and transport-pricing policies use one
ordered canonical contract in `config.JORDAN_GOVERNORATES`: Amman, Irbid,
Zarqa, Balqa, Mafraq, Jerash, Ajloun, Madaba, Karak, Tafilah, Ma'an, and
Aqaba. The UI displays the appropriate English or Arabic label, while the
existing `from_city`/`to_city` schema fields retain stable canonical Arabic
storage values for compatibility with historical route data. Free-form pickup,
street, and maintenance-address fields intentionally remain detailed-address
inputs rather than governorate selectors.
