from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Dict, Any

from .state_db import get_state_db


class OutboxStore:
    """
    Simple queue for pending messages when account is offline/login required.
    """

    def __init__(self) -> None:
        self._db = get_state_db()

    def add_pending(
        self,
        account_id: str,
        username: str,
        direction: str,
        text: str,
        send_after_sec: int = 0,
        ttl_hours: int = 24,
        fail_reason: str | None = None,
    ) -> int:
        now = datetime.utcnow()
        send_after = now + timedelta(seconds=send_after_sec)
        expires_at = now + timedelta(hours=ttl_hours)
        cur = self._db.conn.cursor()
        cur.execute(
            """
            INSERT INTO pending_outbox (account_id, username, direction, text, status, fail_reason, created_at, send_after, expires_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?);
            """,
            (
                account_id,
                username,
                direction,
                text,
                fail_reason,
                now.isoformat(),
                send_after.isoformat(),
                expires_at.isoformat(),
            ),
        )
        self._db.conn.commit()
        return int(cur.lastrowid)

    def list_pending(self, account_id: str | None = None) -> List[Dict[str, Any]]:
        cur = self._db.conn.cursor()
        if account_id:
            cur.execute(
                """
                SELECT id, account_id, username, direction, text, status, fail_reason, created_at, send_after, expires_at
                FROM pending_outbox
                WHERE status = 'pending' AND account_id = ?
                ORDER BY created_at ASC;
                """,
                (account_id,),
            )
        else:
            cur.execute(
                """
                SELECT id, account_id, username, direction, text, status, fail_reason, created_at, send_after, expires_at
                FROM pending_outbox
                WHERE status = 'pending'
                ORDER BY created_at ASC;
                """
            )
        rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "account_id": row[1],
                "username": row[2],
                "direction": row[3],
                "text": row[4],
                "status": row[5],
                "fail_reason": row[6],
                "created_at": row[7],
                "send_after": row[8],
                "expires_at": row[9],
            }
            for row in rows
        ]

    def mark_sent(self, outbox_id: int) -> None:
        cur = self._db.conn.cursor()
        cur.execute(
            "UPDATE pending_outbox SET status='sent' WHERE id=?;",
            (outbox_id,),
        )
        self._db.conn.commit()

    def mark_failed(self, outbox_id: int, reason: str) -> None:
        cur = self._db.conn.cursor()
        cur.execute(
            "UPDATE pending_outbox SET status='failed', fail_reason=? WHERE id=?;",
            (reason, outbox_id),
        )
        self._db.conn.commit()


outbox_store = OutboxStore()
