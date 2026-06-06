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
    dingtalk_sync_enabled: bool = _env_bool("DINGTALK_SYNC_ENABLED")
    dingtalk_api_base_url: str = os.environ.get("DINGTALK_API_BASE_URL", "https://api.dingtalk.com")
    dingtalk_app_key: Optional[str] = os.environ.get("DINGTALK_APP_KEY")
    dingtalk_app_secret: Optional[str] = os.environ.get("DINGTALK_APP_SECRET")
    dingtalk_operator_id: Optional[str] = os.environ.get("DINGTALK_OPERATOR_ID")
    dingtalk_ai_table_base_id: Optional[str] = os.environ.get("DINGTALK_AI_TABLE_BASE_ID")
    dingtalk_feedback_sheet_id: Optional[str] = os.environ.get("DINGTALK_FEEDBACK_SHEET_ID")
    dingtalk_feedback_field_map: str = os.environ.get("DINGTALK_FEEDBACK_FIELD_MAP", "")
    dingtalk_timeout_seconds: int = int(os.environ.get("DINGTALK_TIMEOUT_SECONDS", "15"))
    dingtalk_sync_batch_size: int = int(os.environ.get("DINGTALK_SYNC_BATCH_SIZE", "20"))


settings = WebSettings()
