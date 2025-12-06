from __future__ import annotations

import asyncio
from typing import List, Optional

import openai

from ..core.config import AIConfig


class AIClient:
    """
    Thin async wrapper around the OpenRouter‑compatible OpenAI client.

    This is intentionally minimal for now – we only support a generic
    chat completion call. Specialized helpers (opening / sales / closing)
    can be layered on top later.
    """

    def __init__(self, cfg: AIConfig) -> None:
        self._cfg = cfg
        if not cfg.api_key:
            self._client: Optional[openai.OpenAI] = None
        else:
            self._client = openai.OpenAI(
                api_key=cfg.api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": cfg.referer,
                    "X-Title": cfg.title,
                    # Ask OpenRouter/providers to avoid retention/training where possible.
                    # Providers that ignore the header will simply treat it as a no-op.
                    "X-Do-Not-Store": "true" if cfg.send_do_not_store_header else "false",
                    "X-Privacy-Mode": cfg.privacy_mode,
                },
                timeout=45.0,
            )

    async def chat(
        self,
        messages: List[dict],
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> Optional[str]:
        if not self._client:
            return None

        def _call() -> str:
            resp = self._client.chat.completions.create(
                model=self._cfg.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=1.0,
            )
            if resp.choices and resp.choices[0].message and resp.choices[0].message.content:
                return resp.choices[0].message.content.strip()
            return ""

        try:
            return await asyncio.to_thread(_call)
        except Exception:
            # For now let the caller handle logging/metrics; we only
            # signal failure via None.
            return None

