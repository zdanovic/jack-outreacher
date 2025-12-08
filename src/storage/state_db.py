"""
SQLite-backed state store for leads and dialogs.

Using a single local SQLite database provides a robust and efficient
way to persist state without rewriting CSV/JSON files on every update.
"""

from __future__ import annotations

import os
import sqlite3
from threading import Lock


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

# Prefer external DATA_DIR (e.g., /app/data bind-mounted). Fallback to local src/data.
_env_data_dir = os.getenv("DATA_DIR")
_default_external = os.path.abspath(os.path.join(PROJECT_ROOT, "..", "data"))
if _env_data_dir and os.path.isdir(_env_data_dir):
    DATA_DIR = _env_data_dir
elif os.path.isdir(_default_external):
    DATA_DIR = _default_external
else:
    DATA_DIR = os.path.join(PROJECT_ROOT, "data")

DB_PATH = os.path.join(DATA_DIR, "orchestrator_state.db")

_db_lock = Lock()
_db_instance: "StateDB | None" = None


class StateDB:
    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        # Leads table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                username TEXT PRIMARY KEY,
                name TEXT,
                first_name TEXT,
                last_name TEXT,
                bio TEXT,
                tag TEXT,
                source TEXT,
                status TEXT,
                last_account_id TEXT,
                last_contacted_at TEXT,
                fail_reason TEXT
            );
            """
        )
        # Dialogs table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS dialogs (
                username TEXT PRIMARY KEY,
                peer_id INTEGER,
                is_lead INTEGER,
                lead_id TEXT,
                first_seen_at TEXT,
                last_seen_at TEXT,
                last_account_id TEXT,
                manual_replied_at TEXT
            );
            """
        )
        # Metrics table (daily per account)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                date TEXT NOT NULL,
                account_id TEXT NOT NULL,
                cold_sent INTEGER DEFAULT 0,
                cold_failed INTEGER DEFAULT 0,
                replies_received INTEGER DEFAULT 0,
                hot_leads INTEGER DEFAULT 0,
                warm_leads INTEGER DEFAULT 0,
                cold_leads INTEGER DEFAULT 0,
                floodwait_events INTEGER DEFAULT 0,
                warmup_actions INTEGER DEFAULT 0,
                PRIMARY KEY (date, account_id)
            );
            """
        )
        # Messages table (per account and username)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                username TEXT NOT NULL,
                direction TEXT NOT NULL,
                text TEXT,
                ts TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_messages_account_user_ts
            ON messages(account_id, username, ts);
            """
        )

        # Pending outbox for queued sends (e.g., offline/login issues).
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                username TEXT NOT NULL,
                direction TEXT NOT NULL,
                text TEXT,
                status TEXT DEFAULT 'pending', -- pending/failed/sent
                fail_reason TEXT,
                created_at TEXT,
                send_after TEXT,
                expires_at TEXT
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_outbox_account_status ON pending_outbox(account_id, status);")

        # Attachments metadata (files stored on disk).
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_name TEXT,
                stored_path TEXT,
                mime_type TEXT,
                size_bytes INTEGER,
                created_at TEXT
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_attachments_created_at ON attachments(created_at);")

        # Runtime account state for cross-process visibility (API/UI vs worker).
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS account_runtime (
                account_id TEXT PRIMARY KEY,
                status TEXT,
                last_error TEXT,
                ban_reason TEXT,
                floodwait_until REAL
            );
            """
        )

        # Lightweight migrations for existing DBs.
        try:
            cur.execute("ALTER TABLE dialogs ADD COLUMN manual_replied_at TEXT;")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE leads ADD COLUMN fail_reason TEXT;")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE leads ADD COLUMN first_name TEXT;")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE leads ADD COLUMN last_name TEXT;")
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE leads ADD COLUMN bio TEXT;")
        except Exception:
            pass

        self.conn.commit()

    # -------- Runtime state helpers (statuses/errors/floodwait) --------
    def upsert_account_runtime(
        self,
        account_id: str,
        status: str | None = None,
        last_error: str | None = None,
        ban_reason: str | None = None,
        floodwait_until: float | None = None,
    ) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO account_runtime (account_id, status, last_error, ban_reason, floodwait_until)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                status=excluded.status,
                last_error=excluded.last_error,
                ban_reason=excluded.ban_reason,
                floodwait_until=excluded.floodwait_until;
            """,
            (account_id, status, last_error, ban_reason, floodwait_until),
        )
        self.conn.commit()

    def get_account_runtime(self, account_id: str) -> dict | None:
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT status, last_error, ban_reason, floodwait_until FROM account_runtime WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if not row:
            return None
        status, last_error, ban_reason, floodwait_until = row
        return {
            "status": status,
            "last_error": last_error,
            "ban_reason": ban_reason,
            "floodwait_until": floodwait_until,
        }


def get_state_db() -> StateDB:
    global _db_instance
    with _db_lock:
        if _db_instance is None:
            _db_instance = StateDB(DB_PATH)
        return _db_instance
