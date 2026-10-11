"""Central notification persistence, ownership, and idempotency service."""

from __future__ import annotations

import json
import sqlite3
from typing import Iterable


MAX_PAGE_SIZE = 50


class NotificationService:
    @staticmethod
    def create(conn: sqlite3.Connection, *, recipient_user_id: int, event_type: str,
               source_type: str, source_id: int, metadata: dict | None = None,
               action_target: str = "", transition_key: str = "") -> bool:
        """Insert one semantic notification in the caller's transaction.

        The database unique key makes retries, double-clicks, and repeated
        lifecycle evaluation idempotent without trusting any frontend state.
        """
        dedupe_key = f"{event_type}:{source_type}:{source_id}:{recipient_user_id}:{transition_key or 'v1'}"
        cursor = conn.execute(
            """INSERT OR IGNORE INTO notifications
               (recipient_user_id, event_type, source_type, source_id,
                metadata_json, action_target, dedupe_key)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (recipient_user_id, event_type, source_type, source_id,
             json.dumps(metadata or {}, ensure_ascii=False, separators=(",", ":")),
             action_target, dedupe_key),
        )
        return cursor.rowcount == 1

    @staticmethod
    def create_for_recipients(conn: sqlite3.Connection, recipient_user_ids: Iterable[int], **kwargs) -> int:
        return sum(NotificationService.create(conn, recipient_user_id=int(user_id), **kwargs)
                   for user_id in sorted(set(recipient_user_ids)))

    @staticmethod
    def participant_user_ids(conn: sqlite3.Connection, request_id: int) -> list[int]:
        rows = conn.execute(
            "SELECT user_id FROM trip_request_members WHERE request_id=? AND member_status='active'",
            (request_id,),
        ).fetchall()
        return [int(row["user_id"]) for row in rows]

    @staticmethod
    def company_admin_user_ids(conn: sqlite3.Connection, company_id: int) -> list[int]:
        rows = conn.execute("SELECT user_id FROM users WHERE role='admin' AND company_id=?", (company_id,)).fetchall()
        return [int(row["user_id"]) for row in rows]

    @staticmethod
    def super_admin_user_ids(conn: sqlite3.Connection) -> list[int]:
        rows = conn.execute("SELECT user_id FROM users WHERE role='admin' AND company_id IS NULL").fetchall()
        return [int(row["user_id"]) for row in rows]

    @staticmethod
    def list_for_user(conn: sqlite3.Connection, user_id: int, *, limit: int, offset: int) -> list[dict]:
        limit = max(1, min(int(limit), MAX_PAGE_SIZE))
        offset = max(0, int(offset))
        rows = conn.execute(
            """SELECT notification_id, event_type, source_type, source_id,
                      metadata_json, action_target, read_at, created_at
               FROM notifications WHERE recipient_user_id=?
               ORDER BY created_at DESC, notification_id DESC LIMIT ? OFFSET ?""",
            (user_id, limit, offset),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json"))
            except (TypeError, ValueError):
                item["metadata"] = {}
                item.pop("metadata_json", None)
            item["is_read"] = item["read_at"] is not None
            result.append(item)
        return result

    @staticmethod
    def unread_count(conn: sqlite3.Connection, user_id: int) -> int:
        return int(conn.execute(
            "SELECT COUNT(*) AS count FROM notifications WHERE recipient_user_id=? AND read_at IS NULL",
            (user_id,),
        ).fetchone()["count"])

    @staticmethod
    def mark_read(conn: sqlite3.Connection, user_id: int, notification_id: int) -> bool:
        cursor = conn.execute(
            """UPDATE notifications SET read_at=COALESCE(read_at, datetime('now'))
               WHERE notification_id=? AND recipient_user_id=?""",
            (notification_id, user_id),
        )
        return cursor.rowcount == 1

    @staticmethod
    def mark_all_read(conn: sqlite3.Connection, user_id: int) -> int:
        cursor = conn.execute(
            "UPDATE notifications SET read_at=datetime('now') WHERE recipient_user_id=? AND read_at IS NULL",
            (user_id,),
        )
        return cursor.rowcount
