import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dotenv import load_dotenv


@dataclass
class AccountConfig:
    """Static configuration for a single Telegram account."""

    id: str
    api_id: int
    api_hash: str
    phone: str
    session_name: str
    proxy: Optional[str] = None
    timezone: Optional[str] = None
    behavior_profile: Optional[str] = None


@dataclass
class LimitsConfig:
    """High‑level rate limits for safety tuning."""

    max_cold_per_account_per_day: int = 15
    max_cold_global_per_day: int = 80
    max_concurrent_heavy_actions: int = 2
    # Soft pacing limits (optional; 0 disables)
    min_cold_interval_seconds: int = 0
    max_cold_per_hour_per_account: int = 0
    # Scale knob: conservative / normal / aggressive
    mode: str = "conservative"


@dataclass
class BehaviorConfig:
    """Names of behavior profiles and defaults."""

    default_profile: str = "default"
    profiles: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class AIConfig:
    """AI / OpenRouter configuration shared across engines."""

    api_key: Optional[str]
    model: str = "anthropic/claude-3.5-sonnet"
    referer: str = "http://localhost"
    title: str = "Telegram Orchestrator"
    # Privacy knobs: try to opt-out of training/retention where supported.
    privacy_mode: str = "high"  # high/standard
    send_do_not_store_header: bool = True


@dataclass
class AuthConfig:
    """
    Authentication / RBAC configuration for the UI and landing.

    - enabled: True if AUTH_SHARED_SECRET is provided.
    - allowed_admin_emails: exact emails that may access full UI.
    - allowed_client_emails: exact emails that may access the landing-only view.
    - allowed_domains: optional list of domains allowed for either role.
    """

    enabled: bool
    secret: str
    allowed_admin_emails: List[str] = field(default_factory=list)
    allowed_client_emails: List[str] = field(default_factory=list)
    allowed_domains: List[str] = field(default_factory=list)
    code_ttl_seconds: int = 300  # validity window for login code
    token_ttl_seconds: int = 86400  # 24h JWT lifetime
    passwordless_allowed: bool = False
    # SMTP for login code delivery
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_use_tls: bool = True
    max_code_attempts: int = 5
    codes_dev_dir: str = "data/login_codes"


@dataclass
class AppConfig:
    """Top‑level application configuration snapshot."""

    accounts: List[AccountConfig]
    limits: LimitsConfig
    behavior: BehaviorConfig
    ai: AIConfig
    auth: AuthConfig


def _load_env(env_path: Optional[str] = None) -> None:
    """
    Load environment variables from .env near the project root.

    This mirrors the existing scripts but is kept local to the
    new orchestration layer so that we do not change old behavior.
    """
    if env_path and os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path)
    else:
        # Fallback: rely on default discovery, as existing scripts do.
        load_dotenv()


def _load_accounts_from_env() -> List[AccountConfig]:
    """
    Read account configuration from the existing .env format:

    - ACCOUNTS=account10,account11,...
    - For each suffix:
        {SUFFIX}_API_ID
        {SUFFIX}_API_HASH
        {SUFFIX}_PHONE
        {SUFFIX}_SESSION   (new, unified session name)
        {SUFFIX}_PROXY     (optional)
        {SUFFIX}_TZ        (optional timezone string)
        {SUFFIX}_BEHAVIOR_PROFILE (optional behavior profile name)

    We keep this flexible so that current .env files can be
    extended gradually without breaking existing scripts.
    """
    accounts_env = os.getenv("ACCOUNTS", "")
    suffixes = [s.strip() for s in accounts_env.split(",") if s.strip()]
    accounts: List[AccountConfig] = []

    for suffix in suffixes:
        api_id = os.getenv(f"{suffix}_API_ID")
        api_hash = os.getenv(f"{suffix}_API_HASH")
        phone = os.getenv(f"{suffix}_PHONE")
        # Unified session name for the new orchestrator
        session_name = os.getenv(f"{suffix}_SESSION")
        proxy = os.getenv(f"{suffix}_PROXY")
        tz = os.getenv(f"{suffix}_TZ")
        behavior_profile = os.getenv(f"{suffix}_BEHAVIOR_PROFILE")

        if not all([api_id, api_hash, phone, session_name]):
            # We intentionally log via print here; logging will be wired
            # in at a higher level once the orchestrator is fully in place.
            print(
                f"[config] Skipping account '{suffix}': "
                f"one of API_ID/API_HASH/PHONE/SESSION is missing."
            )
            continue

        try:
            api_id_int = int(api_id)
        except (TypeError, ValueError):
            print(f"[config] Skipping account '{suffix}': invalid API_ID={api_id!r}.")
            continue

        accounts.append(
            AccountConfig(
                id=suffix,
                api_id=api_id_int,
                api_hash=api_hash,
                phone=phone,
                session_name=session_name,
                proxy=proxy,
                timezone=tz,
                behavior_profile=behavior_profile,
            )
        )

    return accounts


