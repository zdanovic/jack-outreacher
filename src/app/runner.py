import asyncio
import logging
import os
from typing import Optional

from ..core.config import load_app_config
from ..telegram.accounts import AccountManager
from ..telegram.client_adapter import TelegramClientAdapter
from ..behavior.scheduler import GlobalScheduler
from ..behavior.warmup_engine import WarmupEngine
from ..behavior.outreach_engine import OutreachEngine
from ..behavior.reply_engine import ReplyEngine
from ..core.state import global_state, AccountStatus
from ..core.rate_limiter import RateLimiter
from ..storage.leads_store import LeadsStore
from ..storage.dialogs_store import DialogsStore
from ..storage.settings_store import settings_store
from ..ai.client import AIClient


async def apply_initial_statuses(accounts, settings_provider=settings_store.get_settings) -> None:
    """
    Set initial statuses for all configured accounts on startup.

    Accounts are set ACTIVE by default unless an override explicitly
    disables them. This ensures orchestrator resumes work after restarts.
    """
    settings = settings_provider() if settings_provider else {}
    overrides = settings.get("accounts", {}).get("overrides", {}) if isinstance(settings, dict) else {}
    for acc in accounts:
        enabled = overrides.get(acc.id, {}).get("enabled", True)
        await global_state.set_status(acc.id, AccountStatus.ACTIVE if enabled else AccountStatus.PAUSED)


def _setup_logging() -> None:
    level = os.getenv("ORCHESTRATOR_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


async def main(env_path: Optional[str] = None) -> None:
    _setup_logging()
    logger = logging.getLogger("Orchestrator.Runner")

    cfg = load_app_config(env_path=env_path)
    if not cfg.accounts:
        logger.warning("No accounts configured. Exiting.")
        return

    client_adapter = TelegramClientAdapter()
    scheduler = GlobalScheduler()
    leads_store = LeadsStore()
    dialogs_store = DialogsStore()
    rate_limiter = RateLimiter(cfg.limits)
    ai_client = AIClient(cfg.ai)
    outreach_engine = OutreachEngine(
        leads_store=leads_store,
        rate_limiter=rate_limiter,
        settings_provider=settings_store.get_settings,
    )
    reply_engine = ReplyEngine(
        leads_store=leads_store,
        dialogs_store=dialogs_store,
        ai_client=ai_client,
    )

    account_manager = AccountManager(
        app_config=cfg,
        client_adapter=client_adapter,
        scheduler=scheduler,
    )
    account_manager.init_workers(
        leads_store=leads_store,
        dialogs_store=dialogs_store,
        rate_limiter=rate_limiter,
        ai_client=ai_client,
        reply_engine=reply_engine,
    )

    await apply_initial_statuses(cfg.accounts)

    # Seed scheduler with initial warmup/idling actions so that newly
    # connected accounts start with benign behaviour.
    warmup_engine = WarmupEngine(cfg.accounts)
    for action in warmup_engine.initial_actions():
        await scheduler.add_action(action)

    async def warmup_loop() -> None:
        """
        Background task that periodically enqueues warmup actions for
        each ACTIVE account. Designed to be lightweight and conservative.
        """
        while True:
            for acc in cfg.accounts:
                status = await global_state.get_status(acc.id)
                if status is not AccountStatus.ACTIVE:
                    continue
                settings = settings_store.get_settings()
                acc_overrides = settings.get("accounts", {}).get("overrides", {})
                if acc_overrides.get(acc.id, {}).get("enabled") is False:
                    await global_state.set_status(acc.id, AccountStatus.PAUSED)
                    continue
                for action in warmup_engine.plan_warmup_batch_for_account(acc.id):
                    await scheduler.add_action(action)
            await asyncio.sleep(warmup_engine.next_batch_interval())

    async def outreach_loop() -> None:
        """
        Background task that periodically enqueues SEND_COLD_DM actions
        for each ACTIVE account, respecting global rate limits and
        lead availability.
        """
        while True:
            for acc in cfg.accounts:
                status = await global_state.get_status(acc.id)
                if status is not AccountStatus.ACTIVE:
                    continue
                settings = settings_store.get_settings()
                acc_overrides = settings.get("accounts", {}).get("overrides", {})
                if acc_overrides.get(acc.id, {}).get("enabled") is False:
                    await global_state.set_status(acc.id, AccountStatus.PAUSED)
                    continue
                # Update limits from settings, if present.
                lim_cfg = settings.get("limits", {})
                updated_limits = cfg.limits.__class__(
                    max_cold_per_account_per_day=int(
                        lim_cfg.get("max_cold_per_account_per_day", cfg.limits.max_cold_per_account_per_day)
                    ),
                    max_cold_global_per_day=int(
                        lim_cfg.get("max_cold_global_per_day", cfg.limits.max_cold_global_per_day)
                    ),
                    max_concurrent_heavy_actions=int(
                        lim_cfg.get("max_concurrent_heavy_actions", cfg.limits.max_concurrent_heavy_actions)
                    ),
                    mode=str(lim_cfg.get("mode", cfg.limits.mode)),
                )
                rate_limiter.update_limits(updated_limits)
                actions = await outreach_engine.plan_batch_for_account(acc.id, max_per_batch=1)
                for action in actions:
                    await scheduler.add_action(action)
            await asyncio.sleep(outreach_engine.next_batch_interval())

    loop = asyncio.get_running_loop()
    account_manager.start_all(loop)

    # Launch background planners.
    loop.create_task(warmup_loop())
    loop.create_task(outreach_loop())

    logger.info("Orchestrator started for %d account(s). Press Ctrl+C to stop.", len(cfg.accounts))
    try:
        # Keep the main task alive while workers run.
        while True:
            await asyncio.sleep(60.0)
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user, stopping workers...")
    finally:
        await account_manager.stop_all()
        logger.info("All workers stopped. Goodbye.")


if __name__ == "__main__":
    asyncio.run(main())
