# Cloudflare Tunnel for UI (single hostname)

Goal: expose only the UI hostname (with `/api` proxied to the local API) without opening ports. Protect with Cloudflare Access + our RBAC.

## Prereqs
- Domain managed by Cloudflare (free plan is enough).
- `cloudflared` installed on the host running UI/API.

## Steps
1) Login and create tunnel:
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create tg-orch
   cloudflared tunnel route dns tg-orch ui.example.com
   ```
   Note the generated credentials JSON path.

2) Configure ingress:
   - Copy `infra/cloudflare/config.example.yml` to `~/.cloudflared/config.yml`.
   - Fill `credentials-file` with the path from step 1.
   - Set `hostname` to your `ui.example.com`.
   - By default it maps:
     - `ui.example.com` → `http://localhost:5173` (Vite dev) and `/api/*` → `http://localhost:8000`.
   - If serving built UI, point the service to `http://localhost:4173` (or your static server).

3) Run tunnel:
   ```bash
   cloudflared tunnel run tg-orch
   ```
   For long-running, install as a service (cloudflared has a `service install` helper).

4) (Recommended) Cloudflare Access:
   - In Cloudflare dashboard → Zero Trust → Access → Applications.
   - Create an app for `ui.example.com`, policy “Allow” for your emails/domains.
   - This adds a CF-managed OTP page before hitting our UI.

5) RBAC in our UI/API:
   - Keep `AUTH_SHARED_SECRET` + allowlists for admin/client emails.
   - Generate codes via `python -m src.app.auth --email you@company.com`.

6) Restart hook (optional):
   - Set `ADMIN_RESTART_COMMAND="systemctl restart tg-orchestrator.service"` (or pm2/docker script).
   - Use the “Restart hint” button in Admin Actions to trigger it.

Notes:
- UI uses relative `/api`; the tunnel maps `/api` on the same host to FastAPI, so the browser can reach API without exposing a separate hostname.
- Leave FastAPI/Uvicorn bound to localhost (127.0.0.1); cloudflared handles ingress.
- For extra safety, you can tighten Cloudflare Access to specific emails and keep our RBAC enabled.

