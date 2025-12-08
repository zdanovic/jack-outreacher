from __future__ import annotations

import json
from threading import Lock
from typing import Any, Dict

from .state_db import get_state_db


DEFAULT_SETTINGS: Dict[str, Any] = {
    "limits": {
        "max_cold_per_account_per_day": 15,
        "max_cold_global_per_day": 80,
        "max_concurrent_heavy_actions": 2,
        "min_cold_interval_seconds": 0,
        "max_cold_per_hour_per_account": 0,
        "mode": "conservative",
    },
    "warmup": {
        "batch_interval_min": 300.0,
        "batch_interval_max": 900.0,
        "night_batch_interval_min": 900.0,
        "night_batch_interval_max": 1800.0,
        "action_jitter_min": 10.0,
        "action_jitter_max": 120.0,
        "bot_read_chance": 0.2,
        "quiet_hours_start": 0,   # local hour inclusive
        "quiet_hours_end": 7,     # local hour exclusive
        "max_read_dialogs_per_hour": 2,
    },
    "outreach": {
        "enabled": True,
        "send_interval_min": 900.0,
        "send_interval_max": 3600.0,
        "max_per_batch": 1,
    },
    "replies": {
        "enabled": True,
    },
    "accounts": {
        # account_id -> {"enabled": True/False}
        "overrides": {}
    },
}


class SettingsStore:
    """
    Simple JSON settings persisted in SQLite (settings table).

    Values are merged over DEFAULT_SETTINGS. Updates are deep-merged.
    """

    def __init__(self) -> None:
        self._db = get_state_db()
        self._lock = Lock()
        self._init_table()

    def _refresh_db(self) -> None:
        """
        Rebind to the current state DB in case callers changed DB_PATH
        (common in tests). Ensures settings table exists in the new DB.
        """
        self._db = get_state_db()
        self._init_table()

    def _init_table(self) -> None:
        cur = self._db.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        self._db.conn.commit()

    def _merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(base)
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(result.get(k), dict):
                result[k] = self._merge(result[k], v)
            else:
                result[k] = v
        return result

    def _load_raw(self) -> Dict[str, Any]:
        cur = self._db.conn.cursor()
        cur.execute("SELECT key, value FROM settings;")
        rows = cur.fetchall()
        saved: Dict[str, Any] = {}
        for key, value in rows:
            try:
                saved[key] = json.loads(value)
            except Exception:
                continue
        return saved

    def get_settings(self) -> Dict[str, Any]:
        with self._lock:
            self._refresh_db()
            saved = self._load_raw()
            merged = self._merge(DEFAULT_SETTINGS, saved)
            return merged

    def update_settings(self, partial: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep-merge `partial` into current settings and persist.
        """
        with self._lock:
            self._refresh_db()
            current = self._merge(DEFAULT_SETTINGS, self._load_raw())
            new_settings = self._merge(current, partial)
            cur = self._db.conn.cursor()
            for key, section in new_settings.items():
                cur.execute(
                    """
                    INSERT INTO settings (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value;
                    """,
                    (key, json.dumps(section)),
                )
            self._db.conn.commit()
        return new_settings


settings_store = SettingsStore()
