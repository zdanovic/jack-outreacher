"""
Structured event logging support for the orchestrator.

We intentionally avoid JSON for persistent text logs and instead use
simple tab-separated values (TSV) which are:
- human-readable,
- easy to import into spreadsheets and analytics tools,
- robust against occasional special characters.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Dict, Any


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))

_env_data_dir = os.getenv("DATA_DIR")
_default_external = os.path.abspath(os.path.join(PROJECT_ROOT, "..", "data"))
if _env_data_dir and os.path.isdir(_env_data_dir):
    DATA_DIR = _env_data_dir
elif os.path.isdir(_default_external):
    DATA_DIR = _default_external
else:
    DATA_DIR = os.path.join(PROJECT_ROOT, "data")


class LogsStore:
    """
    Async-friendly, line-oriented event logger.

    Events are written as TSV lines with a fixed set of fields, so that
    they can be easily grepped, tailed and loaded into external tools.
    """

    def __init__(self, path: str | None = None) -> None:
        self._path = path or os.path.join(DATA_DIR, "events.log.tsv")
        self._lock = asyncio.Lock()
        os.makedirs(DATA_DIR, exist_ok=True)
        # Ensure file exists with header.
        if not os.path.exists(self._path):
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(
                    "ts\taccount_id\taction_type\ttarget\tresult\tinfo\n"
                )

    async def log_event(
        self,
        account_id: str,
        action_type: str,
        target: str = "",
        result: str = "ok",
        info: str = "",
    ) -> None:
        """
        Append a single event line. This call is lightweight but still
        uses a lock to keep lines coherent.
        """
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        line = f"{ts}\t{account_id}\t{action_type}\t{target}\t{result}\t{info}\n"
        async with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line)


logs_store = LogsStore()
