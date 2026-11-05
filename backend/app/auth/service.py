"""登录成功后的共同路径：查找或创建身份，再签发同一套 Session。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.app_settings import get_app_settings
from ..core.audit import audit
from ..models import AuthIdentity, User, UserProfile, UserSettings
from .base import AuthIdentityInfo, AuthProvider
from .local import LocalAuthProvider
from .pku_sso import PKUSSOAuthProvider
from .sessions import create_session, public_user


def get_auth_provider(session: AsyncSession, name: str | None = None) -> AuthProvider:
    settings = get_app_settings()
    mode = name or settings.auth_mode
    if mode == "local":
        return LocalAuthProvider(session)
    if mode == "pku_sso":
        return PKUSSOAuthProvider()
    raise HTTPException(500, "未知认证模式")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _apply_admin_whitelist(user: User, info: AuthIdentityInfo) -> bool:
    settings = get_app_settings()
    hit = (info.provider, info.subject) in settings.admin_identity_set()
    if not hit:
        return False
    if user.role != "admin":
        user.role = "admin"
        return True
    return False


async def complete_login(
    session: AsyncSession,
    info: AuthIdentityInfo,
    request: Request | None = None,
) -> tuple[User, str, dict[str, Any]]:
    identity = await session.scalar(
        select(AuthIdentity).where(
            AuthIdentity.provider == info.provider,
            AuthIdentity.school == (info.school or ""),
            AuthIdentity.subject == info.subject,
        )
    )
    created_user = False
    role_changed = False
    if identity:
        user = await session.get(User, identity.user_id)
        if not user:
            raise HTTPException(401, "账号不存在")
        identity.last_authenticated_at = _now()
    else:
        user = User(
            display_name=info.display_name or info.username or "用户",
            role="user",
            status="active",
        )
        session.add(user)
        await session.flush()
        identity = AuthIdentity(
            user_id=user.id,
            provider=info.provider,
            school=info.school or "",
            subject=info.subject,
            username=info.username,
            password_hash=None,
            provider_data=info.provider_data or None,
            last_authenticated_at=_now(),
        )
        session.add(identity)
        session.add(
            UserProfile(
                user_id=user.id,
                name=info.display_name or "",
            )
        )
        session.add(UserSettings(user_id=user.id, settings={}))
        created_user = True

    if user.status != "active":
        await audit(
            session,
            request,
            action="login_rejected",
            actor_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            details={"reason": "disabled", "provider": info.provider},
        )
        raise HTTPException(403, "账号已停用")

    role_changed = await _apply_admin_whitelist(user, info)
    user.last_login_at = _now()
    user.updated_at = _now()
    token = await create_session(session, user.id, request)

    await audit(
        session,
        request,
        action="register" if created_user else "login_success",
        actor_user_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        details={"provider": info.provider, "created": created_user},
    )
    if role_changed:
        await audit(
            session,
            request,
            action="role_change",
            actor_user_id=user.id,
            target_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            details={"role": "admin", "reason": "admin_identities"},
        )
    payload = await public_user(session, user)
    return user, token, payload


def new_user_id() -> uuid.UUID:
    return uuid.uuid4()
