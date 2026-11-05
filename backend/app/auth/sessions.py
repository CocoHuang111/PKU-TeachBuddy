from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.app_settings import get_app_settings
from ..core.audit import client_ip, client_ua
from ..core.security import hash_session_token, new_session_token
from ..models import AuthIdentity, AuthSession, StoredFile, User, UserProfile


def _now() -> datetime:
    return datetime.now(timezone.utc)


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_app_settings()
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.session_ttl_sec,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_app_settings()
    response.delete_cookie(settings.cookie_name, path="/")


def read_session_token(request: Request) -> str:
    settings = get_app_settings()
    return (request.cookies.get(settings.cookie_name) or "").strip()


async def create_session(
    session: AsyncSession,
    user_id: uuid.UUID,
    request: Request | None = None,
) -> str:
    settings = get_app_settings()
    token = new_session_token()
    now = _now()
    session.add(
        AuthSession(
            user_id=user_id,
            token_hash=hash_session_token(token),
            created_at=now,
            expires_at=now + timedelta(seconds=settings.session_ttl_sec),
            last_seen_at=now,
            ip_address=client_ip(request),
            user_agent=client_ua(request),
        )
    )
    return token


async def load_session_user(session: AsyncSession, token: str) -> User | None:
    if not token:
        return None
    row = await session.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_session_token(token))
    )
    if not row or row.revoked_at is not None:
        return None
    now = _now()
    if row.expires_at <= now:
        return None
    user = await session.get(User, row.user_id)
    if user is None or user.status != "active":
        return None
    row.last_seen_at = now
    return user


async def revoke_session(session: AsyncSession, token: str) -> None:
    if not token:
        return
    row = await session.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_session_token(token))
    )
    if row and row.revoked_at is None:
        row.revoked_at = _now()


async def revoke_user_sessions(session: AsyncSession, user_id: uuid.UUID) -> int:
    rows = (
        await session.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
            )
        )
    ).all()
    now = _now()
    for row in rows:
        row.revoked_at = now
    return len(rows)


async def public_user(session: AsyncSession, user: User) -> dict[str, Any]:
    profile = user.profile
    if profile is None:
        profile = await session.get(UserProfile, user.id)
    identities = (
        await session.scalars(
            select(AuthIdentity).where(AuthIdentity.user_id == user.id)
        )
    ).all()
    avatar_url = None
    if profile and profile.avatar_file_id:
        stored = await session.get(StoredFile, profile.avatar_file_id)
        if stored and stored.deleted_at is None:
            avatar_url = "/api/auth/me/avatar"
    local = next((item for item in identities if item.provider == "local"), None)
    return {
        "id": str(user.id),
        "role": user.role,
        "status": user.status,
        "display_name": user.display_name,
        "username": local.username if local else None,
        "providers": [item.provider for item in identities],
        "name": profile.name if profile else user.display_name,
        "staff_id": profile.staff_id if profile else "",
        "school": (
            profile.school
            if profile and profile.school
            else (local.school if local else "")
        ),
        "title": profile.title if profile else "",
        "department": profile.department if profile else "",
        "email": profile.email if profile else "",
        "phone": profile.phone if profile else "",
        "courses": profile.courses if profile else "",
        "bio": profile.bio if profile else "",
        "avatar": avatar_url or "",
        "created_at": user.created_at.timestamp() if user.created_at else None,
        "last_login_at": user.last_login_at.timestamp() if user.last_login_at else None,
    }


async def get_current_user(request: Request) -> dict[str, Any]:
    from ..core.database import session_scope

    token = read_session_token(request)
    if not token:
        raise HTTPException(401, "请先登录")
    async with session_scope() as session:
        user = await load_session_user(session, token)
        if not user:
            raise HTTPException(401, "登录已失效，请重新登录")
        payload = await public_user(session, user)
        payload["_id"] = user.id
        return payload


async def require_admin(request: Request) -> dict[str, Any]:
    user = await get_current_user(request)
    if user.get("role") != "admin" or user.get("status") != "active":
        raise HTTPException(403, "需要管理员权限")
    return user