def _load_limits_from_env() -> LimitsConfig:
    def _int(name: str, default: int) -> int:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    mode = os.getenv("LIMITS_MODE", "conservative").strip().lower()

    return LimitsConfig(
        max_cold_per_account_per_day=_int("MAX_COLD_PER_ACCOUNT_PER_DAY", 15),
        max_cold_global_per_day=_int("MAX_COLD_GLOBAL_PER_DAY", 80),
        max_concurrent_heavy_actions=_int("MAX_CONCURRENT_HEAVY_ACTIONS", 2),
        min_cold_interval_seconds=_int("MIN_COLD_INTERVAL_SECONDS", 0),
        max_cold_per_hour_per_account=_int("MAX_COLD_PER_HOUR_PER_ACCOUNT", 0),
        mode=mode,
    )


def _load_behavior_from_env() -> BehaviorConfig:
    """
    For MVP we support only a default profile.
    More detailed YAML‑based profiles can be added later.
    """
    default_profile = os.getenv("DEFAULT_BEHAVIOR_PROFILE", "default")
    return BehaviorConfig(default_profile=default_profile, profiles={})


def _load_ai_from_env() -> AIConfig:
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
    referer = os.getenv("OPENROUTER_REFERER", "http://localhost")
    title = os.getenv("OPENROUTER_X_TITLE", "Telegram Orchestrator")
    privacy_mode = os.getenv("OPENROUTER_PRIVACY_MODE", "high").strip().lower() or "high"
    send_do_not_store_header = os.getenv("OPENROUTER_DO_NOT_STORE", "1").strip() not in (
        "",
        "0",
        "false",
    )
    return AIConfig(
        api_key=api_key,
        model=model,
        referer=referer,
        title=title,
        privacy_mode=privacy_mode,
        send_do_not_store_header=send_do_not_store_header,
    )


def _load_auth_from_env() -> AuthConfig:
    secret = os.getenv("AUTH_SHARED_SECRET", "")
    enabled = bool(secret)

    def _split(name: str) -> List[str]:
        raw = os.getenv(name, "")
        return [p.strip().lower() for p in raw.split(",") if p.strip()]

    allowed_admin_emails = _split("AUTH_ALLOWED_ADMIN_EMAILS")
    allowed_client_emails = _split("AUTH_ALLOWED_CLIENT_EMAILS")
    allowed_domains = _split("AUTH_ALLOWED_EMAIL_DOMAINS")

    def _int(name: str, default: int) -> int:
        try:
            raw = os.getenv(name)
            return int(raw) if raw is not None else default
        except Exception:
            return default

    return AuthConfig(
        enabled=enabled,
        secret=secret,
        allowed_admin_emails=allowed_admin_emails,
        allowed_client_emails=allowed_client_emails,
        allowed_domains=allowed_domains,
        code_ttl_seconds=_int("AUTH_CODE_TTL_SECONDS", 300),
        token_ttl_seconds=_int("AUTH_TOKEN_TTL_SECONDS", 86400),
        passwordless_allowed=os.getenv("AUTH_PASSWORDLESS", "false").strip().lower() in ("1", "true", "yes"),
        smtp_host=os.getenv("SMTP_HOST"),
        smtp_port=_int("SMTP_PORT", 587),
        smtp_user=os.getenv("SMTP_USER"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        smtp_from=os.getenv("SMTP_FROM"),
        smtp_use_tls=os.getenv("SMTP_USE_TLS", "true").strip().lower() in ("1", "true", "yes"),
        max_code_attempts=_int("AUTH_MAX_CODE_ATTEMPTS", 5),
        codes_dev_dir=os.getenv("AUTH_CODES_DEV_DIR", "data/login_codes"),
    )


def load_app_config(env_path: Optional[str] = None) -> AppConfig:
    """
    Public entry point for building a full configuration snapshot
    for the new orchestrator.
    """
    _load_env(env_path)
    accounts = _load_accounts_from_env()
    limits = _load_limits_from_env()
    behavior = _load_behavior_from_env()
    ai = _load_ai_from_env()
    auth = _load_auth_from_env()

    if not accounts:
        print("[config] WARNING: no accounts configured for orchestrator.")

    if not auth.enabled:
        print("[config] WARNING: AUTH_SHARED_SECRET missing – API/UI auth is disabled.")

    return AppConfig(
        accounts=accounts,
        limits=limits,
        behavior=behavior,
        ai=ai,
        auth=auth,
    )
