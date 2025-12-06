import asyncio
from dataclasses import dataclass
from typing import Optional, Any

from ..core.config import AccountConfig


@dataclass
class TelegramClientWrapper:
    """
    Lightweight wrapper storing both config and client instance.

    We keep the type of `client` as `Any` here to avoid importing
    Telethon at module import time. This makes it possible to run
    smoke tests even if Telethon is not fully installed. At runtime
    `client` will always be a `telethon.TelegramClient` instance.
    """

    config: AccountConfig
    client: Any


class TelegramClientAdapter:
    """
    Manages TelegramClient instances for all orchestrated accounts.

    For now this focuses on connection lifecycle and exposes the
    raw Telethon client for higher‑level components. Later we can
    add convenience methods for common actions.
    """

    def __init__(self) -> None:
        self._clients: dict[str, TelegramClientWrapper] = {}
        self._lock = asyncio.Lock()

    async def start_account(self, cfg: AccountConfig) -> TelegramClientWrapper:
        """
        Create and start a TelegramClient for a given account config.

        This expects that the session is already authorised; it will
        not prompt for login codes. If the session is invalid, the
        caller should catch the corresponding Telethon errors and
        mark the account as NEED_RELOGIN.
        """
        # Lazy import so that environments without Telethon can still
        # import this module (useful for tests and tooling).
        from telethon import TelegramClient  # type: ignore

        async with self._lock:
            if cfg.id in self._clients:
                return self._clients[cfg.id]

            # For now we do not wire proxies; this will be added when
            # the shared proxy management layer is extracted.
            client = TelegramClient(cfg.session_name, cfg.api_id, cfg.api_hash)
            await client.connect()

            wrapper = TelegramClientWrapper(config=cfg, client=client)
            self._clients[cfg.id] = wrapper
            return wrapper

    async def get_client(self, account_id: str) -> Optional[Any]:
        async with self._lock:
            wrapper = self._clients.get(account_id)
            return wrapper.client if wrapper else None

    async def stop_account(self, account_id: str) -> None:
        async with self._lock:
            wrapper = self._clients.pop(account_id, None)
        if wrapper is not None:
            await wrapper.client.disconnect()
