🤖 Telegram Outreach Orchestrator (Multi-account, AI-assisted)

Minimal, fast stack for cold DM outreach and lead handling:
- Python + Telethon orchestrator (one session per account).
- FastAPI backend + React/Vite UI.
- SQLite for state/metrics/logs.
- AI via OpenRouter (Claude 3.5 Sonnet by default).
- Email+code login (admin vs client view), attachment upload, manual replies, Kanban for leads.

⚠️ Use responsibly. Automated messaging can violate Telegram ToS. Send gently, respect limits, and use at your own risk.

## Quick start (local, Docker)
1) Prereqs: Docker + Docker Compose.
2) Copy `.env.example` → `.env`, set:
   - `ACCOUNTS=1,2,...` + per-account `API_ID/API_HASH/PHONE/SESSION` (Telethon .session paths under `sessions/`).
   - `AUTH_ALLOWED_ADMIN_EMAILS` / `AUTH_ALLOWED_CLIENT_EMAILS`.
   - `AUTH_SHARED_SECRET` (any string to require tokens).
   - `OPENROUTER_API_KEY` (for AI).
3) Bring up stack:
   ```bash
   docker compose up -d --build
   ```
4) UI: http://localhost (or your Cloudflare Tunnel host).
   - Admin login: work email + short code (delivery via configured SMTP or backend logs if dev).

## Cloudflare Tunnel (optional)
We ship `infra/cloudflared/config.yml` to proxy UI/API via your tunnel:
- Set `CLOUDFLARED_TUNNEL_ID` and `CLOUDFLARED_TUNNEL_TOKEN` in `.env`.
- `docker compose up -d cloudflared` (already part of compose).
- Point your DNS (Cloudflare NS) to the tunnel hostnames in `config.yml`.

## Dev workflow
- Backend: Python 3.13. Install deps: `pip install -r requirements.txt`.
- Frontend:
  ```bash
  cd ui
  npm install
  npm run dev   # hot reload
  npm run build # production build to ui/dist
  ```
- Tests: `pytest` (smoke + unit).
- Lint/format: not enforced; keep styles consistent.

## Files/dirs
- `data/` — SQLite state, metrics, logs (ignored by git).
- `sessions/` — Telethon .session files (ignored).
- `src/` — orchestrator, API, behavior engines, stores, prompts.
- `ui/` — React/Vite SPA (login, dashboard, leads, events).
- `infra/` — cloudflared + systemd samples.
- `scripts/` — helper scripts (`up_all.sh`, smoke tests).

## Auth & roles
- Admin: full dashboard/leads/logs, manual replies, account controls.
- Client: landing/summary only (no PII: no phones/usernames/logs).
- Login: email + short-lived code, tokens signed with `AUTH_SHARED_SECRET`.

## Environment highlights
- Rate limits and warmup: see `src/core/rate_limiter.py`, `behavior/warmup_engine.py`.
- Prompts/personas: `src/prompts/*` (`OPENING_PROMPT`, `SALES_PROMPT`, `CLOSING_PROMPT`, `ACCOUNT_LEGENDS`).
- Retention: `MESSAGE_RETENTION_DAYS` (default 90), applied in `MessagesStore`.

## Security & privacy
- All state local in SQLite; client view is sanitized.
- HSTS/secure headers in `ui/nginx.conf`.
- CSP is strict; Cloudflare beacon is blocked by default (safe).

## Useful URLs
- UI: `http://localhost` (or tunnel host).
- API (admin token required when auth enabled): `/api/accounts`, `/api/logs/events`, `/api/auth/login`, etc.

## Troubleshooting
- Blank UI: hard refresh (Cmd/Ctrl+Shift+R); ensure `/assets/index-*.js` loads, check console for `t is not defined` (fix applied).
- Tunnel 530: ensure `cloudflared` is up and DNS points to Cloudflare nameservers.
- Codes not delivered: verify SMTP creds; in dev mode, codes also logged in backend logs.
