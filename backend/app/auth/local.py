from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import normalize_school, normalize_username, verify_password
from ..models import AuthIdentity
from .base import AuthIdentityInfo


class LocalAuthProvider:
    name = "local"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def authenticate(self, **credentials: Any) -> AuthIdentityInfo:
        school = normalize_school(str(credentials.get("school") or ""))
        username = normalize_username(str(credentials.get("username") or ""))
        password = str(credentials.get("password") or "")
        row = await self.session.scalar(
            select(AuthIdentity).where(
                AuthIdentity.provider == "local",
                AuthIdentity.school == school,
                AuthIdentity.subject == username,
            )
        )
        if not row:
            raise HTTPException(401, "学校和工号不匹配")
        if not row.password_hash or not verify_password(password, row.password_hash):
            raise HTTPException(401, "密码错误")
        return AuthIdentityInfo(
            provider="local",
            subject=username,
            school=row.school or "",
            username=row.username or username,
            display_name=row.username or username,
            provider_data={},
        )

    async def get_identity(self, subject: str) -> AuthIdentityInfo:
        username = normalize_username(subject)
        rows = (
            await self.session.scalars(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "local",
                    AuthIdentity.subject == username,
                )
            )
        ).all()
        if len(rows) != 1:
            raise HTTPException(401, "学校和工号不匹配" if not rows else "请填写学校")
        row = rows[0]
        return AuthIdentityInfo(
            provider="local",
            subject=username,
            school=row.school or "",
            username=row.username or username,
            display_name=row.username or username,
            provider_data={},
        )
