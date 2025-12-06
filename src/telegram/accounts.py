import asyncio
import logging
import random
from typing import Dict, Optional

from ..core.config import AccountConfig, AppConfig
from ..core.state import AccountStatus, global_state
from .client_adapter import TelegramClientAdapter
from ..behavior.scheduler import GlobalScheduler
from ..behavior.actions import ActionType
from ..core.metrics import metrics_store
from ..storage.logs_store import logs_store
from ..storage.leads_store import LeadsStore
from ..storage.dialogs_store import DialogsStore, DialogMeta
from ..storage.messages_store import messages_store
from ..core.rate_limiter import RateLimiter
from ..ai.client import AIClient
from ..prompts.opening import OPENING_PROMPT
from ..prompts.account_legends import ACCOUNT_LEGENDS
from ..behavior.reply_engine import ReplyEngine


logger = logging.getLogger("Orchestrator.Accounts")


class AccountWorker:
    """
    Per‑account worker that executes scheduled actions.

    For now this is a thin loop that connects the account and then
    idles. Action scheduling will be plugged in once the scheduler
    and engines are in place.
    """

    def __init__(
        self,
        cfg: AccountConfig,
        client_adapter: TelegramClientAdapter,
        startup_jitter_sec: float = 60.0,
        scheduler: Optional[GlobalScheduler] = None,
    ) -> None:
        self.cfg = cfg
        self.client_adapter = client_adapter
        self.startup_jitter_sec = startup_jitter_sec
        self.scheduler = scheduler
        self.leads_store: Optional[LeadsStore] = None
        self.dialogs_store: Optional[DialogsStore] = None
        self.rate_limiter: Optional[RateLimiter] = None
        self.ai_client: Optional[AIClient] = None
        self.reply_engine: Optional[ReplyEngine] = None
        self._task: Optional[asyncio.Task] = None
        self._stopped = asyncio.Event()
        self._client = None

    async def run(self) -> None:
        """
        Main loop for this account. In the first iteration we only:

        - wait for random jitter
        - connect the client
        - keep the connection alive until stopped
        """
        # Randomised startup delay to avoid simultaneous logins.
        delay = random.uniform(0, self.startup_jitter_sec)
        logger.info("Account %s: startup jitter %.1fs", self.cfg.id, delay)
        await asyncio.sleep(delay)

        try:
            wrapper = await self.client_adapter.start_account(self.cfg)
            self._client = wrapper.client
            logger.info("Account %s: connected as %s", self.cfg.id, wrapper.config.phone)
            await global_state.set_status(self.cfg.id, AccountStatus.ACTIVE)
            # Attach reply handler if available.
            if self.reply_engine is not None and self._client is not None:
                self.reply_engine.attach_to_client(self._client, self.cfg.id)
        except Exception as e:
            logger.error("Account %s: unexpected error during connect: %s", self.cfg.id, e)
            await global_state.set_status(self.cfg.id, AccountStatus.PAUSED)
            return

        # Idle / action loop – later this will execute real actions from the scheduler.
        while not self._stopped.is_set():
            if self.scheduler is None:
                # No scheduler wired yet – just keep the connection warm.
                await asyncio.sleep(5.0)
                continue

            action = await self.scheduler.next_action(self.cfg.id)
            if action is None:
                # Nothing planned – short idle before checking again.
                await asyncio.sleep(5.0)
                continue

            if action.type is ActionType.IDLE:
                # IDLE is represented purely by timing; no extra work needed.
                continue

            if self._client is None:
                logger.warning("Account %s: client not available to execute action %s", self.cfg.id, action.type)
                continue

            if action.type is ActionType.READ_CHANNEL:
                await self._handle_read_channel(action.context or {})
            elif action.type is ActionType.READ_DIALOG:
                await self._handle_read_dialog(action.context or {})
            elif action.type is ActionType.SEND_COLD_DM:
                await self._handle_send_cold_dm(action.context or {})
            else:
                # Other action types will be implemented as engines are wired in.
                logger.debug(
                    "Account %s: received action %s but no handler is implemented yet.",
                    self.cfg.id,
                    action.type.name,
                )

        logger.info("Account %s: worker stopping.", self.cfg.id)

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._task = loop.create_task(self.run())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            await self._task
        self._client = None

    async def _handle_read_channel(self, context: dict) -> None:
        """
        Warmup helper: simulate opening a public channel and reading
        a handful of recent messages.
        """
        channel = context.get("channel")
        if not channel or self._client is None:
            return

        try:
            # Lazy import to avoid hard dependency during tests.
            from telethon.errors import RPCError  # type: ignore
        except Exception:  # pragma: no cover
            RPCError = Exception  # type: ignore

        try:
            entity = await self._client.get_entity(channel)
            # Get a small number of recent messages.
            limit = 10
            await self._client.get_messages(entity, limit=limit)
            # Brief local pause to emulate reading time.
            await asyncio.sleep(1.0)
            logger.debug("Account %s: warmup READ_CHANNEL for %s", self.cfg.id, channel)
            await metrics_store.incr(self.cfg.id, "warmup_actions", 1)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="READ_CHANNEL",
                target=str(channel),
                result="ok",
            )
        except RPCError as e:  # type: ignore
            logger.debug("Account %s: RPC error during READ_CHANNEL %s: %s", self.cfg.id, channel, e)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="READ_CHANNEL",
                target=str(channel),
                result="error",
                info=str(e),
            )
        except Exception as e:
            logger.debug("Account %s: error during READ_CHANNEL %s: %s", self.cfg.id, channel, e)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="READ_CHANNEL",
                target=str(channel),
                result="error",
                info=str(e),
            )

    async def _handle_read_dialog(self, context: dict) -> None:
        """
        Warmup helper: simulate opening a dialog with a bot or well‑known
        user and reading a handful of recent messages.
        """
        peer = context.get("peer")
        if not peer or self._client is None:
            return

        try:
            from telethon.errors import RPCError  # type: ignore
        except Exception:  # pragma: no cover
            RPCError = Exception  # type: ignore

        try:
            entity = await self._client.get_entity(peer)
            limit = 5
            await self._client.get_messages(entity, limit=limit)
            await asyncio.sleep(1.0)
            logger.debug("Account %s: warmup READ_DIALOG for %s", self.cfg.id, peer)
            await metrics_store.incr(self.cfg.id, "warmup_actions", 1)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="READ_DIALOG",
                target=str(peer),
                result="ok",
            )
        except RPCError as e:  # type: ignore
            logger.debug("Account %s: RPC error during READ_DIALOG %s: %s", self.cfg.id, peer, e)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="READ_DIALOG",
                target=str(peer),
                result="error",
                info=str(e),
            )

    async def _handle_send_cold_dm(self, context: dict) -> None:
        """
        Send a simple cold DM message to a reserved lead.
        Uses AI‑generated first‑touch text when possible, falling back
        to a static template if AI is unavailable.
        """
        if self._client is None:
            return

        username = context.get("username")
        name = context.get("name") or ""
        if not username:
            return

        # Optional safeguard: re-check rate limit before sending.
        if self.rate_limiter is not None:
            can_send = await self.rate_limiter.can_send_cold(self.cfg.id)
            if not can_send:
                await logs_store.log_event(
                    account_id=self.cfg.id,
                    action_type="SEND_COLD_DM",
                    target=str(username),
                    result="skipped",
                    info="rate_limit_reached",
                )
                return

        # Build AI first‑touch message if an AI client is available.
        text = None
        if self.ai_client is not None:
            legend = ACCOUNT_LEGENDS.get(
                getattr(self.cfg, "session_name", ""),
                {
                    "role": "IT Recruitment Consultant",
                    "persona": "representing a boutique IT recruitment agency",
                    "style": "friendly, professional",
                },
            )
            account_role = legend.get("role", "Consultant")
            account_persona = legend.get("persona", "")
            account_style = legend.get("style", "friendly")

            language_tag = (context.get("tag") or "eng").lower()
            if language_tag.startswith("ru"):
                language = "Russian"
            else:
                language = "English"

            first_name = name or username
            user_prompt = (
                f"As a {account_role} who is {account_persona}, write a short, casual, and natural-sounding "
                f"first message to this potential lead in {language}.\n"
                f"Your tone should be {account_style}.\n\n"
                f"**Lead's Information:**\n"
                f"- First Name: {first_name or 'N/A'}\n"
                f"- Last Name: N/A\n"
                f"- Professional Bio/Info: N/A\n"
                f"- Display Name in Chat: N/A\n"
                f"- Preferred Language Code: {language_tag}\n\n"
                f"**TASK:** Generate ONLY the message text. Follow all instructions in the system prompt below precisely."
            )

            messages = [
                {"role": "system", "content": OPENING_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            ai_text = await self.ai_client.chat(messages, max_tokens=80, temperature=0.7)
            if ai_text:
                text = ai_text.strip()

        # Conservative fallback message if AI is not available.
        if not text:
            text = f"Hi {name or username}, wanted to briefly connect here."

        try:
            await self._client.send_message(username, text)
            await metrics_store.incr(self.cfg.id, "cold_sent", 1)
            messages_store.add_message(
                account_id=self.cfg.id,
                username=username,
                direction="out",
                text=text,
                ts=None,
            )
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="SEND_COLD_DM",
                target=str(username),
                result="ok",
            )
            if self.rate_limiter is not None:
                await self.rate_limiter.register_cold_sent(self.cfg.id)
            if self.leads_store is not None:
                self.leads_store.mark_contacted(username, self.cfg.id)
            if self.dialogs_store is not None:
                self.dialogs_store.upsert(
                    DialogMeta(
                        username=username,
                        is_lead=True,
                        last_account_id=self.cfg.id,
                    )
                )
        except Exception as e:
            await metrics_store.incr(self.cfg.id, "cold_failed", 1)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="SEND_COLD_DM",
                target=str(username),
                result="error",
                info=str(e),
            )
            # Optionally, we could re-open the lead for future attempts.
            if self.leads_store is not None:
                self.leads_store.update_status(username, "new")
        except Exception as e:
            logger.debug("Account %s: error during READ_DIALOG %s: %s", self.cfg.id, peer, e)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="READ_DIALOG",
                target=str(peer),
                result="error",
                info=str(e),
            )


