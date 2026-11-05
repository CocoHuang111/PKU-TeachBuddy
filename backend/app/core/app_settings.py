"""业务运行时配置。认证模式、数据库和 Session 只读环境变量，前端不能改。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from ai_engine.config import ROOT


def _bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _csv(name: str) -> list[str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name) or default)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是正整数") from exc
    if value < 1:
        raise ValueError(f"{name} 必须是正整数")
    return value


def _nonnegative_int(name: str, default: int = 0) -> int:
    try:
        value = int(os.getenv(name) or default)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是非负整数") from exc
    if value < 0:
        raise ValueError(f"{name} 必须是非负整数")
    return value


class AppSettings:
    def __init__(self) -> None:
        self.app_env = (os.getenv("APP_ENV") or "development").strip().lower()
        self.auth_mode = (os.getenv("AUTH_MODE") or "local").strip().lower()
        if self.auth_mode not in {"local", "pku_sso"}:
            raise ValueError("AUTH_MODE 只能是 local 或 pku_sso")

        self.database_url = (
            os.getenv("DATABASE_URL")
            or "postgresql+asyncpg://pku2:pku2@127.0.0.1:5432/pku2"
        ).strip()
        self.session_secret = (os.getenv("SESSION_SECRET") or "").strip()
        if not self.session_secret:
            if self.app_env == "production":
                raise ValueError("生产环境必须设置 SESSION_SECRET")
            self.session_secret = "dev-only-session-secret-change-me"

        upload = (os.getenv("UPLOAD_ROOT") or "").strip()
        self.upload_root = Path(upload).resolve() if upload else (ROOT / "data" / "uploads")

        self.local_registration_enabled = _bool("LOCAL_REGISTRATION_ENABLED", True)
        self.local_registration_invite_code = (
            os.getenv("LOCAL_REGISTRATION_INVITE_CODE") or ""
        ).strip()
        self.local_registration_max_uses = _nonnegative_int(
            "LOCAL_REGISTRATION_MAX_USES"
        )

        self.pku_sso_client_id = (os.getenv("PKU_SSO_CLIENT_ID") or "").strip()
        self.pku_sso_client_secret = (os.getenv("PKU_SSO_CLIENT_SECRET") or "").strip()
        self.pku_sso_authorize_url = (os.getenv("PKU_SSO_AUTHORIZE_URL") or "").strip()
        self.pku_sso_token_url = (os.getenv("PKU_SSO_TOKEN_URL") or "").strip()
        self.pku_sso_userinfo_url = (os.getenv("PKU_SSO_USERINFO_URL") or "").strip()
        self.pku_sso_redirect_uri = (os.getenv("PKU_SSO_REDIRECT_URI") or "").strip()

        self.admin_identities = _csv("ADMIN_IDENTITIES")
        self.session_ttl_sec = int(os.getenv("SESSION_TTL_SEC") or 14 * 24 * 3600)
        self.password_min_length = int(os.getenv("PASSWORD_MIN_LENGTH") or 8)
        self.cookie_name = (os.getenv("SESSION_COOKIE_NAME") or "pku_session").strip()
        self.login_rate_limit = int(os.getenv("LOGIN_RATE_LIMIT") or 10)
        self.login_rate_window_sec = int(os.getenv("LOGIN_RATE_WINDOW_SEC") or 15 * 60)
        self.qa_max_concurrency = _positive_int("QA_MAX_CONCURRENCY", 4)
        self.syllabus_max_concurrency = _positive_int("SYLLABUS_MAX_CONCURRENCY", 2)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_local_auth(self) -> bool:
        return self.auth_mode == "local"

    @property
    def is_pku_sso(self) -> bool:
        return self.auth_mode == "pku_sso"

    @property
    def registration_open(self) -> bool:
        return self.is_local_auth and self.local_registration_enabled

    @property
    def invite_required(self) -> bool:
        return bool(self.local_registration_invite_code)

    @property
    def pku_sso_configured(self) -> bool:
        return all(
            [
                self.pku_sso_client_id,
                self.pku_sso_client_secret,
                self.pku_sso_authorize_url,
                self.pku_sso_token_url,
                self.pku_sso_userinfo_url,
                self.pku_sso_redirect_uri,
            ]
        )

    @property
    def database_url_sync(self) -> str:
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return "postgresql+psycopg://" + url.split("://", 1)[1]
        if url.startswith("postgresql+psycopg://"):
            return url
        if url.startswith("postgresql://"):
            return "postgresql+psycopg://" + url.split("://", 1)[1]
        return url

    def parse_admin_identity(self, item: str) -> tuple[str, str] | None:
        if ":" not in item:
            return None
        provider, subject = item.split(":", 1)
        provider = provider.strip()
        subject = subject.strip()
        if not provider or not subject:
            return None
        return provider, subject

    def admin_identity_set(self) -> set[tuple[str, str]]:
        found: set[tuple[str, str]] = set()
        for item in self.admin_identities:
            parsed = self.parse_admin_identity(item)
            if parsed:
                found.add(parsed)
        return found


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    return AppSettings()


def reset_app_settings() -> None:
    get_app_settings.cache_clear()
