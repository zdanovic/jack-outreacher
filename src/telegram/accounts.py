import asyncio
import logging
import random
import time
from datetime import datetime
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
from ..storage.outbox_store import outbox_store
from ..core.rate_limiter import RateLimiter
from ..ai.client import AIClient
from ..prompts.opening import OPENING_PROMPT
from ..prompts.account_legends import ACCOUNT_LEGENDS
from ..behavior.reply_engine import ReplyEngine

try:  # Telethon-specific errors for better status reporting.
    from telethon.errors import (  # type: ignore
        SessionRevokedError,
        AuthKeyUnregisteredError,
        UserDeactivatedBanError,
        UserDeactivatedError,
    )
except Exception:  # pragma: no cover
    class _DummyError(Exception):
        ...

    SessionRevokedError = AuthKeyUnregisteredError = UserDeactivatedBanError = UserDeactivatedError = _DummyError  # type: ignore


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
        startup_jitter_sec: float = 600.0,
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
        self._outbox_flush_interval_sec = 30.0
        self._last_outbox_flush: float = 0.0
        # Periodic lightweight healthcheck to detect dropped sessions.
        self._healthcheck_min_sec = 12 * 60  # randomize to avoid synch spikes
        self._healthcheck_max_sec = 20 * 60
        self._next_healthcheck: float = time.time() + random.uniform(
            self._healthcheck_min_sec, self._healthcheck_max_sec
        )

    async def _mark_session_invalid(self, reason: str) -> None:
        """Set status to NEED_RELOGIN and log a login_state event."""
        await global_state.set_last_error(self.cfg.id, reason)
        await global_state.set_status(self.cfg.id, AccountStatus.NEED_RELOGIN)
        await logs_store.log_event(
            account_id=self.cfg.id,
            action_type="LOGIN_STATE",
            target=self.cfg.phone,
            result="need_relogin",
            info=reason,
        )

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _post_connect_healthcheck(self) -> bool:
        """
        Validate session/auth state after connecting.
        Marks NEED_RELOGIN for missing/invalid sessions and BANNED for deactivated accounts.
        """
        if self._client is None:
            return False

        try:
            authorized = await self._client.is_user_authorized()
        except Exception as e:
            reason = f"authorization_check_failed: {e}"
            await global_state.set_last_error(self.cfg.id, reason)
            await global_state.set_status(self.cfg.id, AccountStatus.NEED_RELOGIN)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="LOGIN_STATE",
                target=self.cfg.phone,
                result="error",
                info=reason,
            )
            return False

        if not authorized:
            reason = "session not authorized; login required"
            await global_state.set_last_error(self.cfg.id, reason)
            await global_state.set_status(self.cfg.id, AccountStatus.NEED_RELOGIN)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="LOGIN_STATE",
                target=self.cfg.phone,
                result="need_relogin",
                info=reason,
            )
            return False

        try:
            me = await self._client.get_me()
        except (UserDeactivatedBanError, UserDeactivatedError) as e:
            await global_state.set_ban_reason(self.cfg.id, str(e))
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="LOGIN_STATE",
                target=self.cfg.phone,
                result="banned",
                info=str(e),
            )
            return False
        except (SessionRevokedError, AuthKeyUnregisteredError) as e:
            reason = f"session invalid: {e}"
            await global_state.set_last_error(self.cfg.id, reason)
            await global_state.set_status(self.cfg.id, AccountStatus.NEED_RELOGIN)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="LOGIN_STATE",
                target=self.cfg.phone,
                result="need_relogin",
                info=reason,
            )
            return False
        except Exception as e:
            reason = f"account_check_failed: {e}"
            await global_state.set_last_error(self.cfg.id, reason)
            await global_state.set_status(self.cfg.id, AccountStatus.PAUSED)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="LOGIN_STATE",
                target=self.cfg.phone,
                result="error",
                info=reason,
            )
            return False

        if me is None:
            reason = "session invalid (no profile info)"
            await global_state.set_last_error(self.cfg.id, reason)
            await global_state.set_status(self.cfg.id, AccountStatus.NEED_RELOGIN)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="LOGIN_STATE",
                target=self.cfg.phone,
                result="need_relogin",
                info=reason,
            )
            return False

        return True

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
            await global_state.set_last_error(self.cfg.id, None)
            await global_state.set_ban_reason(self.cfg.id, None)
            await global_state.set_floodwait(self.cfg.id, None)
            # Post-connect health check to validate session state.
            if not await self._post_connect_healthcheck():
                return
            await global_state.set_status(self.cfg.id, AccountStatus.ACTIVE)
            # Attach reply handler if available.
            if self.reply_engine is not None and self._client is not None:
                self.reply_engine.attach_to_client(self._client, self.cfg.id)
        except Exception as e:
            logger.error("Account %s: unexpected error during connect: %s", self.cfg.id, e)
            await global_state.set_last_error(self.cfg.id, str(e))
            await global_state.set_status(self.cfg.id, AccountStatus.PAUSED)
            return

        # Try to flush any queued manual replies as soon as the account is online.
        await self._flush_pending_outbox()
        self._last_outbox_flush = time.time()

        # Idle / action loop – later this will execute real actions from the scheduler.
        while not self._stopped.is_set():
            if self.scheduler is None:
                # No scheduler wired yet – just keep the connection warm + periodic healthcheck.
                await self._maybe_healthcheck()
                await self._maybe_flush_outbox()
                await asyncio.sleep(5.0)
                continue

            action = await self.scheduler.next_action(self.cfg.id)
            if action is None:
                # Nothing planned – short idle before checking again.
                await self._maybe_healthcheck()
                await self._maybe_flush_outbox()
                await asyncio.sleep(5.0)
                continue

            if action.type is ActionType.IDLE:
                # IDLE is represented purely by timing; no extra work needed.
                await self._maybe_flush_outbox()
                continue

            if self._client is None:
                logger.warning("Account %s: client not available to execute action %s", self.cfg.id, action.type)
                await self._maybe_healthcheck()
                await self._maybe_flush_outbox()
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
            await self._maybe_healthcheck()
            await self._maybe_flush_outbox()

        logger.info("Account %s: worker stopping.", self.cfg.id)

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._task = loop.create_task(self.run())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            await self._task
        self._client = None

    async def _maybe_healthcheck(self) -> None:
        """
        Periodically re-validate session state without spamming Telegram.
        Lightweight: just is_user_authorized() and get_me().
        """
        now = time.time()
        if now < self._next_healthcheck:
            return
        # Schedule next window up-front to avoid tight loops on errors.
        self._next_healthcheck = now + random.uniform(
            self._healthcheck_min_sec, self._healthcheck_max_sec
        )

        if self._client is None:
            return

        try:
            authorized = await self._client.is_user_authorized()
            if not authorized:
                reason = "session not authorized; login required"
                await global_state.set_last_error(self.cfg.id, reason)
                await global_state.set_status(self.cfg.id, AccountStatus.NEED_RELOGIN)
                await logs_store.log_event(
                    account_id=self.cfg.id,
                    action_type="LOGIN_STATE",
                    target=self.cfg.phone,
                    result="need_relogin",
                    info=reason,
                )
                return

            me = await self._client.get_me()
            if me is None:
                reason = "session invalid (no profile info)"
                await global_state.set_last_error(self.cfg.id, reason)
                await global_state.set_status(self.cfg.id, AccountStatus.NEED_RELOGIN)
                await logs_store.log_event(
                    account_id=self.cfg.id,
                    action_type="LOGIN_STATE",
                    target=self.cfg.phone,
                    result="need_relogin",
                    info=reason,
                )
                return

            # Session ok – clear transient error/bans if any.
            await global_state.set_last_error(self.cfg.id, None)
            await global_state.set_ban_reason(self.cfg.id, None)
        except Exception as e:
            # Do not spam telemetry; just mark error and let UI show it.
            await global_state.set_last_error(self.cfg.id, f"healthcheck_failed: {e}")
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="LOGIN_STATE",
                target=self.cfg.phone,
                result="error",
                info=str(e),
            )

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
            # Get a small number of recent messages with read-like pauses.
            msgs = await self._client.get_messages(entity, limit=10)
            if msgs:
                await asyncio.sleep(random.uniform(3.0, 8.0))
                await self._client.get_messages(entity, limit=5)
                await asyncio.sleep(random.uniform(5.0, 12.0))
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
            if hasattr(e, "seconds"):
                await global_state.set_floodwait(self.cfg.id, getattr(e, "seconds", None))
            await global_state.set_last_error(self.cfg.id, str(e))
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="READ_CHANNEL",
                target=str(channel),
                result="error",
                info=str(e),
            )
        except (SessionRevokedError, AuthKeyUnregisteredError) as e:
            reason = f"session invalid: {e}"
            await self._mark_session_invalid(reason)
        except Exception as e:
            logger.debug("Account %s: error during READ_CHANNEL %s: %s", self.cfg.id, channel, e)
            await global_state.set_last_error(self.cfg.id, str(e))
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
            # Quick peek to ensure there is history; skip if empty to avoid poking new bots.
            history = await self._client.get_messages(entity, limit=3)
            if not history:
                return
            # Simulate scrolling/reading with a couple of fetches and pauses.
            await asyncio.sleep(random.uniform(3.0, 8.0))
            await self._client.get_messages(entity, limit=10)
            await asyncio.sleep(random.uniform(5.0, 12.0))
            await self._client.get_messages(entity, limit=5)
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
        except (SessionRevokedError, AuthKeyUnregisteredError) as e:
            reason = f"session invalid: {e}"
            await self._mark_session_invalid(reason)

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

            language_tag = (context.get("tag") or "ru").lower()
            # Мы работаем только по-русски; поле оставляем для совместимости,
            # но принудительно считаем основной язык русским.
            language = "Russian"

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
            text = f"Привет, {name or username}! Решил написать здесь и познакомиться."

        try:
            # Typing delay to mimic human behaviour.
            await asyncio.sleep(random.uniform(1.0, 3.5))
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
        except (SessionRevokedError, AuthKeyUnregisteredError) as e:
            reason = f"session invalid: {e}"
            await self._mark_session_invalid(reason)
        except Exception as e:
            await metrics_store.incr(self.cfg.id, "cold_failed", 1)
            await logs_store.log_event(
                account_id=self.cfg.id,
                action_type="SEND_COLD_DM",
                target=str(username),
                result="error",
                info=str(e),
            )
            if self.leads_store is not None:
                # Keep failed leads marked as failed to avoid immediate reuse.
                self.leads_store.update_status(username, "failed", fail_reason=str(e))

    async def _flush_pending_outbox(self) -> None:
        """
        Deliver queued manual replies for this account when it is online.
        """
        if self._client is None:
            return

        pending = outbox_store.list_pending(self.cfg.id)
        now = datetime.utcnow()
        for item in pending:
            try:
                send_after = datetime.fromisoformat(item["send_after"]) if item.get("send_after") else None
                expires_at = datetime.fromisoformat(item["expires_at"]) if item.get("expires_at") else None
            except Exception:
                send_after = None
                expires_at = None

            if send_after and send_after > now:
                continue
            if expires_at and expires_at < now:
                outbox_store.mark_failed(item["id"], "expired")
                continue

            username = item.get("username")
            text = item.get("text") or ""
            if not username:
                outbox_store.mark_failed(item["id"], "missing_username")
                continue

            try:
                await self._client.send_message(username, text)
                outbox_store.mark_sent(item["id"])
                messages_store.add_message(
                    account_id=self.cfg.id,
                    username=username,
                    direction=item.get("direction", "out"),
                    text=text,
                    ts=None,
                )
                await logs_store.log_event(
                    account_id=self.cfg.id,
                    action_type="MANUAL_REPLY",
                    target=str(username),
                    result="ok",
                    info="sent_from_queue",
                )
                if self.leads_store is not None:
                    # Clear failed state if it was set during queueing.
                    self.leads_store.update_status(username, "contacted", fail_reason=None)
            except Exception as e:
                outbox_store.mark_failed(item["id"], str(e))
                await logs_store.log_event(
                    account_id=self.cfg.id,
                    action_type="MANUAL_REPLY",
                    target=str(username),
                    result="error",
                    info=str(e),
                )

    async def _maybe_flush_outbox(self) -> None:
        """
        Throttle outbox flushes during the main loop to avoid spamming
        Telethon with extra sends.
        """
        now = time.time()
        if now - self._last_outbox_flush >= self._outbox_flush_interval_sec:
            await self._flush_pending_outbox()
            self._last_outbox_flush = now


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

    def is_running(self, account_id: str) -> bool:
        worker = self._workers.get(account_id)
        return worker.is_running() if worker else False

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
