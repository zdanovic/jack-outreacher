"""
Utility to validate warmup channel/user lists against Telegram.

- Reads data/warmup_channels.txt and data/warmup_users.txt
- Resolves each username via Telethon using an existing authorised session
- Writes reports (TSV) with resolution status and cleaned lists (only OK usernames)

This is a non-invasive, read-only checker: it never joins/sends, only get_entity/get_messages.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

from src.core.config import load_app_config

# Telethon imports are runtime-only to keep packaging lean.
from telethon import TelegramClient  # type: ignore
from telethon.errors import (  # type: ignore
    FloodWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
    ChannelPrivateError,
    UsernameNotModifiedError,
)
from telethon.tl.types import Channel, User, Chat  # type: ignore


DATA_DIR = Path(os.getenv("DATA_DIR") or Path(__file__).resolve().parents[1] / "data").resolve()
CHANNELS_PATH = DATA_DIR / "warmup_channels.txt"
USERS_PATH = DATA_DIR / "warmup_users.txt"
REPORT_CHANNELS = DATA_DIR / "warmup_channels.report.tsv"
REPORT_USERS = DATA_DIR / "warmup_users.report.tsv"
CLEAN_CHANNELS = DATA_DIR / "warmup_channels.cleaned.txt"
CLEAN_USERS = DATA_DIR / "warmup_users.cleaned.txt"


@dataclass
class CheckResult:
    username: str
    kind: str
    status: str
    info: str = ""
    last_message_ts: str | None = None


def _load_usernames(path: Path) -> List[str]:
    if not path.exists():
        return []
    items: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            items.append(s.lstrip("@"))
    # Deduplicate while preserving order
    seen = set()
    deduped: List[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


async def _check_username(client: TelegramClient, username: str) -> CheckResult:
    try:
        entity = await client.get_entity(username)
        kind = "channel" if isinstance(entity, Channel) else "user" if isinstance(entity, User) else "chat" if isinstance(entity, Chat) else "unknown"
        last_ts = None
        try:
            msg = await client.get_messages(entity, limit=1)
            if msg:
                last_ts = str(msg[0].date)
        except Exception:
            pass
        return CheckResult(username=username, kind=kind, status="ok", last_message_ts=last_ts, info="")
    except UsernameNotOccupiedError:
        return CheckResult(username=username, kind="unknown", status="not_found", info="Username not occupied")
    except UsernameInvalidError:
        return CheckResult(username=username, kind="unknown", status="invalid", info="Invalid username format")
    except UsernameNotModifiedError:
        return CheckResult(username=username, kind="unknown", status="invalid", info="Username not modified/invalid")
    except ChannelPrivateError:
        return CheckResult(username=username, kind="channel", status="private", info="Private/requires join")
    except FloodWaitError as e:
        return CheckResult(username=username, kind="unknown", status="floodwait", info=f"{getattr(e, 'seconds', '?')}s")
    except Exception as e:
        return CheckResult(username=username, kind="unknown", status="error", info=str(e))


async def _check_list(client: TelegramClient, items: Iterable[str], rps: float = 1.0) -> List[CheckResult]:
    results: List[CheckResult] = []
    delay = 1.0 / max(rps, 0.1)
    for username in items:
        start = time.time()
        res = await _check_username(client, username)
        results.append(res)
        elapsed = time.time() - start
        sleep_for = max(0.0, delay - elapsed)
        if sleep_for:
            await asyncio.sleep(sleep_for)
    return results


def _pick_account() -> Tuple[str, int, str, str]:
    """
    Select the first account that has a session file present.
    Returns (session_name, api_id, api_hash, phone).
    """
    cfg = load_app_config()
    for acc in cfg.accounts:
        session_path = Path(acc.session_name).expanduser()
        if session_path.exists():
            return (str(session_path), acc.api_id, acc.api_hash, acc.phone)
    raise RuntimeError("No account session found; ensure at least one account is logged in.")


def _write_report(path: Path, results: List[CheckResult]) -> None:
    lines = ["username\tkind\tstatus\tlast_message_ts\tinfo"]
    for r in results:
        info = (r.info or "").replace("\t", " ")[:200]
        lines.append(f"{r.username}\t{r.kind}\t{r.status}\t{r.last_message_ts or ''}\t{info}")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_clean(path: Path, results: List[CheckResult]) -> None:
    ok = [r.username for r in results if r.status == "ok"]
    path.write_text("\n".join(ok) + ("\n" if ok else ""), encoding="utf-8")


async def main() -> None:
    session_name, api_id, api_hash, phone = _pick_account()
    print(f"[check] Using session {session_name} ({phone})")
    channels = _load_usernames(CHANNELS_PATH)
    users = _load_usernames(USERS_PATH)
    print(f"[check] Channels: {len(channels)}, Users: {len(users)}")

    async with TelegramClient(session_name, api_id, api_hash) as client:
        chan_results = await _check_list(client, channels, rps=1.0)
        user_results = await _check_list(client, users, rps=1.0)

    _write_report(REPORT_CHANNELS, chan_results)
    _write_report(REPORT_USERS, user_results)
    _write_clean(CLEAN_CHANNELS, chan_results)
    _write_clean(CLEAN_USERS, user_results)

    summary = {
        "channels_ok": sum(1 for r in chan_results if r.status == "ok"),
        "channels_bad": sum(1 for r in chan_results if r.status != "ok"),
        "users_ok": sum(1 for r in user_results if r.status == "ok"),
        "users_bad": sum(1 for r in user_results if r.status != "ok"),
    }
    print(f"[done] Summary: {summary}")
    print(f"[files] {REPORT_CHANNELS}, {REPORT_USERS}, {CLEAN_CHANNELS}, {CLEAN_USERS}")


if __name__ == "__main__":
    asyncio.run(main())
