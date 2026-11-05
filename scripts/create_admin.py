"""创建或提升本地管理员。不要做成公开注册接口。

用法：
  python -m scripts.create_admin --username admin --display-name 管理员
  python -m scripts.create_admin --username admin --school 北京大学 --password '...' --display-name 管理员

本地账号的唯一标识是学校 + 工号。未填写 --school 时，若该工号只有一个账号则直接提升；
有多个同工号账号时必须指定学校。
"""

from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import select

from backend.app.core.database import session_scope
from backend.app.core.security import (
    hash_password,
    validate_password,
    validate_school,
    validate_username,
)
from backend.app.models import AuthIdentity, User, UserProfile, UserSettings


async def main() -> None:
    parser = argparse.ArgumentParser(description="创建本地管理员账号")
    parser.add_argument("--username", required=True)
    parser.add_argument("--school", default="")
    parser.add_argument("--display-name", default="管理员")
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    username = validate_username(args.username)
    raw_school = (args.school or "").strip()
    school = validate_school(raw_school) if raw_school else ""
    password = args.password or getpass.getpass("管理员密码: ")
    password = validate_password(password)

    async with session_scope() as session:
        identities = (
            await session.scalars(
                select(AuthIdentity).where(
                    AuthIdentity.provider == "local",
                    AuthIdentity.subject == username,
                )
            )
        ).all()
        if school:
            identities = [item for item in identities if item.school == school]
        elif len(identities) > 1:
            raise SystemExit("存在多个同工号账号，请加上 --school 指定学校")
        identity = identities[0] if identities else None
        if identity:
            user = await session.get(User, identity.user_id)
            if not user:
                raise SystemExit("身份存在但用户不存在")
            user.role = "admin"
            user.status = "active"
            identity.password_hash = hash_password(password)
            label = f"{identity.school} / {username}" if identity.school else username
            print(f"已将现有用户提升为管理员：{label} ({user.id})")
            return

        user = User(display_name=args.display_name, role="admin", status="active")
        session.add(user)
        await session.flush()
        session.add(
            AuthIdentity(
                user_id=user.id,
                provider="local",
                school=school,
                subject=username,
                username=username,
                password_hash=hash_password(password),
            )
        )
        session.add(
            UserProfile(
                user_id=user.id,
                name=args.display_name,
                staff_id=username,
                school=school,
            )
        )
        session.add(UserSettings(user_id=user.id, settings={}))
        label = f"{school} / {username}" if school else username
        print(f"已创建管理员：{label} ({user.id})")


if __name__ == "__main__":
    asyncio.run(main())
