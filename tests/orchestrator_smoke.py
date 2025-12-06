"""
Lightweight smoke tests for the new orchestrator layer.

These tests are intentionally conservative:
- they do not touch real Telegram sessions,
- they do not require any external network calls,
- they only verify that core components can be imported and initialised.
"""

import asyncio
import os
import sys

# Ensure project root is on sys.path so that `src` can be imported
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.core.config import load_app_config, AppConfig
from src.telegram.client_adapter import TelegramClientAdapter
from src.telegram.accounts import AccountManager
from src.behavior.scheduler import GlobalScheduler


def test_config_loads() -> AppConfig:
    cfg = load_app_config()
    assert isinstance(cfg, AppConfig)
    assert cfg.limits is not None
    assert cfg.behavior is not None
    assert cfg.ai is not None
    # accounts list may be empty on a clean setup – this is acceptable
    assert isinstance(cfg.accounts, list)
    return cfg


async def test_account_manager_init(cfg: AppConfig) -> None:
    adapter = TelegramClientAdapter()
    scheduler = GlobalScheduler()
    manager = AccountManager(app_config=cfg, client_adapter=adapter, scheduler=scheduler)
    # Should not raise even if there are zero accounts configured.
    manager.init_workers()


if __name__ == "__main__":
    cfg_obj = test_config_loads()
    asyncio.run(test_account_manager_init(cfg_obj))
    print("orchestrator_smoke: OK")
