# Telegram Outreach Orchestrator

A multi-account orchestrator for safe Telegram cold outreach, warmup, and lead handling. It combines a Telethon-based worker pool, FastAPI backend, React/Vite UI, SQLite state, and OpenRouter/Claude for AI-generated texts. Focus: conservative pacing, read-only warmup, role-based UI, and auditability.

## What it does (capabilities)
- Runs multiple Telegram accounts in parallel with per-account device profiles, soft/hard limits, and runtime status (ACTIVE/PAUSED/NEED_RELOGIN/BANNED).
- Warmup: read-only channel/dialog reads with jitter, quiet hours, night intervals, per-hour caps, and “history-only” dialog reads (no /start, no sends).
- Outreach: plans and sends cold DMs under daily/hourly/interval limits, with jitter to desynchronize accounts; failed sends mark leads as failed (not reused immediately).
- Replies: ingests inbound messages for known leads, builds short history, calls AI to qualify (hot/warm/cold/deal), and sends concise replies; respects manual-reply grace.
- Manual control: pause/resume accounts, send manual replies (queued if offline), upload attachments, tweak settings live via UI.
- Observability: metrics per day/account, event TSV log, messages/logs for dialogs, basic floodwait tracking.

## Architecture (modules and responsibilities)
- **Orchestrator (Python/asyncio/Telethon)**
  - `AccountManager`: creates workers, start/stop, applies global state.
  - `AccountWorker`: connects a Telethon client, runs scheduled actions (warmup, cold send, reply handling), drains pending outbox, updates metrics/logs/state.
  - `GlobalState`: in-memory runtime status per account (status, errors, ban reason, floodwait, cold_sent_today).
  - `RateLimiter`: daily/global limits seeded from DB, plus soft interval/hourly pacing.
- **Schedulers/engines**
  - `GlobalScheduler`: per-account queues with earliest_start_ts.
  - `WarmupEngine`: plans READ_CHANNEL/READ_DIALOG/IDLE with jitter, quiet hours, hour caps, history-only dialog reads.
  - `OutreachEngine`: reserves leads, plans SEND_COLD_DM with jitter and limit checks.
  - `ReplyEngine`: Telethon event handler for inbound messages, AI reply, lead status update, manual-grace guard.
- **API (FastAPI)**
  - Admin endpoints: accounts, metrics/timeseries, dialogs/messages, leads filter/update, logs, settings (GET/PUT), pause/resume, manual replies, attachments upload/download, restart hook, Telethon login start/verify.
  - Client endpoints: landing summary, limited accounts view.
  - Auth endpoints: request code, login, expose auth config.
- **UI (React/Vite)**
  - Admin: account cards (status, metrics, floodwait, login-needed), settings editor (limits, warmup, outreach, replies, account overrides), leads Kanban/search, logs/events viewer, manual reply modal, attachment upload.
  - Client: sanitized summary (no PII).
- **AI client (OpenRouter)**
  - Chat completions (Claude 3.5 Sonnet default); privacy headers (do-not-store, privacy-mode, referer/title).
  - Opening prompt (cold DM) and sales prompt (reply qualification) stored in `src/prompts`.
- **Storage**
  - SQLite `data/orchestrator_state.db`: tables `leads`, `dialogs`, `metrics`, `messages`, `pending_outbox`, `attachments`, `settings`.
  - Files: `data/attachments/` for uploaded files, `data/events.log.tsv` for audit log.
  - Message encryption optional (Fernet from `DATA_ENCRYPTION_KEY`); retention by `MESSAGE_RETENTION_DAYS`.
- **Runtime files**
  - `data/warmup_channels.txt`, `data/warmup_users.txt` (global), optional per-account `data/warmup_channels_<acc>.txt`, `data/warmup_users_<acc>.txt`.
  - `sessions/` for Telethon session files (one per account).
  - `ui/dist/` production bundle.

## Data model and flows
- **Leads**: seeded from CSV (`data/leads_strategy_1.csv` or custom), status `new/pending/contacted/hot/warm/cold/deal/failed`, fields: username, name, first/last, bio, tag, source, last_account_id, last_contacted_at, fail_reason.
- **Dialogs**: known contacts, flags is_lead, peer_id, first/last_seen, last_account_id, manual_replied_at; used to decide reply eligibility and manual-grace.
- **Messages**: per account/user, direction in/out, text (optionally encrypted), timestamp; retention enforced.
- **Metrics**: per date/account (cold_sent, cold_failed, replies_received, hot/warm/cold_leads, floodwait_events, warmup_actions); daily reset via rate limiter.
- **Outbox**: pending manual replies when account offline/paused; delivered when account comes online.
- **Attachments**: metadata in DB, file on disk.
- **Settings**: JSON sections (limits, warmup, outreach, replies, accounts overrides), deep-merged over defaults.

