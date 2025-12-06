# Dev Log – Telegram Outreach Orchestrator

Concise history of changes and hardening steps.

## Latest (Dec 2025)
- UI localization pass: tab/tooltips, concise wording, metric hints, strict CSP kept (Cloudflare beacon blocked by design).
- Leads view: default-safe translation handler (`t`) to avoid runtime crashes; login page stabilized.
- Cloudflare tunnel config packaged; compose includes cloudflared with token/ID from `.env`.
- .gitignore tightened: ignores node_modules, ui/dist, data, .vite caches, coverage artifacts.
- Readme rewritten (minimal setup, tunnel notes, auth/roles, troubleshooting).

## Earlier milestones
- React/Vite UI: dark minimal layout, login + dashboard + leads Kanban, manual replies with attachment upload, client landing (sanitized).
- API (FastAPI): email+code auth, admin/client roles, accounts/metrics/logs, manual reply queue, attachments, login/start/verify for Telethon.
- Orchestrator (Python/Telethon): per-account workers, warmup engine (channels/users), outreach engine (AI cold DMs, rate limits), reply engine (AI qualification hot/warm/cold), manual reply outbox, metrics/logging to SQLite.
- State: single SQLite (`data/orchestrator_state.db`) for leads/dialogs/messages/metrics; retention for messages; structured event log.
- Prompts/personas: opening/sales/closing + account legends; AI via OpenRouter (Claude 3.5 Sonnet default).
- Infra: cloudflared config, systemd samples, Docker Compose for API/UI/tunnel; tests (pytest) for stores/engines/worker/handlers.

## Notes
- Default security: HSTS, CSP strict, client view redacts PII; CF beacon intentionally blocked.
- Login codes: via SMTP in prod, logged in dev. Use modest send rates to avoid Telegram limits.