class AccountManager:
    """
    Coordinates all account workers for the orchestrator.

    Responsible for:
    - creating workers for enabled accounts
    - starting / stopping them
    - reacting to global shutdown
    """

    def __init__(
        self,
        app_config: AppConfig,
        client_adapter: TelegramClientAdapter,
        scheduler: Optional[GlobalScheduler] = None,
    ) -> None:
        self.app_config = app_config
        self.client_adapter = client_adapter
        self.scheduler = scheduler
        self._workers: Dict[str, AccountWorker] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def init_workers(
        self,
        leads_store: Optional[LeadsStore] = None,
        dialogs_store: Optional[DialogsStore] = None,
        rate_limiter: Optional[RateLimiter] = None,
        ai_client: Optional[AIClient] = None,
        reply_engine: Optional[ReplyEngine] = None,
    ) -> None:
        for cfg in self.app_config.accounts:
            if cfg.id in self._workers:
                continue
            worker = AccountWorker(
                cfg=cfg,
                client_adapter=self.client_adapter,
                scheduler=self.scheduler,
            )
            worker.leads_store = leads_store
            worker.dialogs_store = dialogs_store
            worker.rate_limiter = rate_limiter
            worker.ai_client = ai_client
            worker.reply_engine = reply_engine
            self._workers[cfg.id] = worker

    def start_all(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        for worker in self._workers.values():
            worker.start(loop)

    async def stop_all(self) -> None:
        for worker in self._workers.values():
            await worker.stop()

    async def pause_account(self, account_id: str) -> None:
        """
        Stop a single account worker. Intended to be called from
        control/UI layer when an operator pauses an account.
        """
        worker = self._workers.get(account_id)
        if worker:
            await worker.stop()
        await global_state.set_status(account_id, AccountStatus.PAUSED)

    async def resume_account(self, account_id: str) -> None:
        """
        Resume a previously paused account by starting a new worker.
        The event loop is taken from the last start_all() call.
        """
        if self._loop is None:
            raise RuntimeError("Event loop is not initialised in AccountManager.")
        if account_id in self._workers:
            # If worker exists but was stopped, recreate it.
            cfg = next((c for c in self.app_config.accounts if c.id == account_id), None)
            if cfg is None:
                raise KeyError(f"Unknown account id: {account_id}")
            worker = AccountWorker(
                cfg=cfg,
                client_adapter=self.client_adapter,
                scheduler=self.scheduler,
            )
            self._workers[account_id] = worker
        worker = self._workers.get(account_id)
        if worker is None:
            raise KeyError(f"Unknown account id: {account_id}")
        worker.start(self._loop)
        await global_state.set_status(account_id, AccountStatus.ACTIVE)
