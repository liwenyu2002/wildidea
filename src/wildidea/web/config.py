"""Runtime settings for the WildIdea web app."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_env_file() -> None:
    """Load local development env vars without adding a runtime dependency."""
    env_path = Path(os.environ.get("WILDIDEA_ENV_FILE", _PROJECT_ROOT / ".env"))
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_quotes(value.strip())
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WebSettings:
    database_url: str = os.environ.get("WILDIDEA_DATABASE_URL", f"sqlite:///{_PROJECT_ROOT / 'wildidea.db'}")
    secret_key: str = os.environ.get("WILDIDEA_SECRET_KEY", "wildidea-dev-secret-change-me")
    access_token_ttl_hours: int = int(os.environ.get("WILDIDEA_ACCESS_TOKEN_TTL_HOURS", "168"))
    signup_bonus_credits: int = int(os.environ.get("WILDIDEA_SIGNUP_BONUS_CREDITS", "30"))
    run_credit_cost: int = int(os.environ.get("WILDIDEA_RUN_CREDIT_COST", "1"))
    default_provider: str = os.environ.get("WILDIDEA_PROVIDER", "openrouter")
    default_model: str = os.environ.get("WILDIDEA_MODEL", "anthropic/claude-sonnet-4.5")
    default_judge_model: str = os.environ.get("WILDIDEA_JUDGE_MODEL", "anthropic/claude-sonnet-4.5")
    default_base_url: Optional[str] = os.environ.get("WILDIDEA_BASE_URL")
    default_proxy: Optional[str] = os.environ.get("WILDIDEA_PROXY")
    output_dir: Path = Path(os.environ.get("WILDIDEA_OUTPUT_DIR", str(_PROJECT_ROOT / "outputs" / "web")))
    smtp_host: Optional[str] = os.environ.get("WILDIDEA_SMTP_HOST")
    smtp_port: int = int(os.environ.get("WILDIDEA_SMTP_PORT", "587"))
    smtp_username: Optional[str] = os.environ.get("WILDIDEA_SMTP_USERNAME")
    smtp_password: Optional[str] = os.environ.get("WILDIDEA_SMTP_PASSWORD")
    smtp_from_email: Optional[str] = os.environ.get("WILDIDEA_SMTP_FROM_EMAIL")
    smtp_from_name: str = os.environ.get("WILDIDEA_SMTP_FROM_NAME", "WildIdea")
    smtp_starttls: bool = _env_bool("WILDIDEA_SMTP_STARTTLS", True)
    smtp_ssl: bool = _env_bool("WILDIDEA_SMTP_SSL")
    email_code_ttl_minutes: int = int(os.environ.get("WILDIDEA_EMAIL_CODE_TTL_MINUTES", "10"))
    email_code_resend_seconds: int = int(os.environ.get("WILDIDEA_EMAIL_CODE_RESEND_SECONDS", "60"))
    email_code_ip_limit_per_hour: int = int(os.environ.get("WILDIDEA_EMAIL_CODE_IP_LIMIT_PER_HOUR", "80"))
    email_code_address_limit_per_hour: int = int(os.environ.get("WILDIDEA_EMAIL_CODE_ADDRESS_LIMIT_PER_HOUR", "5"))
    login_ip_limit_per_15m: int = int(os.environ.get("WILDIDEA_LOGIN_IP_LIMIT_PER_15M", "60"))
    login_address_limit_per_15m: int = int(os.environ.get("WILDIDEA_LOGIN_ADDRESS_LIMIT_PER_15M", "15"))
    run_create_user_limit_per_10m: int = int(os.environ.get("WILDIDEA_RUN_CREATE_USER_LIMIT_PER_10M", "12"))
    run_executor: str = os.environ.get("WILDIDEA_RUN_EXECUTOR", "background").strip().lower()
    worker_id: Optional[str] = os.environ.get("WILDIDEA_WORKER_ID")
    worker_poll_seconds: float = float(os.environ.get("WILDIDEA_WORKER_POLL_SECONDS", "2"))
    worker_idle_log_seconds: int = int(os.environ.get("WILDIDEA_WORKER_IDLE_LOG_SECONDS", "60"))
    worker_stale_after_seconds: int = int(os.environ.get("WILDIDEA_WORKER_STALE_AFTER_SECONDS", "7200"))
    run_card_capacity: int = int(os.environ.get("WILDIDEA_RUN_CARD_CAPACITY", "50"))
    user_run_card_limit: int = int(os.environ.get("WILDIDEA_USER_RUN_CARD_LIMIT", "9"))
    user_active_run_limit: int = int(os.environ.get("WILDIDEA_USER_ACTIVE_RUN_LIMIT", "1"))
    fake_runs: bool = _env_bool("WILDIDEA_FAKE_RUNS")
    fake_run_seconds: float = float(os.environ.get("WILDIDEA_FAKE_RUN_SECONDS", "10"))


settings = WebSettings()
