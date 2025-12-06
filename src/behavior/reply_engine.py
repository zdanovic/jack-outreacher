from __future__ import annotations

"""
Reply engine.

Subscribes to incoming messages on each account's TelegramClient,
decides which dialogs are eligible, calls the AI client with SALES_PROMPT
and updates lead status and metrics based on the internal analysis block.
"""

import re
from typing import Optional, List
from datetime import datetime, timedelta

try:  # Telethon may not be available in some test environments
    from telethon import events  # type: ignore
except Exception:  # pragma: no cover
    events = None  # type: ignore

from ..prompts.sales import SALES_PROMPT
from ..ai.client import AIClient
from ..storage.leads_store import LeadsStore
from ..storage.dialogs_store import DialogsStore
from ..storage.messages_store import messages_store
from ..core.metrics import metrics_store
from ..storage.logs_store import logs_store
from ..storage.settings_store import settings_store


class ReplyEngine:
    MANUAL_GRACE_MIN = 180  # pause auto replies for 3h after manual reply

    def __init__(
        self,
        leads_store: LeadsStore,
        dialogs_store: DialogsStore,
        ai_client: AIClient,
    ) -> None:
        self._leads_store = leads_store
        self._dialogs_store = dialogs_store
        self._ai_client = ai_client

    def attach_to_client(self, client, account_id: str) -> None:
        """
        Attach a handler for incoming private messages on this client.
        """
        if events is None:
            return

        @client.on(events.NewMessage(incoming=True))  # type: ignore
        async def _on_message(event):  # pragma: no cover - runtime path
            # Skip non-private or outgoing messages.
            if not event.is_private or event.out:
                return
            sender = await event.get_sender()
            username = getattr(sender, "username", None)
            if not username:
                return
            text = event.raw_text or ""
            ts = event.date.isoformat() if getattr(event, "date", None) else None
            await self.handle_incoming(account_id, client, username, text, ts)

    async def handle_incoming(
        self,
        account_id: str,
        client,
        username: str,
        text: str,
        ts: Optional[str] = None,
    ) -> None:
        """
        Process an incoming message from a user with the given username.
        Only handles dialogs that are known leads.
        """
        # Allow admin to disable replies via settings.
        replies_cfg = settings_store.get_settings().get("replies", {})
        if replies_cfg.get("enabled") is False:
            return

        meta = self._dialogs_store.get(username)
        if not meta or not meta.is_lead:
            # We do not persist messages for non-leads to avoid storing
            # unrelated personal chats.
            return

        # Respect manual reply grace window to avoid conflicts.
        if meta.manual_replied_at:
            try:
                dt = datetime.fromisoformat(meta.manual_replied_at)
                if datetime.utcnow() - dt < timedelta(minutes=self.MANUAL_GRACE_MIN):
                    await logs_store.log_event(
                        account_id=account_id,
                        action_type="REPLY_MESSAGE",
                        target=str(username),
                        result="skipped",
                        info="manual_grace_active",
                    )
                    return
            except Exception:
                pass

        # Persist incoming message for known leads only.
        messages_store.add_message(
            account_id=account_id,
            username=username,
            direction="in",
            text=text,
            ts=ts,
        )

        # Build short chat history for AI.
        try:
            entity = await client.get_entity(username)
            history = await client.get_messages(entity, limit=20)
        except Exception as e:
            await logs_store.log_event(
                account_id=account_id,
                action_type="REPLY_MESSAGE",
                target=str(username),
                result="error",
                info=f"history_fetch_failed: {e}",
            )
            return

        messages = [{"role": "system", "content": SALES_PROMPT}]
        # Most recent messages last.
        for msg in reversed(list(history)):
            role = "assistant" if msg.out else "user"
            text = msg.message or ""
            if not text:
                continue
            messages.append({"role": role, "content": text})

        try:
            ai_text = await self._ai_client.chat(messages, max_tokens=200, temperature=0.7)
        except Exception as e:  # pragma: no cover
            ai_text = None
            await logs_store.log_event(
                account_id=account_id,
                action_type="REPLY_MESSAGE",
                target=str(username),
                result="error",
                info=f"ai_error: {e}",
            )

        if not ai_text:
            return

        cleaned, lead_status = self._extract_and_clean(ai_text)

        try:
            await client.send_message(username, cleaned)
            await metrics_store.incr(account_id, "replies_received", 1)
            messages_store.add_message(
                account_id=account_id,
                username=username,
                direction="out",
                text=cleaned,
                ts=None,
            )
            await logs_store.log_event(
                account_id=account_id,
                action_type="REPLY_MESSAGE",
                target=str(username),
                result="ok",
            )
        except Exception as e:
            await logs_store.log_event(
                account_id=account_id,
                action_type="REPLY_MESSAGE",
                target=str(username),
                result="error",
                info=str(e),
            )
            return

        # Update lead status and metrics based on internal analysis.
        if lead_status:
            status_norm = lead_status.strip().lower()
            if status_norm.startswith("deal"):
                # Deal is a manual handoff stage; count as hot for metrics, set status to deal.
                await metrics_store.incr(account_id, "hot_leads", 1)
                self._leads_store.update_status(username, "deal")
            elif status_norm.startswith("hot"):
                await metrics_store.incr(account_id, "hot_leads", 1)
                self._leads_store.update_status(username, "hot")
            elif status_norm.startswith("warm"):
                await metrics_store.incr(account_id, "warm_leads", 1)
                self._leads_store.update_status(username, "warm")
            elif status_norm.startswith("cold"):
                await metrics_store.incr(account_id, "cold_leads", 1)
                self._leads_store.update_status(username, "cold")

    def _extract_and_clean(self, text: str) -> tuple[str, Optional[str]]:
        """
        Remove the internal analysis block from the AI response and
        extract the Lead Status value, if present.
        """
        analysis_status: Optional[str] = None

        # Try to capture [Internal Analysis - Not Shown to User: ...]
        m = re.search(
            r"\[Internal Analysis - Not Shown to User:(.*?)\]",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if m:
            analysis_block = m.group(1)
            # Look for a line starting with 'Lead Status:'
            for line in analysis_block.splitlines():
                if "lead status" in line.lower():
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        analysis_status = parts[1].strip()
                        break

        # Remove various analysis markers.
        patterns: List[str] = [
            r"\[Internal Analysis - Not Shown to User:.*?\]",
            r"\[Internal tracking - not shown to user:.*?\]",
            r"\[Internal tracking:.*?\]",
        ]
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL | re.IGNORECASE)

        return cleaned.strip(), analysis_status
