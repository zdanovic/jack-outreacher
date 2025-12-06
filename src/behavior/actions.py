from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, Optional


class ActionType(Enum):
    READ_CHANNEL = auto()
    READ_DIALOG = auto()
    JOIN_CHANNEL = auto()
    SEND_WARMUP_MESSAGE = auto()
    SEND_COLD_DM = auto()
    REPLY_MESSAGE = auto()
    IDLE = auto()


@dataclass
class Action:
    """
    Planned action for a specific account.

    In later iterations we will extend this with richer metadata
    (priority, estimated cost, tracing ids, etc.).
    """

    account_id: str
    type: ActionType
    earliest_start_ts: float
    context: Dict[str, Any] | None = None

