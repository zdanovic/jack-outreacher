"""
Control helpers for orchestrator management and future UI integration.

This module exposes a thin API over AccountManager and GlobalState
so that a CLI tool, HTTP service, or other UI layer can:
- inspect account statuses and basic metrics,
- pause/resume specific accounts.
"""

from typing import Dict

from ..core.state import global_state, AccountStatus
from ..telegram.accounts import AccountManager
from ..core.config import AppConfig


async def get_account_statuses(app_config: AppConfig) -> Dict[str, AccountStatus]:
    """
    Return a mapping of account_id -> AccountStatus for all accounts
    defined in the current AppConfig.
    """
    result: Dict[str, AccountStatus] = {}
    for acc in app_config.accounts:
        status = await global_state.get_status(acc.id)
        result[acc.id] = status
    return result


async def pause_account(manager: AccountManager, account_id: str) -> None:
    await manager.pause_account(account_id)


async def resume_account(manager: AccountManager, account_id: str) -> None:
    await manager.resume_account(account_id)

