from __future__ import annotations

import os
import random
import time
from datetime import datetime
from typing import Iterable, List, Dict, Any
from zoneinfo import ZoneInfo

from .actions import Action, ActionType
from ..storage.settings_store import settings_store
from ..core.config import AccountConfig

try:
    # DEFAULT_CHANNELS provides a diverse set of public channels that are
    # safe to read for warmup scenarios.
    from ..prompts.defaults import DEFAULT_CHANNELS  # type: ignore
except Exception:  # pragma: no cover - fallback if prompt is not available
    DEFAULT_CHANNELS = [
        "telegram", "durov", "bbcnews", "nytimes", "techcrunch", "openai"
    ]

try:
    # DEFAULT_USERS_OR_BOTS contains popular bots/users; we may use a
    # subset for occasional dialog reads to add variety.
    from ..prompts.defaults import DEFAULT_USERS_OR_BOTS  # type: ignore
except Exception:  # pragma: no cover
    DEFAULT_USERS_OR_BOTS = ["BotFather", "SpamBot", "wiki"]


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


# Default timing parameters for warmup planning (seconds).
WARMUP_BATCH_INTERVAL_MIN = 300.0   # 5 minutes
WARMUP_BATCH_INTERVAL_MAX = 900.0   # 15 minutes
WARMUP_ACTION_JITTER_MIN = 10.0
WARMUP_ACTION_JITTER_MAX = 120.0


