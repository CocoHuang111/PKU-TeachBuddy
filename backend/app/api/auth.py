from __future__ import annotations

import secrets
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy import func, select

from ..auth.pku_sso import PKUSSOAuthProvider, PKUSSONotConfigured
from ..auth.service import complete_login
from ..auth.sessions import (
    clear_session_cookie,
    public_user,
    read_session_token,
    revoke_session,
    set_session_cookie,
)
from ..core.app_settings import get_app_settings
from ..core.audit import audit
from ..core.auth import current_user
from ..core.database import session_scope
from ..core.rate_limit import check_login_rate, clear_login_failures, record_login_failure
from ..core.security import (
    hash_password,
    normalize_school,
    normalize_username,
    validate_password,
    validate_school,
    validate_username,
    verify_password,
)
from ..core.uploads import record_upload, save_avatar
from ..models import AuditLog, AuthIdentity, StoredFile, User, UserProfile, UserSettings
from ..schemas import (
    ChangePasswordForm,
    LoginForm,
    ProfileUpdateForm,
    RegisterForm,
    UserSettingsForm,
)

router = APIRouter(prefix="/api/auth", tags=["账号"])

# PostgreSQL transaction lock serializes registration across backend processes.
_REGISTRATION_QUOTA_LOCK_KEY = 0x5445414348425544


def _auth_config() -> dict:
    settings = get_app_settings()
    return {
        "auth_mode": settings.auth_mode,
        "registration_enabled": settings.registration_open,
        "invite_required": settings.registration_open and settings.invite_required,
        "pku_sso_ready": settings.pku_sso_configured,
        "password_min_length": settings.password_min_length,
    }


@router.get("/config")
async def auth_config() -> dict:
    return _auth_config()


@router.post("/register")
async def register(form: RegisterForm, request: Request, response: Response) -> dict:
    settings = get_app_settings()
    if not settings.registration_open:
        raise HTTPException(403, "当前未开放注册")
    if settings.invite_required and form.invite_code != settings.local_registration_invite_code:
        raise HTTPException(403, "邀请码不正确")
    if form.password != form.confirm_password:
        raise HTTPException(400, "两次输入的密码不一致")
    try:
        school = validate_school(form.school)
        username = validate_username(form.username)
        password = validate_password(form.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    display_name = (form.display_name or username).strip()
    async with session_scope() as session:
        if settings.local_registration_max_uses:
            await session.execute(
                select(func.pg_advisory_xact_lock(_REGISTRATION_QUOTA_LOCK_KEY))
            )
        existing = await session.scalar(
            select(AuthIdentity).where(
                AuthIdentity.provider == "local",
                AuthIdentity.school == school,
                AuthIdentity.subject == username,
            )
        )
        if existing:
            raise HTTPException(409, "该学校的工号已被使用")
        if settings.local_registration_max_uses:
            used = await session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.action == "register",
                    AuditLog.details["provider"].astext == "local",
                )
            )
            if used >= settings.local_registration_max_uses:
                raise HTTPException(403, "内测名额已满，暂不接受新用户注册")
        user = User(
            display_name=display_name,
            role="user",
            status="active",
            last_login_at=datetime.now(timezone.utc),
        )
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
                last_authenticated_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            UserProfile(
                user_id=user.id,
                name=display_name,
                staff_id=username,
                school=school,
            )
        )
        from ..models import UserSettings

        session.add(UserSettings(user_id=user.id, settings={}))
        from ..auth.sessions import create_session

        token = await create_session(session, user.id, request)
        await audit(
            session,
            request,
            action="register",
            actor_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            details={"provider": "local", "username": username, "school": school},
        )
        payload = await public_user(session, user)
    set_session_cookie(response, token)
    return {"user": payload}


