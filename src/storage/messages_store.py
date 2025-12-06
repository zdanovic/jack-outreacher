"""
Message store backed by SQLite.

Keeps a lightweight history of in/out messages per account and user
to make it easy for a UI to display recent dialogs without querying
Telegram every time.
"""

from __future__ import annotations

from typing import List, Dict, Any
from datetime import datetime, timedelta
import os

from .state_db import get_state_db
from ..core.crypto import DataCipher


class MessagesStore:
    def __init__(self) -> None:
        self._db = get_state_db()
        # Retention policy in days; 0 disables pruning.
        self._retention_days = int(os.getenv("MESSAGE_RETENTION_DAYS", "90"))
        self._cipher = DataCipher(os.getenv("DATA_ENCRYPTION_KEY"))

    def add_message(
        self,
        account_id: str,
        username: str,
        direction: str,
        text: str,
        ts: str | None = None,
    ) -> None:
        """
        Persist a single message. Direction is 'in' or 'out'.
        Timestamp is ISO8601; if omitted, current UTC time is used.
        """
        if not ts:
            ts = datetime.utcnow().isoformat()
        cur = self._db.conn.cursor()
        cur.execute(
            """
            INSERT INTO messages (account_id, username, direction, text, ts)
            VALUES (?, ?, ?, ?, ?);
            """,
            (account_id, username, direction, self._cipher.encrypt(text or ""), ts),
        )
        self._db.conn.commit()

        # Apply simple retention policy if configured.
        if self._retention_days > 0:
            cutoff = (datetime.utcnow() - timedelta(days=self._retention_days)).isoformat()
            cur.execute(
                "DELETE FROM messages WHERE ts < ?;",
                (cutoff,),
            )
            self._db.conn.commit()

    def get_messages(
        self,
        account_id: str,
        username: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Return recent messages for a given account / username pair,
        ordered by timestamp ascending.
        """
        cur = self._db.conn.cursor()
        cur.execute(
            """
            SELECT direction, text, ts
            FROM messages
            WHERE account_id = ? AND username = ?
            ORDER BY ts ASC
            LIMIT ?;
            """,
            (account_id, username, limit),
        )
        rows = cur.fetchall()
        return [
            {"direction": direction, "text": self._cipher.decrypt(text or ""), "ts": ts}
            for (direction, text, ts) in rows
        ]


messages_store = MessagesStore()
