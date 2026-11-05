from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select

from ..auth.sessions import public_user, require_admin, revoke_user_sessions
from ..core.app_settings import get_app_settings
from ..core.audit import audit
from ..core.database import session_scope
from ..core.db import count_tasks_by_user, request_cancel, request_cancel_syllabus_task
from ..core.security import hash_password, validate_password
from ..models import (
    AuditLog,
    AuthIdentity,
    AuthSession,
    EvalTask,
    StoredFile,
    SyllabusTask,
    User,
    UserProfile,
)
from ..schemas import AdminPasswordForm, AdminRoleForm

router = APIRouter(prefix="/api/admin", tags=["管理员"])


def _uid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(404, "用户不存在") from exc


@router.get("/overview")
async def overview(admin: dict = Depends(require_admin)) -> dict:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    day_ago = now - timedelta(hours=24)
    async with session_scope() as session:
        user_total = await session.scalar(select(func.count()).select_from(User))
        new_users = await session.scalar(
            select(func.count()).select_from(User).where(User.created_at >= week_ago)
        )
        recent_login = await session.scalar(
            select(func.count()).select_from(User).where(User.last_login_at >= day_ago)
        )
        active_sessions = await session.scalar(
            select(func.count()).select_from(AuthSession).where(
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                AuthSession.last_seen_at >= day_ago,
            )
        )
        eval_rows = (
            await session.execute(
                select(EvalTask.status, func.count()).group_by(EvalTask.status)
            )
        ).all()
        syllabus_rows = (
            await session.execute(
                select(SyllabusTask.status, func.count()).group_by(SyllabusTask.status)
            )
        ).all()
        storage_bytes = await session.scalar(
            select(func.coalesce(func.sum(StoredFile.size_bytes), 0)).where(
                StoredFile.deleted_at.is_(None)
            )
        )
        recent_errors = (
            await session.scalars(
                select(EvalTask)
                .where(EvalTask.status == "failed")
                .order_by(EvalTask.updated_at.desc())
                .limit(8)
            )
        ).all()
    eval_stats = {status: int(count) for status, count in eval_rows}
    syllabus_stats = {status: int(count) for status, count in syllabus_rows}
    return {
        "users": {
            "total": int(user_total or 0),
            "new_7d": int(new_users or 0),
            "recent_login_24h": int(recent_login or 0),
            "active_sessions_24h": int(active_sessions or 0),
        },
        "eval_tasks": eval_stats,
        "syllabus_tasks": syllabus_stats,
        "storage_bytes": int(storage_bytes or 0),
        "recent_errors": [
            {
                "id": str(row.id),
                "user_id": str(row.user_id),
                "filename": row.filename,
                "status": row.status,
                "error": (row.error or "")[:200],
                "updated_at": row.updated_at.timestamp() if row.updated_at else None,
            }
            for row in recent_errors
        ],
    }