@router.post("/login")
async def login(form: LoginForm, request: Request, response: Response) -> dict:
    settings = get_app_settings()
    if not settings.is_local_auth:
        raise HTTPException(403, "当前未启用本地登录")
    school = normalize_school(form.school)
    username = normalize_username(form.username)
    rate_key = f"{request.client.host if request.client else 'unknown'}:{school}:{username}"
    check_login_rate(rate_key)
    async with session_scope() as session:
        identity = await session.scalar(
            select(AuthIdentity).where(
                AuthIdentity.provider == "local",
                AuthIdentity.school == school,
                AuthIdentity.subject == username,
            )
        )
        if not identity:
            record_login_failure(rate_key)
            await audit(
                session,
                request,
                action="login_failed",
                resource_type="auth_identity",
                details={"provider": "local"},
            )
            raise HTTPException(401, "学校和工号不匹配")
        if not identity.password_hash or not verify_password(
            form.password, identity.password_hash
        ):
            record_login_failure(rate_key)
            await audit(
                session,
                request,
                action="login_failed",
                resource_type="auth_identity",
                details={"provider": "local"},
            )
            raise HTTPException(401, "密码错误")
        user = await session.get(User, identity.user_id)
        if not user:
            record_login_failure(rate_key)
            raise HTTPException(401, "学校和工号不匹配")
        from ..auth.base import AuthIdentityInfo

        _, token, payload = await complete_login(
            session,
            AuthIdentityInfo(
                provider="local",
                subject=username,
                school=school,
                username=username,
                display_name=user.display_name,
            ),
            request,
        )
    clear_login_failures(rate_key)
    set_session_cookie(response, token)
    return {"user": payload}


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    token = read_session_token(request)
    async with session_scope() as session:
        user = None
        if token:
            from ..auth.sessions import load_session_user

            user = await load_session_user(session, token)
            await revoke_session(session, token)
        await audit(
            session,
            request,
            action="logout",
            actor_user_id=user.id if user else None,
            resource_type="auth_session",
        )
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(current_user)) -> dict:
    return {k: v for k, v in user.items() if not k.startswith("_")}


@router.patch("/me")
async def update_me(
    form: ProfileUpdateForm, user: dict = Depends(current_user)
) -> dict:
    payload = form.model_dump(exclude_unset=True)
    payload.pop("staff_id", None)
    payload.pop("role", None)
    payload.pop("status", None)
    if "school" in payload:
        try:
            payload["school"] = validate_school(payload.get("school") or "")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    async with session_scope() as session:
        db_user = await session.get(User, user["_id"])
        if not db_user:
            raise HTTPException(404, "用户不存在")
        profile = await session.get(UserProfile, db_user.id)
        if profile is None:
            profile = UserProfile(user_id=db_user.id)
            session.add(profile)
        if "school" in payload:
            identity = await session.scalar(
                select(AuthIdentity).where(
                    AuthIdentity.user_id == db_user.id,
                    AuthIdentity.provider == "local",
                )
            )
            if identity is not None and identity.school != payload["school"]:
                taken = await session.scalar(
                    select(AuthIdentity.id).where(
                        AuthIdentity.provider == "local",
                        AuthIdentity.school == payload["school"],
                        AuthIdentity.subject == identity.subject,
                        AuthIdentity.id != identity.id,
                    )
                )
                if taken:
                    raise HTTPException(409, "该学校的工号已被使用")
                identity.school = payload["school"]
        for key, value in payload.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        if "name" in payload:
            db_user.display_name = payload["name"]
        profile.updated_at = datetime.now(timezone.utc)
        db_user.updated_at = profile.updated_at
        return await public_user(session, db_user)


@router.get("/settings")
async def get_settings(user: dict = Depends(current_user)) -> dict:
    async with session_scope() as session:
        row = await session.get(UserSettings, user["_id"])
        return {"settings": (row.settings if row else {}) or {}}


@router.patch("/settings")
async def update_settings(
    form: UserSettingsForm, user: dict = Depends(current_user)
) -> dict:
    allowed = {"default_corpora", "syllabus_prompt_mode", "export_format"}
    incoming = {k: v for k, v in (form.settings or {}).items() if k in allowed}
    async with session_scope() as session:
        await session.scalar(select(User).where(User.id == user["_id"]).with_for_update())
        row = await session.scalar(select(UserSettings).where(UserSettings.user_id == user["_id"]).with_for_update())
        if row is None:
            row = UserSettings(user_id=user["_id"], settings=incoming)
            session.add(row)
        else:
            merged = dict(row.settings or {})
            merged.update(incoming)
            row.settings = merged
        row.updated_at = datetime.now(timezone.utc)
        return {"settings": row.settings}


