"""
FastAPI-based control and read-only UI backend.

This module exposes a minimal REST API to:
- list accounts and their basic metrics,
- view per-account metrics and events,
- inspect stored dialog messages.

It is designed to run alongside the orchestrator and operate on the
shared SQLite state and log files.
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import date, timedelta
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Header, status, UploadFile, File
from fastapi.responses import FileResponse
from fastapi import Request
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ..core.config import load_app_config
from ..core.state import global_state, AccountStatus
from ..storage.state_db import get_state_db
from ..storage.messages_store import messages_store
from ..storage.logs_store import logs_store
from .auth import AuthService, AuthUser
from ..storage.settings_store import settings_store
from ..storage.outbox_store import outbox_store
from ..storage.dialogs_store import DialogsStore
from ..storage.attachments_store import attachments_store
from ..storage.leads_store import LeadsStore


app = FastAPI(title="TG Orchestrator UI API")

_config = load_app_config()
_db = get_state_db()
_auth = AuthService(_config.auth)
_restart_cmd = os.getenv("ADMIN_RESTART_COMMAND")
_leads_store = LeadsStore()
_dialogs_store = DialogsStore()

# Simple in-memory rate limit (best-effort) for auth endpoints.
_RATE_LIMIT: Dict[str, List[float]] = {}
_RATE_LIMIT_WINDOW = 60.0
_RATE_LIMIT_MAX = 10


def _rate_limit(request: Request, key_suffix: str = "") -> None:
    ip = request.client.host if request and request.client else "unknown"
    key = f"{ip}:{key_suffix}"
    now = time.time()
    bucket = _RATE_LIMIT.get(key, [])
    bucket = [t for t in bucket if now - t < _RATE_LIMIT_WINDOW]
    if len(bucket) >= _RATE_LIMIT_MAX:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests.")
    bucket.append(now)
    _RATE_LIMIT[key] = bucket


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add common security headers for every response.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        # HSTS (only meaningful over HTTPS/Cloudflare)
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains; preload",
        )
        # Basic hardening
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # CSP tuned for this API/UI bundle
        csp = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "media-src 'self'; "
            "font-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "upgrade-insecure-requests"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        return response


app.add_middleware(SecurityHeadersMiddleware)

# Optional login session registry for Telethon-based login flow.
try:  # pragma: no cover - Telethon may not be available in all environments
    from telethon import TelegramClient  # type: ignore
    from telethon.errors import SessionPasswordNeededError  # type: ignore
except Exception:  # pragma: no cover
    TelegramClient = None  # type: ignore
    SessionPasswordNeededError = Exception  # type: ignore

_login_clients: dict[str, Any] = {}


def _get_today_metrics() -> Dict[str, Dict[str, int]]:
    today = date.today().isoformat()
    cur = _db.conn.cursor()
    cur.execute(
        """
        SELECT account_id, cold_sent, cold_failed, replies_received,
               hot_leads, warm_leads, cold_leads, floodwait_events, warmup_actions
        FROM metrics
        WHERE date = ?;
        """,
        (today,),
    )
    rows = cur.fetchall()
    metrics: Dict[str, Dict[str, int]] = {}
    for (
        account_id,
        cold_sent,
        cold_failed,
        replies_received,
        hot_leads,
        warm_leads,
        cold_leads,
        floodwait_events,
        warmup_actions,
    ) in rows:
        metrics[account_id] = {
            "cold_sent": cold_sent or 0,
            "cold_failed": cold_failed or 0,
            "replies_received": replies_received or 0,
            "hot_leads": hot_leads or 0,
            "warm_leads": warm_leads or 0,
            "cold_leads": cold_leads or 0,
            "floodwait_events": floodwait_events or 0,
            "warmup_actions": warmup_actions or 0,
        }
    return metrics


def _zero_metrics() -> Dict[str, int]:
    return {
        "cold_sent": 0,
        "cold_failed": 0,
        "replies_received": 0,
        "hot_leads": 0,
        "warm_leads": 0,
        "cold_leads": 0,
        "floodwait_events": 0,
        "warmup_actions": 0,
    }


def _normalize_list_param(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip().lower() for v in value.split(",") if v.strip()]


class LeadStatusUpdate(BaseModel):
    status: str


def _require_auth_header(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header.")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization scheme.")
    return authorization.split(" ", 1)[1]


async def current_user(authorization: str | None = Header(None)) -> AuthUser:
    token = _require_auth_header(authorization) if _config.auth.enabled else None
    user = _auth.verify_token(token) if token else AuthUser(email="insecure@local", role="admin")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")
    return user


def admin_required(user: AuthUser = Depends(current_user)) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins only.")
    return user


def client_or_admin(user: AuthUser = Depends(current_user)) -> AuthUser:
    return user


@app.get("/accounts")
async def list_accounts(_: AuthUser = Depends(admin_required)) -> List[Dict[str, Any]]:
    metrics = _get_today_metrics()
    settings = settings_store.get_settings()
    acc_overrides = settings.get("accounts", {}).get("overrides", {})
    result = []
    now = time.time()
    for acc in _config.accounts:
        runtime = await global_state.get_runtime(acc.id)
        status = runtime.status
        m = metrics.get(acc.id, {})
        enabled = acc_overrides.get(acc.id, {}).get("enabled", True)
        flood_sec = None
        if runtime.flood_wait_until:
            flood_sec = max(0, int(runtime.flood_wait_until - now))
        result.append(
            {
                "id": acc.id,
                "phone": acc.phone,
                "status": status.name,
                "enabled": bool(enabled),
                "metrics": m,
                "ban_reason": runtime.ban_reason,
                "last_error": runtime.last_error,
                "floodwait_seconds": flood_sec,
            }
        )
    return result


@app.get("/accounts/{account_id}/metrics")
async def account_metrics(account_id: str, _: AuthUser = Depends(admin_required)) -> Dict[str, Any]:
    metrics = _get_today_metrics()
    if account_id not in metrics:
        raise HTTPException(status_code=404, detail="Metrics not found for account")
    return metrics[account_id]


@app.get("/accounts/{account_id}/dialogs")
async def account_dialogs(
    account_id: str, limit: int = 100, _: AuthUser = Depends(admin_required)
) -> List[Dict[str, Any]]:
    limit = max(1, min(limit, 200))
    return _dialogs_store.list_for_account(account_id=account_id, limit=limit)


@app.get("/metrics/timeseries")
async def metrics_timeseries(days: int = 30, _: AuthUser = Depends(admin_required)) -> Dict[str, Any]:
    """
    Return daily metrics aggregates for the last `days` (max 180).
    Includes global by-date totals and per-account series.
    """
    days = max(1, min(days, 180))
    start_date = date.today() - timedelta(days=days - 1)
    cur = _db.conn.cursor()
    cur.execute(
        """
        SELECT date, account_id, cold_sent, cold_failed, replies_received,
               hot_leads, warm_leads, cold_leads, floodwait_events, warmup_actions
        FROM metrics
        WHERE date >= ?
        ORDER BY date ASC;
        """,
        (start_date.isoformat(),),
    )
    rows = cur.fetchall()

    agg_by_date: Dict[str, Dict[str, int]] = {}
    per_account: Dict[str, Dict[str, Dict[str, int]]] = {}

    for (
        day,
        account_id,
        cold_sent,
        cold_failed,
        replies_received,
        hot_leads,
        warm_leads,
        cold_leads,
        floodwait_events,
        warmup_actions,
    ) in rows:
        if day not in agg_by_date:
            agg_by_date[day] = _zero_metrics()
        agg = agg_by_date[day]
        agg["cold_sent"] += cold_sent or 0
        agg["cold_failed"] += cold_failed or 0
        agg["replies_received"] += replies_received or 0
        agg["hot_leads"] += hot_leads or 0
        agg["warm_leads"] += warm_leads or 0
        agg["cold_leads"] += cold_leads or 0
        agg["floodwait_events"] += floodwait_events or 0
        agg["warmup_actions"] += warmup_actions or 0

        per_account.setdefault(account_id, {})
        per_account[account_id][day] = {
            "cold_sent": cold_sent or 0,
            "cold_failed": cold_failed or 0,
            "replies_received": replies_received or 0,
            "hot_leads": hot_leads or 0,
            "warm_leads": warm_leads or 0,
            "cold_leads": cold_leads or 0,
            "floodwait_events": floodwait_events or 0,
            "warmup_actions": warmup_actions or 0,
        }

    # Ensure continuous dates and zero-fill missing days.
    date_range = [start_date + timedelta(days=i) for i in range(days)]
    by_date: List[Dict[str, Any]] = []
    per_account_series: Dict[str, List[Dict[str, Any]]] = {}

    for acc in _config.accounts:
        per_account_series[acc.id] = []

    for dt in date_range:
        day = dt.isoformat()
        day_metrics = agg_by_date.get(day, _zero_metrics())
        by_date.append({"date": day, **day_metrics})

        for acc in _config.accounts:
            acc_day = per_account.get(acc.id, {}).get(day, _zero_metrics())
            per_account_series[acc.id].append({"date": day, **acc_day})

    return {"by_date": by_date, "per_account": per_account_series}


@app.get("/leads")
async def list_leads(
    statuses: str | None = None,
    search: str | None = None,
    since_days: int = 180,
    limit: int = 200,
    _: AuthUser = Depends(admin_required),
) -> List[Dict[str, Any]]:
    """
    List leads with optional filters (statuses, text search, time window).
    Defaults to warm/hot leads for quick CRM navigation.
    """
    _leads_store.seed_from_csv_once()
    since_days = max(1, min(since_days, 365))
    limit = max(1, min(limit, 500))
    status_list = _normalize_list_param(statuses) or ["hot", "warm", "deal", "failed"]
    clauses = []
    params: list[Any] = []
    if status_list:
        placeholders = ",".join(["?"] * len(status_list))
        clauses.append(f"status IN ({placeholders})")
        params.extend(status_list)
    if search:
        clauses.append("(LOWER(username) LIKE ? OR LOWER(name) LIKE ? OR LOWER(source) LIKE ?)")
        like = f"%{search.lower()}%"
        params.extend([like, like, like])
    if since_days:
        clauses.append("(last_contacted_at IS NULL OR last_contacted_at >= ?)")
        cutoff = (date.today() - timedelta(days=since_days)).isoformat()
        params.append(cutoff)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    cur = _db.conn.cursor()
    cur.execute(
        f"""
        SELECT username, name, first_name, last_name, bio, tag, source, status, last_account_id, last_contacted_at, fail_reason
        FROM leads
        {where}
        ORDER BY COALESCE(last_contacted_at, '0000-00-00T00:00:00') DESC
        LIMIT ?;
        """,
        (*params, limit),
    )
    rows = cur.fetchall()
    leads: List[Dict[str, Any]] = []
    for (
        username,
        name,
        first_name,
        last_name,
        bio,
        tag,
        source,
        status,
        last_account_id,
        last_contacted_at,
        fail_reason,
    ) in rows:
        leads.append(
            {
                "username": username,
                "name": name or "",
                "first_name": first_name or "",
                "last_name": last_name or "",
                "bio": bio or "",
                "tag": tag or "",
                "source": source or "",
                "status": status or "new",
                "last_account_id": last_account_id,
                "last_contacted_at": last_contacted_at,
                "fail_reason": fail_reason or "",
            }
        )
    return leads


@app.post("/leads/{username}/status")
async def update_lead_status(
    username: str,
    body: LeadStatusUpdate,
    _: AuthUser = Depends(admin_required),
) -> Dict[str, Any]:
    """
    Manually update lead status (kanban drag/drop). Accepts warm/hot/deal/etc.
    """
    new_status = body.status.lower().strip()
    allowed = {"warm", "hot", "deal", "cold", "contacted", "pending", "new", "lost", "failed"}
    if new_status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid status")
    _leads_store.update_status(username, new_status)
    cur = _db.conn.cursor()
    cur.execute(
        """
        SELECT username, name, tag, source, status, last_account_id, last_contacted_at
        FROM leads WHERE username = ?;
        """,
        (username,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Lead not found")
    uname, name, tag, source, status, last_account_id, last_contacted_at = row
    return {
        "username": uname,
        "name": name or "",
        "tag": tag or "",
        "source": source or "",
        "status": status or new_status,
        "last_account_id": last_account_id,
        "last_contacted_at": last_contacted_at,
    }


@app.get("/accounts/{account_id}/dialogs/{username}/messages")
async def dialog_messages(
    account_id: str,
    username: str,
    limit: int = 50,
    _: AuthUser = Depends(admin_required),
) -> List[Dict[str, Any]]:
    return messages_store.get_messages(account_id=account_id, username=username, limit=limit)


@app.get("/logs/events")
async def list_events(limit: int = 200, _: AuthUser = Depends(admin_required)) -> List[Dict[str, Any]]:
    """
    Return the last `limit` events from the TSV log file.
    """
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "events.log.tsv")
    if not os.path.exists(path):
        return []
    lines: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if not lines:
        return []
    header = lines[0].rstrip("\n").split("\t")
    body = lines[1:][-limit:]
    events: List[Dict[str, Any]] = []
    for line in body:
        parts = line.rstrip("\n").split("\t")
        if len(parts) != len(header):
            continue
        events.append(dict(zip(header, parts)))
    return events


@app.post("/accounts/{account_id}/pause")
async def pause_account(account_id: str, _: AuthUser = Depends(admin_required)) -> Dict[str, str]:
    """
    Mark an account as PAUSED at the state level and persist disable override.
    """
    settings = settings_store.get_settings()
    overrides = settings.get("accounts", {}).get("overrides", {})
    overrides[account_id] = {**overrides.get(account_id, {}), "enabled": False}
    settings_store.update_settings({"accounts": {"overrides": overrides}})
    await global_state.set_status(account_id, AccountStatus.PAUSED)
    return {"id": account_id, "status": AccountStatus.PAUSED.name}


@app.post("/accounts/{account_id}/resume")
async def resume_account(account_id: str, _: AuthUser = Depends(admin_required)) -> Dict[str, str]:
    """
    Mark an account as ACTIVE at the state level and persist enable override.
    """
    settings = settings_store.get_settings()
    overrides = settings.get("accounts", {}).get("overrides", {})
    overrides[account_id] = {**overrides.get(account_id, {}), "enabled": True}
    settings_store.update_settings({"accounts": {"overrides": overrides}})
    await global_state.set_status(account_id, AccountStatus.ACTIVE)
    return {"id": account_id, "status": AccountStatus.ACTIVE.name}


class LoginStartResponse(BaseModel):
    status: str


class LoginVerifyBody(BaseModel):
    code: str
    password: str | None = None


class AuthLoginRequest(BaseModel):
    email: str
    code: str


class AuthLoginResponse(BaseModel):
    token: str
    role: str
    email: str


class AuthConfigResponse(BaseModel):
    auth_enabled: bool
    email_code_enabled: bool = True
    code_ttl_seconds: int | None = None
    email_delivery: str | None = None


class AuthCodeRequest(BaseModel):
    email: str


class AccountConfigItem(BaseModel):
    id: str
    api_id: int
    api_hash: str
    phone: str
    session_name: str
    proxy: str | None = None
    timezone: str | None = None
    behavior_profile: str | None = None


class AccountsConfigBody(BaseModel):
    accounts: List[AccountConfigItem]


class SettingsUpdate(BaseModel):
    limits: Dict[str, Any] | None = None
    warmup: Dict[str, Any] | None = None
    outreach: Dict[str, Any] | None = None
    replies: Dict[str, Any] | None = None
    accounts: Dict[str, Any] | None = None


class ManualReplyBody(BaseModel):
    text: str
    attachment_id: int | None = None


@app.post("/auth/login", response_model=AuthLoginResponse)
async def auth_login(body: AuthLoginRequest, request: Request) -> AuthLoginResponse:
    """
    Validate email + one-time code and issue an internal HS256 token.
    """
    _rate_limit(request, "auth_login")
    if not body.email or not body.code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email and code are required")
    token = _auth.login(body.email, body.code)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or code.")
    role = _auth._role_for_email(body.email) or "client"
    return AuthLoginResponse(token=token, role=role, email=body.email.lower())


@app.get("/auth/config", response_model=AuthConfigResponse)
async def auth_config() -> AuthConfigResponse:
    """Expose minimal auth capabilities to the UI (safe to be public)."""
    cfg = _config.auth
    return AuthConfigResponse(
        auth_enabled=cfg.enabled,
        email_code_enabled=True,
        code_ttl_seconds=cfg.code_ttl_seconds if cfg.enabled else None,
        email_delivery="smtp" if cfg.smtp_host else "dev",
    )


@app.post("/auth/request-code")
async def auth_request_code(body: AuthCodeRequest, request: Request) -> dict[str, str]:
    """
    Send a one-time code to the email if it is allowed. Response is generic to avoid user enumeration.
    """
    _rate_limit(request, "auth_code")
    if not body.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email is required")
    _auth.request_code(body.email.lower())
    return {"status": "ok"}


@app.get("/settings")
async def get_settings(_: AuthUser = Depends(admin_required)) -> Dict[str, Any]:
    """
    Return merged settings (defaults + overrides).
    """
    return settings_store.get_settings()


@app.put("/settings")
async def update_settings(body: SettingsUpdate, _: AuthUser = Depends(admin_required)) -> Dict[str, Any]:
    """
    Update settings (deep-merge). Admin-only.
    """
    partial: Dict[str, Any] = {}
    if body.limits is not None:
        partial["limits"] = body.limits
    if body.warmup is not None:
        partial["warmup"] = body.warmup
    if body.outreach is not None:
        partial["outreach"] = body.outreach
    if body.replies is not None:
        partial["replies"] = body.replies
    if body.accounts is not None:
        partial["accounts"] = body.accounts

    merged = settings_store.update_settings(partial)

    # Apply account enable/disable immediately to global_state.
    overrides = merged.get("accounts", {}).get("overrides", {})
    for acc_id, cfg in overrides.items():
        if cfg.get("enabled") is False:
            await global_state.set_status(acc_id, AccountStatus.PAUSED)
        else:
            await global_state.set_status(acc_id, AccountStatus.ACTIVE)

    return merged


@app.post("/admin/restart")
async def admin_restart(_: AuthUser = Depends(admin_required)) -> Dict[str, Any]:
    """
    Request a restart. If ADMIN_RESTART_COMMAND is set, it will be executed
    (non-blocking). Otherwise returns an instructional message to restart via
    process manager (systemd/pm2/docker).
    """
    if _restart_cmd:
        try:
            subprocess.Popen(_restart_cmd, shell=True)  # nosec - admin-only endpoint
            return {"status": "triggered", "message": f"Restart command started: {_restart_cmd}"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to run restart command: {e}")
    return {
        "status": "pending",
        "message": "Set ADMIN_RESTART_COMMAND to enable remote restart. Otherwise restart orchestrator/API via systemd/pm2/docker.",
    }


@app.post("/accounts/{account_id}/dialogs/{username}/reply")
async def manual_reply(
    account_id: str,
    username: str,
    body: ManualReplyBody,
    _: AuthUser = Depends(admin_required),
) -> Dict[str, Any]:
    """
    Record a manual reply for a dialog. This stores the message and logs the event.
    Actual Telegram send would be handled by a worker if wired; currently stored for audit/UI.
    """
    status = await global_state.get_status(account_id)
    if not body.text and body.attachment_id is None:
        raise HTTPException(status_code=400, detail="Empty message")

    if body.attachment_id is not None:
        attachment = attachments_store.get(int(body.attachment_id))
        if not attachment:
            raise HTTPException(status_code=404, detail="Attachment not found")
        body.text = (body.text or "").strip()
        filename = attachment["original_name"] or "file"
        if body.text:
            body.text += f" [file: {filename}]"
        else:
            body.text = f"[file: {filename}]"

    _dialogs_store.mark_manual_reply(username, account_id)

    if status == AccountStatus.ACTIVE:
        messages_store.add_message(account_id=account_id, username=username, direction="out", text=body.text)
        await logs_store.log_event(
            account_id=account_id,
            action_type="MANUAL_REPLY",
            target=username,
            result="ok",
            info=body.text[:200],
        )
        return {"status": "sent", "account_id": account_id, "username": username}

    # Queue for later if account is not active (logout/ban/etc.).
    reason = f"Account status {status.name}"
    outbox_store.add_pending(
        account_id=account_id,
        username=username,
        direction="out",
        text=body.text,
        fail_reason=reason,
    )
    _leads_store.update_status(username, "failed", fail_reason=reason)
    await logs_store.log_event(
        account_id=account_id,
        action_type="MANUAL_REPLY",
        target=username,
        result="queued",
        info=f"{reason}: {body.text[:120]}",
    )
    return {"status": "queued", "account_id": account_id, "username": username, "reason": reason}


@app.post("/attachments/upload")
async def upload_attachment(file: UploadFile = File(...), _: AuthUser = Depends(admin_required)) -> Dict[str, Any]:
    """
    Upload a document to the local attachments store. The file is saved on disk;
    DB keeps only metadata. Returned ID can be attached to manual replies.
    """
    saved = attachments_store.safe_store_upload(file)
    return saved


@app.get("/attachments/{attachment_id}")
async def get_attachment(attachment_id: int, _: AuthUser = Depends(admin_required)):
    att = attachments_store.get(attachment_id)
    if not att or not os.path.exists(att["stored_path"]):
        raise HTTPException(status_code=404, detail="Attachment not found")
    filename = att["original_name"] or f"attachment_{attachment_id}"
    return FileResponse(att["stored_path"], media_type=att["mime_type"] or "application/octet-stream", filename=filename)


@app.get("/landing/summary")
async def landing_summary(_: AuthUser = Depends(client_or_admin)) -> Dict[str, Any]:
    """
    Sanitized snapshot intended for clients/landing: no usernames, phones, or logs.
    """
    metrics = _get_today_metrics()
    aggregate = {
        "cold_sent": 0,
        "replies": 0,
        "hot": 0,
        "warm": 0,
        "cold": 0,
        "warmup_actions": 0,
    }
    for m in metrics.values():
        aggregate["cold_sent"] += m.get("cold_sent", 0)
        aggregate["replies"] += m.get("replies_received", 0)
        aggregate["hot"] += m.get("hot_leads", 0)
        aggregate["warm"] += m.get("warm_leads", 0)
        aggregate["cold"] += m.get("cold_leads", 0)
        aggregate["warmup_actions"] += m.get("warmup_actions", 0)

    status_counts = {"active": 0, "paused": 0}
    for acc in _config.accounts:
        status = await global_state.get_status(acc.id)
        if status == AccountStatus.PAUSED:
            status_counts["paused"] += 1
        else:
            status_counts["active"] += 1

    return {
        "date": date.today().isoformat(),
        "accounts_total": len(_config.accounts),
        "status_counts": status_counts,
        "metrics": aggregate,
    }


@app.get("/client/accounts")
async def client_accounts(_: AuthUser = Depends(client_or_admin)) -> List[Dict[str, Any]]:
    """
    Limited account view for clients: only id + status + aggregate metrics.
    """
    metrics = _get_today_metrics()
    result = []
    for acc in _config.accounts:
        status = await global_state.get_status(acc.id)
        m = metrics.get(acc.id, {})
        result.append(
            {
                "id": acc.id,
                "status": status.name,
                "metrics": m,
            }
        )
    return result


@app.post("/accounts/{account_id}/login/start", response_model=LoginStartResponse)
async def login_start(account_id: str, _: AuthUser = Depends(admin_required)) -> LoginStartResponse:
    """
    Start login flow for a given account by sending a login code to the
    configured phone number. Requires Telethon to be installed and will
    create or reuse the configured session file.
    """
    if TelegramClient is None:
        raise HTTPException(status_code=500, detail="Telethon is not available in this environment.")

    acc = next((a for a in _config.accounts if a.id == account_id), None)
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")

    client = TelegramClient(acc.session_name, acc.api_id, acc.api_hash)  # type: ignore[call-arg]
    await client.connect()
    await client.send_code_request(acc.phone)
    _login_clients[account_id] = client
    return LoginStartResponse(status="code_sent")


@app.post("/accounts/{account_id}/login/verify")
async def login_verify(
    account_id: str,
    body: LoginVerifyBody,
    _: AuthUser = Depends(admin_required),
) -> Dict[str, str]:
    """
    Complete login flow by providing the code (and optional 2FA password).
    """
    if TelegramClient is None:
        raise HTTPException(status_code=500, detail="Telethon is not available in this environment.")

    acc = next((a for a in _config.accounts if a.id == account_id), None)
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")

    client = _login_clients.get(account_id)
    if client is None:
        raise HTTPException(status_code=400, detail="Login has not been started for this account.")

    try:
        await client.sign_in(acc.phone, code=body.code)
    except SessionPasswordNeededError:  # type: ignore[misc]
        if not body.password:
            raise HTTPException(status_code=400, detail="2FA password required.")
        await client.sign_in(password=body.password)

    await client.disconnect()
    _login_clients.pop(account_id, None)
    return {"status": "logged_in"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
