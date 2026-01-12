from dataclasses import dataclass
from typing import List, Optional

import csv
import os
from datetime import datetime
import threading

from .state_db import get_state_db, DATA_DIR


def _normalize_username(raw: str) -> str:
    return raw.strip().lstrip("@").lower()


@dataclass
class Lead:
    username: str  # normalized telegram username without '@'
    name: str
    tag: str
    source: str = ""
    status: str = "new"  # new/contacted/hot/warm/cold/lost
    last_account_id: Optional[str] = None
    last_contacted_at: Optional[str] = None  # ISO8601
    first_name: str = ""
    last_name: str = ""
    bio: str = ""


class LeadsStore:
    """
    Minimal placeholder for lead storage.

    In the first iteration this can simply read from the existing CSV
    file used by auto_dms.py; later we can move to a database and add
    richer status tracking.
    """

    def __init__(self, csv_path: Optional[str] = None) -> None:
        # Input CSV with raw lead data (usernames, names, tags).
        self.csv_path = csv_path or os.path.join(DATA_DIR, "leads_strategy_1.csv")
        self._db = get_state_db()
        self._seeded = False
        self._seed_lock = threading.Lock()

        # Temporary customer test mode (multi-account contact on fixed usernames).
        self.customer_test_mode = os.getenv("CUSTOMER_TEST_MODE", "").strip().lower() in ("1", "true", "yes", "on")
        raw_users = os.getenv("CUSTOMER_TEST_USERS", "")
        self.customer_test_users = [_normalize_username(u) for u in raw_users.split(",") if _normalize_username(u)]
        if os.getenv("PYTEST_CURRENT_TEST"):
            # Never force customer test mode during unit tests.
            self.customer_test_mode = False
            self.customer_test_users = []

        def _to_float(env: str, default: float) -> float:
            try:
                return float(os.getenv(env, default))
            except Exception:
                return default

        self.customer_test_send_min = _to_float("CUSTOMER_TEST_SEND_MIN", 30.0)
        self.customer_test_send_max = _to_float("CUSTOMER_TEST_SEND_MAX", 300.0)
        self._customer_test_cursor = 0

    def seed_from_csv_once(self) -> None:
        """
        One-time ingestion from the lead CSV into SQLite.

        New leads are inserted only if they are not already present in
        the database; existing rows are left untouched so that state
        changes are durable and not overwritten.
        """
        if self._seeded:
            return
        with self._seed_lock:
            if self._seeded:
                return
            self._seeded = True
            if not os.path.exists(self.csv_path):
                return

            with open(self.csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                cur = self._db.conn.cursor()
                for row in reader:
                    raw_username = row.get("Username", "") or row.get("username", "")
                    username = _normalize_username(raw_username)
                    if not username:
                        continue
                    first_name = (row.get("First Name") or row.get("first_name") or "").strip()
                    last_name = (row.get("Last Name") or row.get("last_name") or "").strip()
                    name = (row.get("name") or f"{first_name} {last_name}".strip() or "").strip()
                    bio = (row.get("Bio") or row.get("bio") or "").strip()
                    tag = (row.get("Tag") or row.get("tag") or "eng").strip().lower()[:3]
                    source = (row.get("Source") or row.get("source") or "").strip()

                    cur.execute(
                        """
                        INSERT INTO leads (username, name, first_name, last_name, bio, tag, source, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
                        ON CONFLICT(username) DO NOTHING;
                        """,
                        (username, name, first_name, last_name, bio, tag, source),
                    )
                self._db.conn.commit()

    def load_new_leads(self, limit: int | None = None) -> List[Lead]:
        """
        Return a list of leads with status 'new' (not yet contacted).

        This is the primary entry point for OutreachEngine when planning
        new cold DMs.
        """
        self.seed_from_csv_once()
        cur = self._db.conn.cursor()
        if limit is not None:
            cur.execute(
                """
                SELECT username, name, tag, source, status, last_account_id, last_contacted_at
                FROM leads
                WHERE status = 'new'
                LIMIT ?;
                """,
                (limit,),
            )
        else:
            cur.execute(
                """
                SELECT username, name, first_name, last_name, bio, tag, source, status, last_account_id, last_contacted_at
                FROM leads
                WHERE status = 'new';
                """
            )
        rows = cur.fetchall()
        leads: List[Lead] = []
        for (
            username,
            name,
            first_name,
            last_name,
            bio,
            tag,
            source,
            status,
            last_account_id,
            last_contacted_at,
        ) in rows:
            leads.append(
                Lead(
                    username=username,
                    name=name or "",
                    first_name=first_name or "",
                    last_name=last_name or "",
                    bio=bio or "",
                    tag=tag or "",
                    source=source or "",
                    status=status or "new",
                    last_account_id=last_account_id,
                    last_contacted_at=last_contacted_at,
                )
            )
        return leads

    def _next_customer_test_lead(self, account_id: str) -> Optional[Lead]:
        """
        Round-robin over CUSTOMER_TEST_USERS allowing multiple accounts to
        contact the same usernames without blocking each other.
        """
        if not self.customer_test_mode or not self.customer_test_users:
            return None
        uname = self.customer_test_users[self._customer_test_cursor % len(self.customer_test_users)]
        self._customer_test_cursor += 1

        cur = self._db.conn.cursor()
        cur.execute(
            """
            INSERT INTO leads (username, tag, source, status, last_account_id)
            VALUES(?, 'customer_test', 'manual_customer_test', 'pending', ?)
            ON CONFLICT(username) DO UPDATE SET
                status='pending',
                last_account_id=excluded.last_account_id;
            """,
            (uname, account_id),
        )
        self._db.conn.commit()

        return Lead(
            username=uname,
            name="",
            tag="customer_test",
            source="manual_customer_test",
            status="pending",
            last_account_id=account_id,
            last_contacted_at=None,
        )

    def mark_contacted(self, username: str, account_id: str) -> None:
        """Mark a lead as contacted by a specific account."""
        uname = _normalize_username(username)
        ts = datetime.utcnow().isoformat()
        cur = self._db.conn.cursor()
        cur.execute(
            """
            UPDATE leads
            SET status = 'contacted',
                last_account_id = ?,
                last_contacted_at = ?
            WHERE username = ?;
            """,
            (account_id, ts, uname),
        )
        self._db.conn.commit()

    def update_status(self, username: str, status: str, fail_reason: str | None = None) -> None:
        """
        Update lead status (e.g. hot/warm/cold/lost). This is typically
        called by ReplyEngine after AI‑based qualification.
        """
        uname = _normalize_username(username)
        cur = self._db.conn.cursor()
        cur.execute(
            "UPDATE leads SET status = ?, fail_reason = ? WHERE username = ?;",
            (status, fail_reason, uname),
        )
        self._db.conn.commit()

    def reserve_lead_for_account(self, account_id: str) -> Optional[Lead]:
        """
        Atomically reserve the next 'new' lead for the given account.
        The lead status is changed to 'pending' to avoid duplicates
        between accounts and processes.
        """
        test_lead = self._next_customer_test_lead(account_id)
        if test_lead:
            return test_lead

        self.seed_from_csv_once()
        cur = self._db.conn.cursor()
        try:
            cur.execute("BEGIN IMMEDIATE;")
            cur.execute(
                """
                SELECT username, name, tag, source, status, last_account_id, last_contacted_at
                FROM leads
                WHERE status = 'new'
                LIMIT 1;
                """
            )
            row = cur.fetchone()
            if not row:
                self._db.conn.commit()
                return None
            username, name, tag, source, status, last_account_id, last_contacted_at = row
            cur.execute(
                """
                UPDATE leads
                SET status = 'pending',
                    last_account_id = ?
                WHERE username = ?;
                """,
                (account_id, username),
            )
            self._db.conn.commit()
            return Lead(
                username=username,
                name=name or "",
                tag=tag or "",
                source=source or "",
                status="pending",
                last_account_id=account_id,
                last_contacted_at=last_contacted_at,
            )
        except Exception:
            self._db.conn.rollback()
            return None