## Behavior details
- **Warmup (read-only, human-like)**
  - Actions: READ_CHANNEL, READ_DIALOG (history-only), IDLE.
  - Pauses: multiple `get_messages` per target with 3–12 s delays; IDLE after batch.
  - Quiet hours: default 00–07 Europe/Belgrade (or account TZ), uses longer batch intervals at night.
  - Caps: `max_read_dialogs_per_hour` (default 2), `bot_read_chance` (default 0.2), day/night batch interval ranges, action jitter ranges.
  - Sources: shuffled per account with stable seed; per-account lists if present, otherwise global lists.
  - No writes: no /start, no joins, no reactions, no sends.
- **Outreach**
  - RateLimiter: daily per-account/global, min interval (s), max per hour per account; global counters seeded from metrics, reset daily.
  - Planning: jittered send interval per action, extra jitter per batch to avoid simultaneous sends across accounts.
  - AI opening: uses `OPENING_PROMPT` and per-account legend (role/persona/style); fallback static message if AI unavailable.
  - Errors: mark lead as failed with reason; metrics increment cold_failed.
- **Replies**
  - Triggered only for known leads; skips if manual reply <3h ago.
  - Builds history (last 20), calls AI sales prompt, strips internal analysis, sends concise reply.
  - Lead status updates: hot/warm/cold/deal map to metrics and lead status.
  - Logging: success/error/skip recorded; floodwait errors propagated to global state.
- **Manual replies**
  - If account ACTIVE: stored in messages, event log.
  - If paused/offline: enqueued to pending_outbox with reason; delivered by worker when online; lead marked failed until sent.
- **Accounts lifecycle**
  - Startup: statuses seeded ACTIVE/PAUSED from settings overrides; healthcheck marks NEED_RELOGIN or BANNED if Telethon session invalid/ban detected.
  - Restart: global state counters reset daily; floodwait stored in memory only.

## API surface (high level)
- `GET /accounts` (admin): id, phone tail, status, login_required, enabled, metrics, ban_reason, last_error, floodwait_seconds.
- `POST /accounts/{id}/pause|resume` (admin): toggle account and persist override.
- `GET /metrics/timeseries` (admin): by date and per-account aggregates.
- `GET /leads` (admin): filters by statuses/search/since/limit; `POST /leads/{username}/status`.
- `GET /accounts/{id}/dialogs` and `/dialogs/{username}/messages` (admin).
- `POST /accounts/{id}/dialogs/{username}/reply` (admin): manual reply, queues if offline.
- `GET /logs/events` (admin): TSV events tail.
- `GET/PUT /settings` (admin): deep-merge settings; applies account overrides to runtime.
- `POST /attachments/upload`, `GET /attachments/{id}` (admin).
- Auth: `POST /auth/request-code`, `POST /auth/login`, `GET /auth/config`.
- Client: `GET /landing/summary`, `GET /client/accounts`.
- Telethon login: `POST /accounts/{id}/login/start`, `POST /accounts/{id}/login/verify`.