@router.post("/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: dict = Depends(current_user),
) -> dict:
    path, key = await asyncio.to_thread(save_avatar, file, user["id"])
    file_id = await record_upload(
        user_id=user["id"],
        purpose="avatar",
        original_name=file.filename or "avatar",
        storage_key=key,
        mime_type=file.content_type,
        path=path,
    )
    async with session_scope() as session:
        profile = await session.get(UserProfile, user["_id"])
        if profile is None:
            profile = UserProfile(user_id=user["_id"])
            session.add(profile)
        if profile.avatar_file_id:
            old = await session.get(StoredFile, profile.avatar_file_id)
            if old and old.user_id == user["_id"] and old.storage_backend == "oss":
                old.deleted_at = datetime.now(timezone.utc)
        profile.avatar_file_id = __import__("uuid").UUID(file_id)
        profile.updated_at = datetime.now(timezone.utc)
        db_user = await session.get(User, user["_id"])
        result = await public_user(session, db_user)
    from ..core.material_storage import upload_backend
    if upload_backend() == "oss":
        from pathlib import Path
        Path(path).unlink(missing_ok=True)
    return result


@router.get("/me/avatar")
async def get_avatar(user: dict = Depends(current_user)):
    from fastapi.responses import FileResponse

    async with session_scope() as session:
        profile = await session.get(UserProfile, user["_id"])
        if not profile or not profile.avatar_file_id:
            raise HTTPException(404, "还没有头像")
        stored = await session.get(StoredFile, profile.avatar_file_id)
        if not stored or stored.deleted_at is not None or stored.user_id != user["_id"]:
            raise HTTPException(404, "还没有头像")
        from ..core.db import stored_file_disk_path

        path = await asyncio.to_thread(stored_file_disk_path, stored.storage_key, stored.storage_backend)
    if not path.is_file():
        raise HTTPException(404, "还没有头像")
    return FileResponse(path, media_type=stored.mime_type or "image/jpeg")


@router.post("/change-password")
async def change_password(
    form: ChangePasswordForm,
    request: Request,
    user: dict = Depends(current_user),
) -> dict:
    settings = get_app_settings()
    if not settings.is_local_auth:
        raise HTTPException(403, "当前账号密码由统一身份认证管理")
    if form.new_password != form.confirm_password:
        raise HTTPException(400, "两次输入的密码不一致")
    try:
        new_password = validate_password(form.new_password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    async with session_scope() as session:
        identity = await session.scalar(
            select(AuthIdentity).where(
                AuthIdentity.user_id == user["_id"],
                AuthIdentity.provider == "local",
            )
        )
        if not identity or not identity.password_hash:
            raise HTTPException(400, "当前账号没有本地密码")
        if not verify_password(form.old_password, identity.password_hash):
            raise HTTPException(400, "原密码不正确")
        identity.password_hash = hash_password(new_password)
        await audit(
            session,
            request,
            action="password_change",
            actor_user_id=user["_id"],
            resource_type="user",
            resource_id=user["id"],
        )
    return {"ok": True}


@router.get("/pku/start")
async def pku_start(request: Request) -> dict:
    settings = get_app_settings()
    if not settings.is_pku_sso:
        raise HTTPException(403, "当前未启用北京大学统一身份认证")
    state = secrets.token_urlsafe(16)
    request.session_state = state  # type: ignore[attr-defined]
    try:
        url = PKUSSOAuthProvider().start_url(state)
    except PKUSSONotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    return {"authorize_url": url, "state": state}


@router.get("/pku/callback")
async def pku_callback(request: Request, response: Response) -> dict:
    settings = get_app_settings()
    if not settings.is_pku_sso:
        raise HTTPException(403, "当前未启用北京大学统一身份认证")
    provider = PKUSSOAuthProvider(allow_mock=not settings.is_production)
    info = await provider.exchange_callback(
        code=request.query_params.get("code"),
        state=request.query_params.get("state"),
        mock=request.query_params.get("mock") == "1",
        subject=request.query_params.get("subject"),
    )
    async with session_scope() as session:
        _, token, payload = await complete_login(session, info, request)
    set_session_cookie(response, token)
    return {"user": payload}
