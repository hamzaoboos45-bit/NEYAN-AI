"""
database/init_db.py — Complete Database Schema & Seed Data

Version 2 — Upgraded for:
    - Multi-company support (transport + maintenance)
    - Authentication (users with roles)
    - Trip classes (economy / business / vip)
    - Booking payment tracking
    - Maintenance requests
    - Chat history (for analytics + AI training)
    - Activity logs
    - Future AraBERT data collection

Run once on app startup — safe to re-run (IF NOT EXISTS).
"""

import bcrypt
import secrets

from database.db import get_db_connection


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA — All CREATE TABLE statements
# ═══════════════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """

-- ─────────────────────────────────────────────────────────
-- 1. companies
--    Stores both transport companies AND maintenance shops.
--    company_type decides which services they offer.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS companies (
    company_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    name_ar      TEXT    NOT NULL,
    company_type TEXT    NOT NULL
                 CHECK(company_type IN ('transport', 'maintenance')),
    phone        TEXT,
    email        TEXT,
    city         TEXT,
    rating       REAL    DEFAULT 0.0
                 CHECK(rating >= 0.0 AND rating <= 5.0),
    status       TEXT    NOT NULL DEFAULT 'active'
                 CHECK(status IN ('active', 'inactive', 'suspended')),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 2. users
--    Platform users: customers, admins, company employees.
--    password_hash stores bcrypt hash — never plain text.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name     TEXT    NOT NULL,
    name          TEXT,
    email         TEXT    NOT NULL UNIQUE,
    phone         TEXT,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL DEFAULT 'user'
                  CHECK(role IN ('user', 'admin', 'customer', 'company_admin')),
    status        TEXT    NOT NULL DEFAULT 'active'
                  CHECK(status IN ('active', 'pending', 'approved', 'rejected', 'disabled')),
    company_id    INTEGER REFERENCES companies(company_id),
    is_active     INTEGER NOT NULL DEFAULT 1,
    last_login    TEXT,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 3. trips
--    Scheduled transport trips offered by companies.
--    Supports bus / car / van and three booking classes.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trips (
    trip_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL
                    REFERENCES companies(company_id),
    from_city       TEXT    NOT NULL,
    to_city         TEXT    NOT NULL,
    departure_time  TEXT    NOT NULL,
    arrival_time    TEXT    NOT NULL,
    vehicle_type    TEXT    NOT NULL
                    CHECK(vehicle_type IN ('bus', 'car', 'van')),
    trip_class      TEXT    NOT NULL
                    CHECK(trip_class IN ('economy', 'business', 'vip')),
    total_seats     INTEGER NOT NULL CHECK(total_seats > 0),
    available_seats INTEGER NOT NULL CHECK(available_seats >= 0),
    price_jod       REAL    NOT NULL CHECK(price_jod >= 0),
    status          TEXT    NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active', 'cancelled', 'completed')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 4. bookings
--    Seat reservations linked to trips and optionally users.
--    Tracks payment status and booking lifecycle.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bookings (
    booking_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(user_id),
    trip_id         INTEGER NOT NULL REFERENCES trips(trip_id),
    seats_booked    INTEGER NOT NULL DEFAULT 1
                    CHECK(seats_booked > 0),
    total_price     REAL    NOT NULL CHECK(total_price >= 0),
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'confirmed', 'cancelled')),
    payment_status  TEXT    NOT NULL DEFAULT 'unpaid'
                    CHECK(payment_status IN ('unpaid', 'paid', 'refunded')),
    passenger_name  TEXT,
    passenger_phone TEXT,
    notes           TEXT,
    booked_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 4a. trip_requests / trip_request_members (Phase 5)
--     Customer demand is intentionally separate from real company trips and
--     bookings.  Assignment/conversion fields remain NULL in Step 2.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS trip_requests (
    request_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    creator_user_id        INTEGER NOT NULL REFERENCES users(user_id),
    assigned_company_id    INTEGER REFERENCES companies(company_id),
    assigned_at            TEXT,
    assigned_by_user_id    INTEGER REFERENCES users(user_id),
    company_decision       TEXT NOT NULL DEFAULT 'pending'
                           CHECK(company_decision IN ('pending', 'accepted', 'rejected')),
    company_decision_at    TEXT,
    company_decided_by_user_id INTEGER REFERENCES users(user_id),
    converted_trip_id      INTEGER UNIQUE REFERENCES trips(trip_id),
    from_city              TEXT NOT NULL,
    to_city                TEXT NOT NULL,
    requested_date         TEXT NOT NULL,
    requested_time_start   TEXT,
    requested_time_end     TEXT,
    desired_vehicle_type   TEXT CHECK(desired_vehicle_type IS NULL OR desired_vehicle_type IN ('bus', 'car', 'van')),
    desired_trip_class     TEXT CHECK(desired_trip_class IS NULL OR desired_trip_class IN ('economy', 'business', 'vip')),
    minimum_passengers     INTEGER NOT NULL CHECK(minimum_passengers >= 1),
    maximum_passengers     INTEGER NOT NULL CHECK(maximum_passengers >= minimum_passengers),
    status                 TEXT NOT NULL DEFAULT 'collecting'
                           CHECK(status IN ('collecting', 'minimum_reached', 'converted', 'rejected', 'expired', 'cancelled')),
    expires_at             TEXT NOT NULL,
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at             TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at            TEXT
);

CREATE TABLE IF NOT EXISTS trip_request_members (
    request_id          INTEGER NOT NULL REFERENCES trip_requests(request_id),
    user_id             INTEGER NOT NULL REFERENCES users(user_id),
    passenger_quantity  INTEGER NOT NULL CHECK(passenger_quantity > 0),
    member_status       TEXT NOT NULL DEFAULT 'active'
                        CHECK(member_status IN ('active', 'withdrawn')),
    joined_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (request_id, user_id)
);

CREATE TABLE IF NOT EXISTS transport_pricing_policies (
    policy_id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_city TEXT NOT NULL,
    to_city TEXT NOT NULL,
    vehicle_type TEXT,
    trip_class TEXT,
    base_trip_price_fils INTEGER NOT NULL CHECK(base_trip_price_fils > 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_by_user_id INTEGER REFERENCES users(user_id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 4b. reviews
--    A real, customer-authored rating tied to one completed-experience
--    booking. company_id is server-derived at creation time and retained
--    for efficient, auditable aggregation.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reviews (
    review_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(user_id),
    booking_id      INTEGER NOT NULL UNIQUE REFERENCES bookings(booking_id),
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    rating          INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    review_text     TEXT CHECK(review_text IS NULL OR length(review_text) <= 1000),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 5. maintenance_requests
--    Vehicle service requests assigned to maintenance companies.
--    Covers: tires, oil, battery, engine.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS maintenance_requests (
    request_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(user_id),
    company_id      INTEGER REFERENCES companies(company_id),
    service_type    TEXT    NOT NULL
                    CHECK(service_type IN (
                        'tire_repair', 'tire_replace',
                        'oil_change', 'battery',
                        'engine', 'other'
                    )),
    service_details TEXT,
    location        TEXT    NOT NULL,
    preferred_date  TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK(status IN (
                        'pending', 'assigned',
                        'in_progress', 'completed', 'cancelled'
                    )),
    customer_name   TEXT,
    customer_phone  TEXT,
    notes           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS maintenance_service_catalog (
    service_id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_key TEXT NOT NULL,
    name_en TEXT NOT NULL,
    name_ar TEXT NOT NULL,
    pricing_type TEXT NOT NULL CHECK(pricing_type IN ('fixed', 'range')),
    unit_price_fils INTEGER,
    minimum_price_fils INTEGER,
    maximum_price_fils INTEGER,
    service_fee_fils INTEGER NOT NULL DEFAULT 0 CHECK(service_fee_fils >= 0),
    quantity_enabled INTEGER NOT NULL DEFAULT 1 CHECK(quantity_enabled IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_by_user_id INTEGER REFERENCES users(user_id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Persistent recipient-owned in-app notifications. Only semantic data is
-- stored; the browser renders it safely through localization templates.
CREATE TABLE IF NOT EXISTS notifications (
    notification_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_user_id   INTEGER NOT NULL REFERENCES users(user_id),
    event_type          TEXT NOT NULL,
    source_type         TEXT NOT NULL,
    source_id           INTEGER NOT NULL,
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    action_target       TEXT NOT NULL DEFAULT '',
    read_at             TEXT,
    dedupe_key          TEXT NOT NULL UNIQUE,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 6. conversation_sessions
--    Chatbot state per browser session.
--    context_json holds collected data (cities, dates, etc.)
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversation_sessions (
    session_id    TEXT    PRIMARY KEY,
    user_id       INTEGER REFERENCES users(user_id),
    current_state TEXT    NOT NULL DEFAULT 'idle',
    context_json  TEXT    NOT NULL DEFAULT '{}',
    last_active   TEXT    NOT NULL DEFAULT (datetime('now')),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 7. chat_history
--    Every message exchanged in every conversation.
--    Used for: analytics + future AraBERT training data.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_history (
    message_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL
                    REFERENCES conversation_sessions(session_id),
    user_id         INTEGER REFERENCES users(user_id),
    sender          TEXT    NOT NULL
                    CHECK(sender IN ('user', 'bot')),
    message_text    TEXT    NOT NULL,
    detected_intent TEXT,
    bot_state       TEXT,
    sent_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 8. activity_logs
--    Tracks key user actions for analytics and auditing.
--    action_type covers all important platform events.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activity_logs (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(user_id),
    session_id  TEXT,
    action_type TEXT    NOT NULL
                CHECK(action_type IN (
                    'login', 'logout',
                    'trip_search', 'trip_view',
                    'booking_create', 'booking_cancel',
                    'maintenance_create', 'maintenance_cancel',
                    'chat_start', 'chat_reset',
                    'admin_action'
                )),
    details_json TEXT   DEFAULT '{}',
    ip_address   TEXT,
    logged_at    TEXT   NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 9. service_types  (lookup / reference table)
--    Stores display names for maintenance service types.
--    Used by frontend dropdowns and analytics labels.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS service_types (
    service_key  TEXT    PRIMARY KEY,
    name_ar      TEXT    NOT NULL,
    name_en      TEXT    NOT NULL,
    description  TEXT
);

-- ─────────────────────────────────────────────────────────
-- 10. voice_history  (Version 3 — Voice Assistant)
--     Every confirmed voice interaction: the saved audio file,
--     its Whisper transcription, and when it happened.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS voice_history (
    voice_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER REFERENCES users(user_id),
    session_id    TEXT,
    audio_filename TEXT   NOT NULL,
    transcription TEXT    NOT NULL DEFAULT '',
    duration_seconds REAL DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 11. voice_settings  (Version 3 — Voice Assistant)
--     Per-user persisted voice preferences (mirrors the
--     client-side settings panel so preferences survive
--     across devices/browsers).
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS voice_settings (
    user_id           INTEGER PRIMARY KEY REFERENCES users(user_id),
    auto_play_voice   INTEGER NOT NULL DEFAULT 1,
    voice_language    TEXT    NOT NULL DEFAULT 'ar',
    playback_speed    REAL    NOT NULL DEFAULT 1.0,
    voice_id          TEXT,
    mic_sensitivity   REAL    NOT NULL DEFAULT 0.02,
    noise_suppression INTEGER NOT NULL DEFAULT 1,
    echo_cancellation INTEGER NOT NULL DEFAULT 1,
    auto_stop         INTEGER NOT NULL DEFAULT 1,
    updated_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 12. login_attempts  (Phase One — Authentication System)
--     Every login attempt (success or failure). Used purely
--     for brute-force lockouts — see backend/security/brute_force.py.
--     Old rows are pruned automatically, so this table never
--     grows without bound.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS login_attempts (
    attempt_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    email        TEXT    NOT NULL,
    ip_address   TEXT,
    success      INTEGER NOT NULL DEFAULT 0,
    attempted_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 13. password_resets  (Phase One — Authentication System)
--     One-time, time-limited tokens for the forgot/reset
--     password flow. Only the sha256 hash of the token is
--     stored — see backend/security/password_reset.py.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS password_resets (
    token_hash TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(user_id),
    expires_at TEXT    NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 13b. password_reset_requests  (Phase 3 continuation)
--     Counts forgot-password requests (not failed logins —
--     see backend/security/brute_force.py for that) so the
--     endpoint can be rate-limited. Deliberately does NOT
--     store whether the email actually belonged to an
--     account, so this table alone reveals nothing about
--     account existence — see backend/security/reset_rate_limit.py.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS password_reset_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    email        TEXT    NOT NULL,
    ip_address   TEXT,
    requested_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 14. remember_tokens  (Phase One — Authentication System)
--     "Remember me" persistent login — selector/verifier
--     pattern. Only the sha256 hash of the verifier is
--     stored — see backend/security/remember_me.py.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS remember_tokens (
    selector   TEXT    PRIMARY KEY,
    token_hash TEXT    NOT NULL,
    user_id    INTEGER NOT NULL REFERENCES users(user_id),
    expires_at TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 15. nlp_analysis_log  (Project Two, Phase Two — Arabic NLP)
--     Best-effort audit trail of every Hybrid NLP Pipeline
--     decision: which intent was detected, how confident the
--     AI was, whether AraBERT or the Rule-Based fallback
--     answered, and what entities MARBERT/gazetteer found.
--     Purely additive table — no existing table's schema was
--     changed. Written by backend/chatbot.py on a best-effort
--     basis (a logging failure here never blocks a chat reply).
--     This is the dataset the Final Audit (intent/entity
--     accuracy, fallback rate) should be measured against.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS nlp_analysis_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    detected_intent TEXT    NOT NULL,
    confidence      REAL    NOT NULL,
    source          TEXT    NOT NULL,   -- 'ai' | 'rule_based'
    entities_json   TEXT    NOT NULL DEFAULT '{}',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────
-- 16. chat_rate_limit_events (Phase 6)
--     Short-lived authenticated chat request events. This small table keeps
--     abuse controls effective across requests and process restarts without
--     introducing another dependency or changing existing business tables.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_rate_limit_events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(user_id),
    ip_address TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

"""


# ═══════════════════════════════════════════════════════════════════════════════
# INDEXES — speed up common queries
# ═══════════════════════════════════════════════════════════════════════════════

INDEXES_SQL = """

-- Trips: most common search is by route
CREATE INDEX IF NOT EXISTS idx_trips_route
    ON trips(from_city, to_city);

-- Trips: filter by company
CREATE INDEX IF NOT EXISTS idx_trips_company
    ON trips(company_id);

-- Phase 8 dashboard company-scoped counts and optional UTC date filters.
CREATE INDEX IF NOT EXISTS idx_trips_company_created
    ON trips(company_id, created_at);

-- Platform-wide time filters and trend grouping used by the advanced admin dashboard.
CREATE INDEX IF NOT EXISTS idx_trips_created
    ON trips(created_at);

CREATE INDEX IF NOT EXISTS idx_bookings_trip_booked
    ON bookings(trip_id, booked_at);

CREATE INDEX IF NOT EXISTS idx_bookings_booked
    ON bookings(booked_at);

CREATE INDEX IF NOT EXISTS idx_bookings_user_booked
    ON bookings(user_id, booked_at);

-- Forming trip request reads, expiry sweeps, and future assignment queues.
CREATE INDEX IF NOT EXISTS idx_trip_requests_compatibility
    ON trip_requests(status, from_city, to_city, requested_date);
CREATE INDEX IF NOT EXISTS idx_trip_requests_assigned_status
    ON trip_requests(assigned_company_id, status);
CREATE INDEX IF NOT EXISTS idx_trip_requests_decision_queue
    ON trip_requests(assigned_company_id, company_decision, status);
CREATE INDEX IF NOT EXISTS idx_trip_requests_expiry_status
    ON trip_requests(expires_at, status);
CREATE INDEX IF NOT EXISTS idx_trip_request_members_active
    ON trip_request_members(request_id, member_status);
CREATE INDEX IF NOT EXISTS idx_transport_pricing_policy_lookup
    ON transport_pricing_policies(is_active, from_city, to_city, vehicle_type, trip_class);
CREATE INDEX IF NOT EXISTS idx_maintenance_catalog_active
    ON maintenance_service_catalog(is_active, service_key);

-- Real-review aggregation and the customer's bounded review dashboard list.
CREATE INDEX IF NOT EXISTS idx_reviews_company
    ON reviews(company_id);

CREATE INDEX IF NOT EXISTS idx_reviews_user_created
    ON reviews(user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_maintenance_company_created
    ON maintenance_requests(company_id, created_at);

CREATE INDEX IF NOT EXISTS idx_maintenance_created
    ON maintenance_requests(created_at);

CREATE INDEX IF NOT EXISTS idx_maintenance_user_created
    ON maintenance_requests(user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_notifications_recipient_created
    ON notifications(recipient_user_id, created_at DESC, notification_id DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient_unread
    ON notifications(recipient_user_id, read_at, created_at DESC);

-- Chat history: fetch all messages of a session
CREATE INDEX IF NOT EXISTS idx_chat_session
    ON chat_history(session_id);

-- Activity logs: time-based analytics queries
CREATE INDEX IF NOT EXISTS idx_logs_time
    ON activity_logs(logged_at);

-- Voice history: fetch a user's recordings, most recent first
CREATE INDEX IF NOT EXISTS idx_voice_history_user
    ON voice_history(user_id, created_at);

-- Login attempts: brute-force lockout lookups (by email / by IP)
CREATE INDEX IF NOT EXISTS idx_login_attempts_email
    ON login_attempts(email, attempted_at);
CREATE INDEX IF NOT EXISTS idx_login_attempts_ip
    ON login_attempts(ip_address, attempted_at);

-- Remember-me tokens: cleanup / per-user revocation
CREATE INDEX IF NOT EXISTS idx_remember_tokens_user
    ON remember_tokens(user_id);

-- Password resets: per-user lookups
CREATE INDEX IF NOT EXISTS idx_password_resets_user
    ON password_resets(user_id);

-- Password reset requests: rate-limit lookups by email/IP within a window
CREATE INDEX IF NOT EXISTS idx_reset_requests_email
    ON password_reset_requests(email, requested_at);
CREATE INDEX IF NOT EXISTS idx_reset_requests_ip
    ON password_reset_requests(ip_address, requested_at);

-- NLP analysis log: per-session audit trail lookups
CREATE INDEX IF NOT EXISTS idx_nlp_log_session
    ON nlp_analysis_log(session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_chat_rate_limit_user
    ON chat_rate_limit_events(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_rate_limit_ip
    ON chat_rate_limit_events(ip_address, created_at);

"""


# ═══════════════════════════════════════════════════════════════════════════════
# SEED DATA — realistic sample records for development and testing
# ═══════════════════════════════════════════════════════════════════════════════

SEED_SQL = """

-- ── Companies: Transport ────────────────────────────────────────────────────
INSERT OR IGNORE INTO companies
    (company_id, name, name_ar, company_type, phone, email, city, rating)
VALUES
    (1, 'Jordan Express',  'الأردن إكسبريس',  'transport', '0799001001', 'info@jexpress.jo',  'عمان',   4.5),
    (2, 'Northern Lines',  'الخطوط الشمالية', 'transport', '0799002002', 'info@nlines.jo',    'إربد',   4.2),
    (3, 'Gulf Transport',  'الخليج للنقل',    'transport', '0799003003', 'info@gulftrans.jo', 'العقبة', 4.7),
    (4, 'Capital Shuttle', 'كابيتال شاتل',    'transport', '0799004004', 'info@cshuttle.jo',  'عمان',   4.0);

-- ── Companies: Maintenance ──────────────────────────────────────────────────
INSERT OR IGNORE INTO companies
    (company_id, name, name_ar, company_type, phone, email, city, rating)
VALUES
    (5, 'Quick Fix Auto',  'كويك فيكس للسيارات', 'maintenance', '0799005005', 'info@quickfix.jo', 'عمان', 4.3),
    (6, 'North Garage',    'مرآب الشمال',         'maintenance', '0799006006', 'info@ngauge.jo',   'إربد', 4.1),
    (7, 'South Auto Care', 'ساوث أوتو',           'maintenance', '0799007007', 'info@sauto.jo',    'العقبة', 4.6);

-- ── Users ───────────────────────────────────────────────────────────────────
-- Seed identities are customers only. Privileged accounts are deliberately
-- never created with known credentials; use scripts/bootstrap_super_admin.py.
INSERT OR IGNORE INTO users
    (user_id, full_name, name, email, phone, password_hash, role, status)
VALUES
    (1, 'Demo Customer',  'Demo Customer', 'sample.customer@example.invalid', '0790000001', 'hashed_user_pw_0',  'user', 'active'),
    (2, 'Ahmad Al-Masri', 'Ahmad Al-Masri', 'sample.ahmad@example.invalid', '0791000001', 'hashed_user_pw_1',  'user', 'active'),
    (3, 'Sara Al-Khalil', 'Sara Al-Khalil', 'sample.sara@example.invalid',  '0791000002', 'hashed_user_pw_2',  'user', 'active'),
    (4, 'Demo Company User', 'Demo Company User', 'sample.company@example.invalid', '0799001010', 'hashed_user_pw_3', 'user', 'active');

-- ── Service Types (lookup table) ────────────────────────────────────────────
INSERT OR IGNORE INTO service_types
    (service_key, name_ar, name_en, description)
VALUES
    ('tire_repair',  'تصليح إطارات', 'Tire Repair',     'إصلاح البنشر وتصليح الإطار'),
    ('tire_replace', 'تبديل إطارات', 'Tire Replacement', 'تبديل إطار واحد أو أكثر'),
    ('oil_change',   'تغيير زيت',    'Oil Change',       'تغيير زيت المحرك والفلتر'),
    ('battery',      'صيانة بطارية', 'Battery Service',  'فحص وشحن أو تبديل البطارية'),
    ('engine',       'صيانة محرك',   'Engine Maintenance','فحص وصيانة المحرك'),
    ('other',        'أخرى',         'Other',            'خدمات صيانة أخرى');

-- ── Trips ───────────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO trips
    (trip_id, company_id, from_city, to_city,
     departure_time, arrival_time,
     vehicle_type, trip_class,
     total_seats, available_seats, price_jod)
VALUES
    -- عمان ← إربد
    (1, 1, 'عمان', 'إربد',   '2025-07-01 07:00', '2025-07-01 09:00', 'bus', 'economy',  45, 32, 3.50),
    (2, 1, 'عمان', 'إربد',   '2025-07-01 09:00', '2025-07-01 11:00', 'bus', 'business', 30, 18, 6.00),
    (3, 2, 'عمان', 'إربد',   '2025-07-01 11:00', '2025-07-01 13:00', 'van', 'economy',  10,  7, 4.00),
    -- عمان ← العقبة
    (4, 3, 'عمان', 'العقبة', '2025-07-01 06:00', '2025-07-01 10:00', 'bus', 'economy',  45, 20, 8.00),
    (5, 1, 'عمان', 'العقبة', '2025-07-01 08:00', '2025-07-01 12:00', 'bus', 'business', 30, 15, 12.00),
    (6, 3, 'عمان', 'العقبة', '2025-07-02 07:00', '2025-07-02 11:00', 'bus', 'vip',      20, 10, 18.00),
    -- إربد ← عمان
    (7, 2, 'إربد', 'عمان',   '2025-07-01 08:00', '2025-07-01 10:00', 'bus', 'economy',  45, 28, 3.50),
    (8, 2, 'إربد', 'عمان',   '2025-07-01 14:00', '2025-07-01 16:00', 'van', 'economy',  10,  5, 4.00),
    -- الزرقاء ← عمان
    (9, 4, 'عمان', 'الزرقاء','2025-07-01 07:30', '2025-07-01 08:30', 'car', 'economy',   4,  3, 2.00),
    (10,4, 'عمان', 'الزرقاء','2025-07-01 10:00', '2025-07-01 11:00', 'car', 'economy',   4,  4, 2.00);

-- ── Sample Bookings ─────────────────────────────────────────────────────────
INSERT OR IGNORE INTO bookings
    (booking_id, user_id, trip_id, seats_booked,
     total_price, status, payment_status, passenger_name, passenger_phone)
VALUES
    (1, 2, 1, 2, 7.00,  'confirmed', 'paid',   'Ahmad Al-Masri', '0791000001'),
    (2, 3, 4, 1, 8.00,  'confirmed', 'paid',   'Sara Al-Khalil', '0791000002'),
    (3, 2, 7, 1, 3.50,  'pending',   'unpaid', 'Ahmad Al-Masri', '0791000001'),
    (4, NULL, 5, 2, 24.00, 'confirmed', 'paid', 'مسافر زيارة',   '0795000001');

-- ── Sample Maintenance Requests ─────────────────────────────────────────────
INSERT OR IGNORE INTO maintenance_requests
    (request_id, user_id, company_id, service_type,
     service_details, location, preferred_date,
     status, customer_name, customer_phone)
VALUES
    (1, 2, 5, 'tire_repair',
     'بنشر في الإطار الأمامي الأيمن',
     'شارع الجامعة، عمان',
     '2025-07-05', 'completed',
     'Ahmad Al-Masri', '0791000001'),
    (2, 3, 6, 'oil_change',
     'تغيير زيت المحرك وفلتر الزيت',
     'حي النزهة، إربد',
     '2025-07-10', 'pending',
     'Sara Al-Khalil', '0791000002'),
    (3, NULL, 5, 'battery',
     'البطارية لا تشحن',
     'الدوار الأول، عمان',
     '2025-07-08', 'assigned',
     'خالد العمري', '0796000001');

"""


# ═══════════════════════════════════════════════════════════════════════════════
# INITIALIZE — called from app.py on startup
# ═══════════════════════════════════════════════════════════════════════════════

def initialize_database():
    """
    Create all tables, indexes, and seed data.
    Safe to call every startup — IF NOT EXISTS / INSERT OR IGNORE
    ensure existing data is never overwritten.
    """
    conn = get_db_connection()
    try:
        # Enable foreign key enforcement
        conn.execute("PRAGMA foreign_keys = ON")

        # Step 1: Create new tables (IF NOT EXISTS — safe for existing DBs)
        conn.executescript(SCHEMA_SQL)

        # Step 2: Add missing columns to OLD tables (migration)
        # Must run BEFORE indexes so columns exist when indexes are created
        _run_migrations(conn)
        _ensure_users_table_v3(conn)

        # Step 3: Create indexes (now all columns exist)
        conn.executescript(INDEXES_SQL)

        # Step 4: Insert seed data (INSERT OR IGNORE — safe)
        conn.executescript(SEED_SQL)

        # Step 5: Normalize Version 3 authentication fields and seed hashes.
        _normalize_auth_accounts(conn)

        conn.commit()
        print("[DB] OK Database initialized successfully.")
        print("[DB] OK Tables: companies, users, trips, bookings,")
        print("[DB]          maintenance_requests, conversation_sessions,")
        print("[DB]          chat_history, activity_logs, service_types,")
        print("[DB]          voice_history, voice_settings,")
        print("[DB]          login_attempts, password_resets, password_reset_requests, remember_tokens")

    except Exception as e:
        conn.rollback()
        print(f"[DB] ERROR Initialization error: {e}")
        raise

    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# MIGRATION HELPERS — run once to upgrade existing databases
# ═══════════════════════════════════════════════════════════════════════════════

def _run_migrations(conn):
    """
    Internal helper — adds missing columns to existing tables.
    Each ALTER TABLE is wrapped in try/except so it's safe to re-run
    even if the column already exists.
    Called automatically by initialize_database() before indexes.
    """
    migrations = [
        # trips
        "ALTER TABLE trips ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
        "ALTER TABLE trips ADD COLUMN created_at TEXT NOT NULL DEFAULT (datetime('now'))",
        "ALTER TABLE trips ADD COLUMN vehicle_type TEXT NOT NULL DEFAULT 'bus'",
        "ALTER TABLE trips ADD COLUMN trip_class TEXT NOT NULL DEFAULT 'economy'",
        "ALTER TABLE trips ADD COLUMN total_seats INTEGER NOT NULL DEFAULT 45",
        "ALTER TABLE trips ADD COLUMN departure_time TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE trips ADD COLUMN arrival_time TEXT NOT NULL DEFAULT ''",
        # bookings
        "ALTER TABLE bookings ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'unpaid'",
        "ALTER TABLE bookings ADD COLUMN updated_at TEXT NOT NULL DEFAULT (datetime('now'))",
        "ALTER TABLE bookings ADD COLUMN notes TEXT",
        "ALTER TABLE bookings ADD COLUMN user_id INTEGER",
        "ALTER TABLE bookings ADD COLUMN passenger_name TEXT",
        "ALTER TABLE bookings ADD COLUMN passenger_phone TEXT",
        # users
        "ALTER TABLE users ADD COLUMN name TEXT",
        "ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
        "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE users ADD COLUMN last_login TEXT",
        "ALTER TABLE users ADD COLUMN company_id INTEGER",
        "ALTER TABLE users ADD COLUMN phone TEXT",
        # companies
        "ALTER TABLE companies ADD COLUMN rating REAL DEFAULT 0.0",
        "ALTER TABLE companies ADD COLUMN status TEXT NOT NULL DEFAULT 'active'",
        "ALTER TABLE companies ADD COLUMN phone TEXT",
        "ALTER TABLE companies ADD COLUMN email TEXT",
        "ALTER TABLE companies ADD COLUMN city TEXT",
        "ALTER TABLE companies ADD COLUMN created_at TEXT NOT NULL DEFAULT (datetime('now'))",

        # Phase 5 Step 4: bounded assignment/decision metadata. Existing
        # rows remain safe with a pending decision until a super admin acts.
        "ALTER TABLE trip_requests ADD COLUMN assigned_at TEXT",
        "ALTER TABLE trip_requests ADD COLUMN assigned_by_user_id INTEGER",
        "ALTER TABLE trip_requests ADD COLUMN company_decision TEXT NOT NULL DEFAULT 'pending'",
        "ALTER TABLE trip_requests ADD COLUMN company_decision_at TEXT",
        "ALTER TABLE trip_requests ADD COLUMN company_decided_by_user_id INTEGER",
        # Pricing additions preserve legacy rows as private/unpriced.
        "ALTER TABLE trip_requests ADD COLUMN sharing_mode TEXT NOT NULL DEFAULT 'private'",
        "ALTER TABLE trip_requests ADD COLUMN transport_pricing_policy_id INTEGER",
        "ALTER TABLE trip_requests ADD COLUMN base_trip_price_fils INTEGER",
        "ALTER TABLE trips ADD COLUMN forming_request_id INTEGER",
        "ALTER TABLE trips ADD COLUMN shared_base_price_fils INTEGER",
        "ALTER TABLE trips ADD COLUMN transport_pricing_policy_id INTEGER",
        "ALTER TABLE bookings ADD COLUMN pricing_snapshot_fils INTEGER",
        "ALTER TABLE maintenance_requests ADD COLUMN catalog_service_id INTEGER",
        "ALTER TABLE maintenance_requests ADD COLUMN service_name_en_snapshot TEXT",
        "ALTER TABLE maintenance_requests ADD COLUMN service_name_ar_snapshot TEXT",
        "ALTER TABLE maintenance_requests ADD COLUMN pricing_type_snapshot TEXT",
        "ALTER TABLE maintenance_requests ADD COLUMN quantity INTEGER",
        "ALTER TABLE maintenance_requests ADD COLUMN unit_price_fils_snapshot INTEGER",
        "ALTER TABLE maintenance_requests ADD COLUMN minimum_price_fils_snapshot INTEGER",
        "ALTER TABLE maintenance_requests ADD COLUMN maximum_price_fils_snapshot INTEGER",
        "ALTER TABLE maintenance_requests ADD COLUMN service_fee_fils_snapshot INTEGER",
        "ALTER TABLE maintenance_requests ADD COLUMN total_minimum_fils_snapshot INTEGER",
        "ALTER TABLE maintenance_requests ADD COLUMN total_maximum_fils_snapshot INTEGER",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
            conn.commit()
        except Exception:
            pass


def migrate_add_missing_columns():
    """
    Public migration helper — can be called manually if needed.
    """
    conn = get_db_connection()
    _run_migrations(conn)
    _normalize_auth_accounts(conn)
    conn.commit()
    conn.close()
    print("[DB] OK Migration completed.")


def _bcrypt_hash(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _ensure_users_table_v3(conn):
    """
    Rebuild only the users table if an older CHECK constraint rejects role='user'.
    User IDs are copied exactly so foreign-key references remain valid.
    """
    create_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).fetchone()
    if not create_sql or "'user'" in create_sql["sql"]:
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(
        """
        CREATE TABLE users_v3 (
            user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name     TEXT    NOT NULL,
            name          TEXT,
            email         TEXT    NOT NULL UNIQUE,
            phone         TEXT,
            password_hash TEXT    NOT NULL,
            role          TEXT    NOT NULL DEFAULT 'user'
                          CHECK(role IN ('user', 'admin', 'customer', 'company_admin')),
            status        TEXT    NOT NULL DEFAULT 'active'
                          CHECK(status IN ('active', 'pending', 'approved', 'rejected', 'disabled')),
            company_id    INTEGER REFERENCES companies(company_id),
            is_active     INTEGER NOT NULL DEFAULT 1,
            last_login    TEXT,
            created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        INSERT INTO users_v3 (
            user_id, full_name, name, email, phone, password_hash,
            role, status, company_id, is_active, last_login, created_at
        )
        SELECT
            user_id,
            full_name,
            COALESCE(NULLIF(name, ''), full_name),
            email,
            phone,
            password_hash,
            CASE
                WHEN role = 'customer' THEN 'user'
                WHEN role = 'company_admin' THEN 'admin'
                ELSE role
            END,
            CASE
                WHEN role IN ('admin', 'company_admin') THEN 'approved'
                ELSE COALESCE(status, 'active')
            END,
            company_id,
            is_active,
            last_login,
            created_at
        FROM users;

        DROP TABLE users;
        ALTER TABLE users_v3 RENAME TO users;
        """
    )
    conn.execute("PRAGMA foreign_keys = ON")


def _normalize_auth_accounts(conn):
    """
    Upgrade old Version 2 user rows for Version 3 authentication.
    Existing IDs are preserved so bookings, maintenance, and chat history stay linked.
    """
    conn.execute("UPDATE users SET name = full_name WHERE name IS NULL OR trim(name) = ''")
    conn.execute("UPDATE users SET role = 'user' WHERE role = 'customer'")
    conn.execute("UPDATE users SET role = 'admin' WHERE role = 'company_admin'")
    conn.execute("UPDATE users SET status = 'approved' WHERE role = 'admin' AND status = 'active'")
    conn.execute("UPDATE users SET status = 'active' WHERE role = 'user' AND status IS NULL")

    # Seed rows must never introduce a known credential into a fresh project
    # archive or deployment. Their initial random passwords are intentionally
    # not persisted outside bcrypt hashes; real users use registration/reset
    # flows, and administrator bootstrap remains an explicit operator action.
    seed_passwords = {
        email: secrets.token_urlsafe(32)
        for email in (
            "sample.customer@example.invalid", "sample.ahmad@example.invalid",
            "sample.sara@example.invalid", "sample.company@example.invalid",
        )
    }
    placeholders = {"hashed_user_pw_0", "hashed_user_pw_1", "hashed_user_pw_2", "hashed_user_pw_3"}

    rows = conn.execute("SELECT user_id, email, password_hash FROM users").fetchall()
    for row in rows:
        if row["password_hash"] in placeholders and row["email"] in seed_passwords:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE user_id = ?",
                (_bcrypt_hash(seed_passwords[row["email"]]), row["user_id"]),
            )