## Configuration (.env) essentials
- Accounts: `ACCOUNTS=acc1,acc2`, then `acc1_API_ID`, `acc1_API_HASH`, `acc1_PHONE`, `acc1_SESSION` (path to .session), optional `acc1_PROXY`, `acc1_TZ`, `acc1_BEHAVIOR_PROFILE`.
- Auth: `AUTH_SHARED_SECRET` (enables auth), `AUTH_ALLOWED_ADMIN_EMAILS`, `AUTH_ALLOWED_CLIENT_EMAILS`, `AUTH_ALLOWED_EMAIL_DOMAINS`, `AUTH_CODE_TTL_SECONDS`, `AUTH_TOKEN_TTL_SECONDS`, SMTP (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_PORT`, `SMTP_USE_TLS`).
- AI: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` (default anthropic/claude-3.5-sonnet), `OPENROUTER_DO_NOT_STORE`, `OPENROUTER_PRIVACY_MODE`, `OPENROUTER_REFERER`, `OPENROUTER_X_TITLE`.
- Limits: `MAX_COLD_PER_ACCOUNT_PER_DAY`, `MAX_COLD_GLOBAL_PER_DAY`, `MAX_CONCURRENT_HEAVY_ACTIONS`, `MIN_COLD_INTERVAL_SECONDS`, `MAX_COLD_PER_HOUR_PER_ACCOUNT`, `LIMITS_MODE`.
- Retention/security: `MESSAGE_RETENTION_DAYS`, `DATA_ENCRYPTION_KEY` (optional Fernet).
- UI polling: `VITE_POLL_INTERVAL_MS`, `VITE_LOGS_POLL_INTERVAL_MS`.

## Running and ops
- **Docker Compose**: `docker compose up -d --build` (API, UI, optional cloudflared).
- **Dev**: `pip install -r requirements.txt`, `npm install --prefix ui`, `uvicorn src.app.api:app --reload`, `npm run dev --prefix ui`.
- **Build UI**: `npm run build --prefix ui` → `ui/dist`.
- **Sessions**: place `.session` files under `sessions/` (paths from .env).

## Data handling and retention
- DB: `data/orchestrator_state.db` (WAL mode enabled). Back up before upgrades.
- Logs: `data/events.log.tsv` (tsv header, append-only). Rotate manually if needed.
- Messages: optional encryption; retention deletes rows older than `MESSAGE_RETENTION_DAYS`.
- Attachments: stored on disk; no encryption by default.
- Warmup lists: editable text files, one entry per line; comments with `#`.

## Security posture
- Auth required if `AUTH_SHARED_SECRET` set; HS256 JWT with exp and role; codes via SMTP or dev file output.
- Best-effort rate limit on auth endpoints (in-memory).
- Strict headers/CSP on API; UI client view hides PII (no phones/usernames/logs).
- AI privacy headers request non-retention; data stored locally (SQLite/files).
- Cloudflare beacon is blocked by CSP by default; console warnings are benign.
- No destructive defaults: no auto-joins, no commands sent, no reactions.

## Anti-abuse and evasion tactics
- Human-like warmup: history-only dialog reads, multi-step scroll with pauses, quiet hours, per-hour caps, jittered scheduling.
- Pacing: min interval and hourly soft caps for cold sends; per-batch jitter to avoid synchronized sends.
- Device diversity: per-account device profile from curated list.
- Lead handling: on errors, mark leads failed to avoid immediate retries; manual-reply grace to prevent AI conflicts.
- Floodwait: stored in memory and surfaced via `/accounts` (seconds remaining).

## Known limitations
- Runtime state (floodwait/status/hourly warmup counters) is in memory; restart resets these (but re-applies settings overrides).
- Pending outbox drains only when account is online; if a session is dead, messages remain queued.
- Proxy management not wired in code (env placeholders exist).
- No built-in monitoring/alerting; event log/metrics must be tailed or exported manually.
- No e2e tests; frontend only build-tested.

## Testing
- Backend: `pytest` (stores, engines, auth, API). Ensure Telethon is installable in test env or guard with skips.
- Frontend: `npm run build` (prod build).

## File layout
- `src/`: core, app (API/auth/control/runner), behavior (warmup/outreach/reply/scheduler), telegram (accounts/client adapter), storage (stores/DB), prompts, ai client.
- `data/`: DB, logs, warmup lists, leads CSV, attachments.
- `sessions/`: Telethon sessions (gitignored).
- `ui/`: React/Vite app; `ui/dist` for deploy.
- `scripts/`: helper scripts.

## License
No open-source license is granted; all rights reserved by the project owner. Contact the owner for usage or redistribution permissions.

## Configuration (.env)
Copy `.env.example` → `.env`:
- Accounts: `ACCOUNTS`, per-suffix `{ID}_API_ID`, `{ID}_API_HASH`, `{ID}_PHONE`, `{ID}_SESSION`; optional `{ID}_PROXY`, `{ID}_TZ`, `{ID}_BEHAVIOR_PROFILE`.
- AI: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_DO_NOT_STORE`, `OPENROUTER_PRIVACY_MODE`.
- Auth: `AUTH_SHARED_SECRET`, `AUTH_ALLOWED_ADMIN_EMAILS`, `AUTH_ALLOWED_CLIENT_EMAILS`, `AUTH_ALLOWED_EMAIL_DOMAINS`, TTLs, SMTP for codes.
- Limits: `MAX_COLD_PER_ACCOUNT_PER_DAY`, `MAX_COLD_GLOBAL_PER_DAY`, `MAX_CONCURRENT_HEAVY_ACTIONS`, `MIN_COLD_INTERVAL_SECONDS`, `MAX_COLD_PER_HOUR_PER_ACCOUNT`, `LIMITS_MODE`.
- Retention/security: `MESSAGE_RETENTION_DAYS`, optional `DATA_ENCRYPTION_KEY` (Fernet-derived).
- UI polling: `VITE_POLL_INTERVAL_MS`, `VITE_LOGS_POLL_INTERVAL_MS`.

## Running
### Docker Compose
```bash
docker compose up -d --build
```
- UI: http://localhost (or via Cloudflare Tunnel if configured).
- API: port 8000 inside compose; secured by auth if enabled.

### Local dev
```bash
pip install -r requirements.txt
cd ui && npm install
uvicorn src.app.api:app --reload
npm run dev --prefix ui
```

## Admin Settings (UI)
- **Limits**: daily per-account/global cold caps, concurrent heavy actions, min interval between cold sends (s), max cold per hour.
- **Warmup**: day/night batch intervals, action jitter, quiet hours, bot-read probability, max dialog reads per hour.
- **Outreach**: enable/disable, send interval min/max, max per batch.
- **Replies**: enable/disable auto replies.
- **Accounts overrides**: enable/pause per account (synced with runtime state).

## Warmup behavior (human-like, low noise)
- Read-only only: `get_entity`, `get_messages`; no /start, no reactions, no joins.
- Dialog reads happen only if history exists; otherwise skipped to avoid poking bots.
- Simulated scrolling: multiple small fetches with 3–12 s pauses, plus idle gaps.
- Quiet hours: longer batch intervals at night (default Europe/Belgrade 00–07); uses account TZ if provided.
- Per-hour soft cap for dialog reads; jitter to desynchronize accounts.
- Source lists: shared `data/warmup_channels.txt` and `data/warmup_users.txt`; optional per-account `data/warmup_channels_<acc>.txt` / `data/warmup_users_<acc>.txt` (used if present).

## Cold outreach and replies
- RateLimiter: daily per-account/global limits, min interval, max/hour; counters reset daily from metrics.
- OutreachEngine: plans SEND_COLD_DM with jitter, checks limits; on error marks lead as failed (not immediately returned to new).
- ReplyEngine: only for known leads; respects 3h grace after manual reply; builds short history, calls AI, strips internal blocks, updates lead status/metrics.
- Manual replies: if account not ACTIVE, enqueue to pending_outbox and set lead status failed with reason; sent later when online.

## Data and retention
- SQLite `data/orchestrator_state.db`: tables `leads`, `dialogs`, `metrics`, `messages`, `pending_outbox`, `attachments`, `settings`.
- Messages can be encrypted at rest (Fernet key from `DATA_ENCRYPTION_KEY`); retention by `MESSAGE_RETENTION_DAYS`.
- Attachments stored under `data/attachments` with metadata in DB.
- Event log `data/events.log.tsv` (TSV, tail/grep-friendly).

## Authentication and security
- Email + one-time code, HS256 JWT; domain- and email-based allowlists for admin/client roles.
- In-memory rate limit for auth endpoints.
- Strict headers and CSP for API/UI; client mode redacts PII (no phones/usernames/logs).
- Privacy: AI calls use do-not-store headers; data stays local (SQLite + files).
- By default, Cloudflare beacon is blocked by CSP; console noise is expected but harmless.

## Files and layout
- `data/`: database, logs, warmup lists, attachments.
- `sessions/`: Telethon session files (never commit).
- `ui/`: React/Vite app; `ui/dist` is the production bundle.
- `scripts/`: helper scripts (bring-up, smoke).

## Testing
- Backend: `pytest` (smoke/unit for stores, engines, auth, API).
- Frontend: `npm run build` (production build). No bundled e2e.

## Known behaviors and caveats
- Runtime state (floodwait/status) is in memory; on restart ACTIVE/PAUSED is restored from settings, warmup hourly counters reset.
- If an account never connects, pending_outbox will not drain.
- Per-account device profile is set, but proxy management is not wired yet (proxy env per account is available for future use).

## License
No open-source license is granted; all rights reserved by the project owner. Contact the owner for usage or redistribution permissions.
