from dataclasses import dataclass
from typing import Optional

from datetime import datetime

from .state_db import get_state_db


def _normalize_username(raw: str) -> str:
    return raw.strip().lstrip("@").lower()


@dataclass
class DialogMeta:
    """Basic information about a dialog with a user."""

    username: str  # normalized username without '@'
    peer_id: Optional[int] = None
    is_lead: bool = False
    lead_id: Optional[str] = None
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    last_account_id: Optional[str] = None
    manual_replied_at: Optional[str] = None


class DialogsStore:
    """
    Placeholder for dialog state (sent users, passed_to_sales, etc.).
    """

    def __init__(self) -> None:
        self._db = get_state_db()

    def get(self, username: str) -> Optional[DialogMeta]:
        uname = _normalize_username(username)
        cur = self._db.conn.cursor()
        cur.execute(
            """
            SELECT username, peer_id, is_lead, lead_id,
                   first_seen_at, last_seen_at, last_account_id, manual_replied_at
            FROM dialogs WHERE username = ?;
            """,
            (uname,),
        )
        row = cur.fetchone()
        if not row:
            return None
        username, peer_id, is_lead, lead_id, first_seen_at, last_seen_at, last_account_id, manual_replied_at = row
        return DialogMeta(
            username=username,
            peer_id=peer_id,
            is_lead=bool(is_lead),
            lead_id=lead_id or None,
            first_seen_at=first_seen_at or None,
            last_seen_at=last_seen_at or None,
            last_account_id=last_account_id or None,
            manual_replied_at=manual_replied_at or None,
        )

    def upsert(self, meta: DialogMeta) -> None:
        uname = _normalize_username(meta.username)
        now = datetime.utcnow().isoformat()
        cur = self._db.conn.cursor()
        # Preserve first_seen_at if the row already exists.
        cur.execute(
            "SELECT first_seen_at FROM dialogs WHERE username = ?;",
            (uname,),
        )
        row = cur.fetchone()
        first_seen_at = row[0] if row and row[0] else now
        cur.execute(
            """
            INSERT INTO dialogs (
                username, peer_id, is_lead, lead_id,
                first_seen_at, last_seen_at, last_account_id, manual_replied_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                peer_id = excluded.peer_id,
                is_lead = excluded.is_lead,
                lead_id = excluded.lead_id,
                first_seen_at = first_seen_at,
                last_seen_at = excluded.last_seen_at,
                last_account_id = excluded.last_account_id,
                manual_replied_at = excluded.manual_replied_at;
            """.replace("first_seen_at = first_seen_at", "first_seen_at = first_seen_at"),
            (
                uname,
                meta.peer_id,
                1 if meta.is_lead else 0,
                meta.lead_id,
                first_seen_at,
                now,
                meta.last_account_id,
                meta.manual_replied_at,
            ),
        )
        self._db.conn.commit()

    def list_for_account(self, account_id: str, limit: int = 100):
        cur = self._db.conn.cursor()
        cur.execute(
            """
            SELECT username, peer_id, is_lead, lead_id, first_seen_at, last_seen_at, last_account_id, manual_replied_at
            FROM dialogs
            WHERE last_account_id = ?
            ORDER BY COALESCE(last_seen_at, first_seen_at) DESC
            LIMIT ?;
            """,
            (account_id, limit),
        )
        rows = cur.fetchall()
        result = []
        for row in rows:
            username, peer_id, is_lead, lead_id, first_seen_at, last_seen_at, last_account_id, manual_replied_at = row
            result.append(
                {
                    "username": username,
                    "peer_id": peer_id,
                    "is_lead": bool(is_lead),
                    "lead_id": lead_id,
                    "first_seen_at": first_seen_at,
                    "last_seen_at": last_seen_at,
                    "last_account_id": last_account_id,
                    "manual_replied_at": manual_replied_at,
                }
            )
        return result

    def mark_manual_reply(self, username: str, account_id: str) -> None:
        uname = _normalize_username(username)
        now = datetime.utcnow().isoformat()
        cur = self._db.conn.cursor()
        # Ensure row exists
        cur.execute(
            """
            INSERT INTO dialogs (username, manual_replied_at, last_account_id, first_seen_at, last_seen_at, is_lead)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(username) DO NOTHING;
            """,
            (uname, now, account_id, now, now),
        )
        cur.execute(
            """
            UPDATE dialogs
            SET manual_replied_at = ?, last_account_id = ?
            WHERE username = ?;
            """,
            (now, account_id, uname),
        )
        self._db.conn.commit()
