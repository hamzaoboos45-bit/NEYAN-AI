"""
database/voice_db.py — Data access for Version 3 voice_history / voice_settings.
Follows the same get_db_connection() pattern as the rest of database/.
"""

from database.db import get_db_connection


def save_history_entry(user_id, session_id, audio_filename, transcription, duration_seconds):
    conn = get_db_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO voice_history
                (user_id, session_id, audio_filename, transcription, duration_seconds)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, session_id, audio_filename, transcription, duration_seconds),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_history(user_id, limit=50):
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT voice_id, session_id, audio_filename, transcription,
                   duration_seconds, created_at
            FROM voice_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_history_entry(voice_id, user_id):
    conn = get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT voice_id, user_id, session_id, audio_filename, transcription,
                   duration_seconds, created_at
            FROM voice_history
            WHERE voice_id = ? AND user_id = ?
            """,
            (voice_id, user_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_history_entry(voice_id, user_id):
    conn = get_db_connection()
    try:
        cur = conn.execute(
            "DELETE FROM voice_history WHERE voice_id = ? AND user_id = ?",
            (voice_id, user_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_settings(user_id):
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT * FROM voice_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            return dict(row)
        # Return defaults (matching the schema defaults) if never saved.
        return {
            "user_id": user_id,
            "auto_play_voice": 1,
            "voice_language": "ar",
            "playback_speed": 1.0,
            "voice_id": None,
            "mic_sensitivity": 0.02,
            "noise_suppression": 1,
            "echo_cancellation": 1,
            "auto_stop": 1,
        }
    finally:
        conn.close()


def save_settings(user_id, settings):
    conn = get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO voice_settings
                (user_id, auto_play_voice, voice_language, playback_speed,
                 voice_id, mic_sensitivity, noise_suppression,
                 echo_cancellation, auto_stop, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                auto_play_voice   = excluded.auto_play_voice,
                voice_language    = excluded.voice_language,
                playback_speed    = excluded.playback_speed,
                voice_id          = excluded.voice_id,
                mic_sensitivity   = excluded.mic_sensitivity,
                noise_suppression = excluded.noise_suppression,
                echo_cancellation = excluded.echo_cancellation,
                auto_stop         = excluded.auto_stop,
                updated_at        = datetime('now')
            """,
            (
                user_id,
                int(bool(settings.get("auto_play_voice", 1))),
                settings.get("voice_language", "ar"),
                float(settings.get("playback_speed", 1.0)),
                settings.get("voice_id"),
                float(settings.get("mic_sensitivity", 0.02)),
                int(bool(settings.get("noise_suppression", 1))),
                int(bool(settings.get("echo_cancellation", 1))),
                int(bool(settings.get("auto_stop", 1))),
            ),
        )
        conn.commit()
    finally:
        conn.close()
