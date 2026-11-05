"""密码哈希、Session 令牌与用户名规范化。不把原始令牌写入日志或数据库。"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .app_settings import get_app_settings

_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")


def normalize_username(raw: str) -> str:
    return (raw or "").strip().lower()


def normalize_school(raw: str) -> str:
    """折叠空白并忽略英文大小写，使同一学校名称只对应一个登录标识。"""
    return " ".join((raw or "").strip().split()).casefold()


def validate_school(raw: str) -> str:
    school = normalize_school(raw)
    if not school:
        raise ValueError("请填写学校")
    if len(school) > 80:
        raise ValueError("学校名称不能超过 80 字")
    return school


def validate_username(raw: str) -> str:
    username = normalize_username(raw)
    if not USERNAME_RE.match(username):
        raise ValueError("工号需为 3–32 位小写字母、数字、点、下划线或连字符")
    return username


def validate_password(password: str) -> str:
    text = password or ""
    minimum = get_app_settings().password_min_length
    if len(text) < minimum:
        raise ValueError(f"密码至少 {minimum} 位")
    if len(text) > 64:
        raise ValueError("密码不能超过 64 位")
    return text


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    try:
        return _HASHER.verify(stored, password)
    except (VerifyMismatchError, ValueError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    secret = get_app_settings().session_secret.encode("utf-8")
    return hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_invite_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()