class WarmupEngine:
    """
    Generates low‑risk warmup actions (reading channels, idle gaps).

    The goal is to make each account periodically exhibit benign behaviour
    similar to that of a regular user: occasionally opening channels and
    spending some time "reading" them, interleaved with idle periods.
    """

    def __init__(self, accounts: Iterable[Any]) -> None:
        # Accept AccountConfig or plain ids.
        self._account_ids: List[str] = []
        self._account_tz: Dict[str, str] = {}
        for acc in accounts:
            if isinstance(acc, AccountConfig):
                self._account_ids.append(acc.id)
                if acc.timezone:
                    self._account_tz[acc.id] = acc.timezone
            else:
                self._account_ids.append(str(acc))

        self._channels: List[str] = list(DEFAULT_CHANNELS)
        self._bots: List[str] = list(DEFAULT_USERS_OR_BOTS)

        self._load_extra_sources()

        # Per-account RNGs and channel sequences to increase divergence
        # between accounts and reduce the chance of similar action traces.
        self._rngs: Dict[str, random.Random] = {}
        self._channel_sequences: Dict[str, List[str]] = {}
        self._channel_indices: Dict[str, int] = {}
        for acc in self._account_ids:
            rng = random.Random(self._seed_for_account(acc))
            self._rngs[acc] = rng
            seq = self._channels.copy()
            rng.shuffle(seq)
            self._channel_sequences[acc] = seq
            self._channel_indices[acc] = 0
        # Track recent dialog reads to limit frequency.
        self._read_dialog_history: Dict[str, List[float]] = {}

    @staticmethod
    def _seed_for_account(account_id: str) -> int:
        # Stable but distinct seed per account to avoid identical patterns.
        return abs(hash(account_id)) % (2**31)

    def _load_extra_sources(self) -> None:
        """
        Optionally extend default channels and users from text files.

        This allows you to maintain hundreds of real, safe items without
        hard‑coding them in the codebase:
        - data/warmup_channels.txt
        - data/warmup_users.txt

        Each non‑empty, non‑comment line is treated as a channel/username.
        """

        def _load_list(path: str) -> List[str]:
            if not os.path.exists(path):
                return []
            items: List[str] = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#"):
                        continue
                    items.append(s)
            return items

        extra_channels = _load_list(os.path.join(DATA_DIR, "warmup_channels.txt"))
        extra_users = _load_list(os.path.join(DATA_DIR, "warmup_users.txt"))

        if extra_channels:
            merged = list(dict.fromkeys(self._channels + extra_channels))
            self._channels = merged
        if extra_users:
            merged = list(dict.fromkeys(self._bots + extra_users))
            self._bots = merged

    def initial_actions(self) -> list[Action]:
        """
        Produce a minimal set of IDLE actions so that accounts do not
        immediately start performing network operations on startup.
        """
        now = time.time()
        actions: list[Action] = []
        for acc_id in self._account_ids:
            jitter = random.uniform(5.0, 30.0)
            actions.append(
                Action(
                    account_id=acc_id,
                    type=ActionType.IDLE,
                    earliest_start_ts=now + jitter,
                    context=None,
                )
            )
        return actions

    def plan_warmup_batch_for_account(self, account_id: str) -> list[Action]:
        """
        Plan a small batch of warmup actions for a single account.

        For now this consists of:
        - one READ_CHANNEL action for a random channel
        - optionally a READ_DIALOG (if allowed)
        - followed by an IDLE gap
        """
        if not self._channels:
            return []

        now = time.time()
        actions: list[Action] = []

        rng = self._rngs.get(account_id)
        if rng is None:
            rng = random.Random(self._seed_for_account(account_id))
            self._rngs[account_id] = rng

        # Decide scenario: mostly channels, sometimes a bot dialog (throttled).
        warm = settings_store.get_settings().get("warmup", {})
        bot_chance = float(warm.get("bot_read_chance", 0.2))
        use_bot = self._bots and rng.random() < bot_chance
        # Throttle dialog reads per hour.
        max_dialogs_per_hour = int(warm.get("max_read_dialogs_per_hour", 2))
        now_ts = time.time()
        hist = self._read_dialog_history.get(account_id, [])
        hist = [ts for ts in hist if now_ts - ts < 3600]
        self._read_dialog_history[account_id] = hist
        if len(hist) >= max_dialogs_per_hour:
            use_bot = False

        # Primary action: READ_CHANNEL from per‑account shuffled sequence.
        seq = self._channel_sequences.get(account_id) or self._channels
        idx = self._channel_indices.get(account_id, 0) % len(seq)
        channel = seq[idx]
        self._channel_indices[account_id] = (idx + 1) % len(seq)

        aj_min = float(warm.get("action_jitter_min", WARMUP_ACTION_JITTER_MIN))
        aj_max = float(warm.get("action_jitter_max", WARMUP_ACTION_JITTER_MAX))

        read_delay = rng.uniform(aj_min, aj_max)
        idle_delay = read_delay + rng.uniform(aj_min, aj_max)

        actions.append(
            Action(
                account_id=account_id,
                type=ActionType.READ_CHANNEL,
                earliest_start_ts=now + read_delay,
                context={"channel": channel},
            )
        )

        # Optional secondary action: read a bot/user dialog to diversify access patterns.
        if use_bot and rng.random() < bot_chance:
            bot = rng.choice(self._bots)
            bot_delay = read_delay + rng.uniform(5.0, 60.0)
            actions.append(
                Action(
                    account_id=account_id,
                    type=ActionType.READ_DIALOG,
                    earliest_start_ts=now + bot_delay,
                    context={"peer": bot},
                )
            )
            self._read_dialog_history[account_id].append(now_ts + bot_delay)

        actions.append(
            Action(
                account_id=account_id,
                type=ActionType.IDLE,
                earliest_start_ts=now + idle_delay,
                context=None,
            )
        )
        return actions

    def next_batch_interval(self) -> float:
        """
        Return a random delay until the next warmup planning cycle.
        """
        warm = settings_store.get_settings().get("warmup", {})
        # Use Belgrade TZ as default; if any account has a timezone set, use the first one.
        tzname = None
        if self._account_tz:
            tzname = list(self._account_tz.values())[0]
        tz = ZoneInfo(tzname or "Europe/Belgrade")
        hour = datetime.now(tz).hour
        quiet_start = int(warm.get("quiet_hours_start", 0))
        quiet_end = int(warm.get("quiet_hours_end", 7))
        in_quiet = quiet_start <= hour < quiet_end if quiet_start < quiet_end else (hour >= quiet_start or hour < quiet_end)

        if in_quiet:
            bmin = float(warm.get("night_batch_interval_min", WARMUP_BATCH_INTERVAL_MIN * 2))
            bmax = float(warm.get("night_batch_interval_max", WARMUP_BATCH_INTERVAL_MAX * 2))
        else:
            bmin = float(warm.get("batch_interval_min", WARMUP_BATCH_INTERVAL_MIN))
            bmax = float(warm.get("batch_interval_max", WARMUP_BATCH_INTERVAL_MAX))
        return random.uniform(bmin, bmax)