@router.get("/users")
async def list_users(
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: dict = Depends(require_admin),
) -> dict:
    async with session_scope() as session:
        stmt = select(User)
        if q:
            pattern = f"%{q.strip()}%"
            stmt = (
                stmt.outerjoin(UserProfile, UserProfile.user_id == User.id)
                .outerjoin(AuthIdentity, AuthIdentity.user_id == User.id)
                .where(
                    or_(
                        User.display_name.ilike(pattern),
                        UserProfile.name.ilike(pattern),
                        UserProfile.staff_id.ilike(pattern),
                        UserProfile.school.ilike(pattern),
                        AuthIdentity.username.ilike(pattern),
                        AuthIdentity.school.ilike(pattern),
                        AuthIdentity.subject.ilike(pattern),
                    )
                )
                .distinct()
            )
        total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            await session.scalars(
                stmt.order_by(User.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        items = []
        for user in rows:
            payload = await public_user(session, user)
            counts = await count_tasks_by_user(session, user.id)
            items.append({**payload, "task_counts": counts})
    return {"total": int(total or 0), "page": page, "page_size": page_size, "items": items}


@router.get("/users/{user_id}")
async def get_user(user_id: str, admin: dict = Depends(require_admin)) -> dict:
    async with session_scope() as session:
        user = await session.get(User, _uid(user_id))
        if not user:
            raise HTTPException(404, "用户不存在")
        payload = await public_user(session, user)
        identities = (
            await session.scalars(
                select(AuthIdentity).where(AuthIdentity.user_id == user.id)
            )
        ).all()
        counts = await count_tasks_by_user(session, user.id)
    return {
        **payload,
        "identities": [
            {
                "provider": item.provider,
                "subject": item.subject,
                "username": item.username,
                "created_at": item.created_at.timestamp() if item.created_at else None,
                "last_authenticated_at": (
                    item.last_authenticated_at.timestamp()
                    if item.last_authenticated_at
                    else None
                ),
            }
            for item in identities
        ],
        "task_counts": counts,
    }


@router.post("/users/{user_id}/disable")
async def disable_user(
    user_id: str, request: Request, admin: dict = Depends(require_admin)
) -> dict:
    async with session_scope() as session:
        user = await session.get(User, _uid(user_id))
        if not user:
            raise HTTPException(404, "用户不存在")
        if str(user.id) == admin["id"]:
            raise HTTPException(400, "不能停用当前登录的管理员")
        user.status = "disabled"
        user.updated_at = datetime.now(timezone.utc)
        revoked = await revoke_user_sessions(session, user.id)
        await audit(
            session,
            request,
            action="user_disable",
            actor_user_id=admin["_id"],
            target_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            details={"revoked_sessions": revoked},
        )
        return await public_user(session, user)


@router.post("/users/{user_id}/enable")
async def enable_user(
    user_id: str, request: Request, admin: dict = Depends(require_admin)
) -> dict:
    async with session_scope() as session:
        user = await session.get(User, _uid(user_id))
        if not user:
            raise HTTPException(404, "用户不存在")
        user.status = "active"
        user.updated_at = datetime.now(timezone.utc)
        await audit(
            session,
            request,
            action="user_enable",
            actor_user_id=admin["_id"],
            target_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
        )
        return await public_user(session, user)


@router.post("/users/{user_id}/role")
async def set_role(
    user_id: str,
    form: AdminRoleForm,
    request: Request,
    admin: dict = Depends(require_admin),
) -> dict:
    async with session_scope() as session:
        user = await session.get(User, _uid(user_id))
        if not user:
            raise HTTPException(404, "用户不存在")
        if str(user.id) == admin["id"] and form.role != "admin":
            raise HTTPException(400, "不能取消自己的管理员身份")
        old = user.role
        user.role = form.role
        user.updated_at = datetime.now(timezone.utc)
        if form.role != "admin":
            await revoke_user_sessions(session, user.id)
        await audit(
            session,
            request,
            action="role_change",
            actor_user_id=admin["_id"],
            target_user_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            details={"from": old, "to": form.role},
        )
        return await public_user(session, user)


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    form: AdminPasswordForm,
    request: Request,
    admin: dict = Depends(require_admin),
) -> dict:
    settings = get_app_settings()
    if not settings.is_local_auth:
        raise HTTPException(403, "统一身份认证模式下不能重置本地密码")
    try:
        password = validate_password(form.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    async with session_scope() as session:
        identity = await session.scalar(
            select(AuthIdentity).where(
                AuthIdentity.user_id == _uid(user_id),
                AuthIdentity.provider == "local",
            )
        )
        if not identity:
            raise HTTPException(404, "该用户没有本地登录身份")
        identity.password_hash = hash_password(password)
        await revoke_user_sessions(session, identity.user_id)
        await audit(
            session,
            request,
            action="password_reset",
            actor_user_id=admin["_id"],
            target_user_id=identity.user_id,
            resource_type="user",
            resource_id=user_id,
        )
    return {"ok": True}


def _task_brief(row, kind: str) -> dict:
    return {
        "id": str(row.id),
        "kind": kind,
        "user_id": str(row.user_id),
        "filename": row.filename,
        "status": row.status,
        "current_step": row.current_step,
        "error": (row.error or "")[:200],
        "created_at": row.created_at.timestamp() if row.created_at else None,
        "updated_at": row.updated_at.timestamp() if row.updated_at else None,
    }


@router.get("/tasks")
async def list_tasks(
    kind: str = Query("eval", pattern="^(eval|syllabus)$"),
    status: str | None = None,
    user_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: dict = Depends(require_admin),
) -> dict:
    model = EvalTask if kind == "eval" else SyllabusTask
    async with session_scope() as session:
        stmt = select(model)
        if status:
            stmt = stmt.where(model.status == status)
        if user_id:
            stmt = stmt.where(model.user_id == _uid(user_id))
        total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            await session.scalars(
                stmt.order_by(model.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    return {
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "items": [_task_brief(row, kind) for row in rows],
    }


@router.post("/tasks/{kind}/{task_id}/cancel")
async def cancel_task(
    kind: str,
    task_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
) -> dict:
    if kind not in {"eval", "syllabus"}:
        raise HTTPException(404, "任务不存在")
    if kind == "eval":
        result = await request_cancel(task_id)
    else:
        result = await request_cancel_syllabus_task(task_id)
    if result.get("reason") == "not_found":
        raise HTTPException(404, "任务不存在")
    if not result["ok"]:
        raise HTTPException(409, f"任务当前状态为 {result['reason']}，无法停止")
    async with session_scope() as session:
        await audit(
            session,
            request,
            action="admin_cancel_task",
            actor_user_id=admin["_id"],
            resource_type=f"{kind}_task",
            resource_id=task_id,
        )
    return {"ok": True, "status": result.get("status", "cancelled")}


@router.delete("/tasks/{kind}/{task_id}")
async def cleanup_task(
    kind: str,
    task_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
) -> dict:
    from ..core import db

    if kind == "eval":
        result = await db.delete_task(task_id)
        if result.get("reason") == "not_found":
            raise HTTPException(404, "任务不存在")
        if not result["ok"]:
            raise HTTPException(409, "任务尚未结束，请先停止任务并等待其完全退出")
        ok = True
    elif kind == "syllabus":
        ok = await db.delete_syllabus_task(task_id)
    else:
        raise HTTPException(404, "任务不存在")
    if not ok:
        raise HTTPException(404, "任务不存在")
    async with session_scope() as session:
        await audit(
            session,
            request,
            action="admin_cleanup_task",
            actor_user_id=admin["_id"],
            resource_type=f"{kind}_task",
            resource_id=task_id,
        )
    return {"ok": True}


@router.get("/audit")
async def list_audit(
    action: str | None = None,
    resource_type: str | None = None,
    actor_user_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    admin: dict = Depends(require_admin),
) -> dict:
    async with session_scope() as session:
        stmt = select(AuditLog)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if resource_type:
            stmt = stmt.where(AuditLog.resource_type == resource_type)
        if actor_user_id:
            stmt = stmt.where(AuditLog.actor_user_id == _uid(actor_user_id))
        total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            await session.scalars(
                stmt.order_by(AuditLog.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    return {
        "total": int(total or 0),
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": str(row.id),
                "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "target_user_id": str(row.target_user_id) if row.target_user_id else None,
                "ip_address": str(row.ip_address) if row.ip_address else None,
                "details": row.details,
                "created_at": row.created_at.timestamp() if row.created_at else None,
            }
            for row in rows
        ],
    }
