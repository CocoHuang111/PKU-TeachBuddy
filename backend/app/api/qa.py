from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ai_engine.config import settings
from ai_engine.qa import ask, ask_stream, public_modes
from ai_engine.rag import collection_stats

from ..core import db
from ..core.audit import audit
from ..core.auth import current_user
from ..core.database import session_scope
from ..core.execution import run_qa
from ..core.qa_attachments import (
    MAX_FILE_BYTES,
    MAX_FILES_PER_UPLOAD,
    MAX_REQUEST_IMAGE_BYTES,
    delete_attachment,
    image_data_url,
    load_attachment,
    original_path,
    save_attachment,
)
from ..schemas import QAForm, SessionPatch

router = APIRouter(prefix="/api/qa", tags=["教学智能问答"])

# 生成任务跟请求脱钩：客户端断开 SSE 后，线程里的 LLM 仍跑完并落库
_background_jobs: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_jobs.add(task)
    task.add_done_callback(_background_jobs.discard)
    return task


def _user_turn(
    question: str, mode: str, attachments: list[dict] | None = None
) -> dict:
    turn = {"role": "user", "content": question, "mode": mode}
    if attachments:
        turn["attachments"] = attachments
    return turn


def _pending_history(
    history: list[dict],
    question: str,
    mode: str,
    attachments: list[dict] | None = None,
) -> list[dict]:
    return list(history) + [
        _user_turn(question, mode, attachments),
        {
            "role": "assistant",
            "content": "",
            "mode": mode,
            "pending": True,
            "citations": [],
            "plan": None,
        },
    ]


def _complete_history(
    history: list[dict],
    question: str,
    *,
    answer: str,
    citations: list | None = None,
    plan: dict | None = None,
    mode: str = "ask",
    attachments: list[dict] | None = None,
) -> list[dict]:
    assistant: dict = {
        "role": "assistant",
        "content": answer,
        "mode": mode,
        "citations": citations or [],
    }
    if plan is not None:
        assistant["plan"] = plan
    return list(history) + [
        _user_turn(question, mode, attachments),
        assistant,
    ]


@router.get("/modes")
async def list_modes(user: dict = Depends(current_user)) -> list[dict]:
    """返回前端可选工作模式；提示词内部指令不对外暴露。"""
    valid_corpora = set(settings.corpus_names(include_auto=False))
    result = public_modes()
    for mode in result:
        mode["default_corpora"] = [
            name for name in mode["default_corpora"] if name in valid_corpora
        ]
    return result


@router.get("/corpora")
async def list_corpora(user: dict = Depends(current_user)) -> list[dict]:
    """语料库列表 + 各库当前文本块数量，前端用来渲染勾选框。

    eval_reports 的 count 改成当前用户已完成评估份数，而不是 Chroma 全库块数。
    """
    stats = await asyncio.to_thread(collection_stats)
    reports = await db.list_tasks(
        user_id=user["id"], status="completed", limit=200
    )
    return [
        {
            "name": c["name"],
            "label": c.get("label", c["name"]),
            "description": c.get("description", ""),
            "auto": c.get("auto", False),
            "count": (
                len(reports) if c["name"] == "eval_reports" else stats.get(c["name"], 0)
            ),
        }
        for c in settings.corpora
    ]


async def _owned_eval_task_ids(
    user_id: str, requested: list[str] | None
) -> list[str] | None:
    if requested is None:
        return None
    tasks = await db.list_tasks(user_id=user_id, status="completed", limit=200)
    allowed = {t["id"] for t in tasks}
    return [tid for tid in requested if tid in allowed]


def _format_eval_context(task: dict) -> dict | None:
    result = task.get("result") or {}
    report = (result.get("report") or "").strip()
    overall = result.get("overall") if isinstance(result.get("overall"), dict) else {}
    if not report and overall.get("score") is None:
        return None
    dims = "、".join(
        f"{d.get('label')}{d.get('score')}分"
        for d in (result.get("dimensions") or [])
        if isinstance(d, dict) and d.get("assessed")
    )
    name = task.get("filename") or result.get("video_file") or "未命名"
    grade = overall.get("grade")
    grade_label = overall.get("grade_label")
    grade_text = f"，等级 {grade}（{grade_label}）" if grade else ""
    dim_text = f"五维得分：{dims}。\n" if dims else ""
    text = (
        f"教学视频评估报告（{name}）\n"
        f"综合得分 {overall.get('score', '—')}/100{grade_text}。\n"
        f"{dim_text}\n"
        f"{report}"
    )
    meta = settings.corpus_meta("eval_reports")
    score = overall.get("score")
    chip_name = name
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        rounded = int(float(score) + (0.5 if score >= 0 else -0.5))
        chip_name = f"{name}（{rounded}分）"
    return {
        "text": text.strip(),
        "corpus": "eval_reports",
        "corpus_label": meta.get("label", "历史评估报告"),
        "source": f"评估报告-{name}",
        "score": 1.0,
        "pinned": True,
        "context_type": "eval_report",
        "history_attachment": {
            "id": f"eval:{task.get('id') or chip_name}",
            "name": chip_name,
            "size": 0,
            "kind": "eval_report",
            "warnings": [],
        },
    }


def _eval_history_items(contexts: list[dict] | None) -> list[dict]:
    items = []
    for ctx in contexts or []:
        if not isinstance(ctx, dict):
            continue
        chip = ctx.get("history_attachment")
        if isinstance(chip, dict) and chip.get("name"):
            items.append(dict(chip))
    return items


def _public_contexts(contexts: list[dict] | None) -> list[dict]:
    cleaned = []
    for ctx in contexts or []:
        if not isinstance(ctx, dict):
            continue
        cleaned.append(
            {key: value for key, value in ctx.items() if key != "history_attachment"}
        )
    return cleaned


async def _pinned_eval_contexts(
    user_id: str, eval_task_ids: list[str] | None
) -> list[dict]:
    if not eval_task_ids:
        return []
    items = []
    for tid in eval_task_ids:
        task = await db.get_task(tid, user_id=user_id)
        if not task or task.get("status") != "completed":
            continue
        ctx = _format_eval_context(task)
        if ctx:
            items.append(ctx)
    return items


def _attachment_contexts(
    user_id: str, attachment_ids: list[str] | None
) -> tuple[list[dict], list[dict]]:
    contexts: list[dict] = []
    history_items: list[dict] = []
    missing: list[str] = []
    image_bytes = 0
    for attachment_id in dict.fromkeys(attachment_ids or []):
        loaded = load_attachment(user_id, attachment_id)
        if not loaded:
            missing.append(attachment_id)
            continue
        metadata, text = loaded
        warnings = metadata.get("warnings") or []
        warning_text = (
            "\n解析说明：" + " ".join(str(item) for item in warnings) if warnings else ""
        )
        context = {
            "corpus": "user_files",
            "corpus_label": "本次上传材料",
            "source": metadata["name"],
            "score": 1.0,
            "pinned": True,
            "context_type": "attachment",
            "warnings": warnings,
        }
        if metadata.get("kind") == "image":
            path = original_path(user_id, attachment_id)
            if path is None:
                missing.append(attachment_id)
                continue
            image_bytes += int(metadata.get("size") or 0)
            if image_bytes > MAX_REQUEST_IMAGE_BYTES:
                raise HTTPException(
                    400, "本次图片合计超过 30 MB，请减少图片后再提问"
                )
            mime = metadata.get("content_type") or "image/jpeg"
            context["text"] = (
                f"文件名：{metadata['name']}{warning_text}\n"
                "这是一张图片，原图附在本条消息末尾。"
            )
            context["media_type"] = "image"
            context["mime"] = mime
            context["image_data_url"] = image_data_url(path, mime)
        else:
            context["text"] = f"文件名：{metadata['name']}{warning_text}\n\n{text}"
        contexts.append(context)
        history_items.append(
            {
                "id": metadata["id"],
                "name": metadata["name"],
                "size": metadata["size"],
                "char_count": metadata["char_count"],
                "kind": metadata.get("kind") or "text",
                "warnings": warnings,
            }
        )
    if missing:
        raise HTTPException(400, "部分附件已不存在，请移除后重新上传")
    if image_bytes and settings.mode != "cloud":
        raise HTTPException(
            400, "当前是本地文本模型，不能理解图片。请使用云端 deepseek-flash。"
        )
    return contexts, history_items


@router.post("/attachments")
async def upload_attachments(
    files: list[UploadFile] = File(...), user: dict = Depends(current_user)
) -> dict:
    """上传并提取问答材料。提取结果私有保存，不进入向量库。"""
    if not files or len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(400, f"一次最多上传 {MAX_FILES_PER_UPLOAD} 个文件")
    attachments: list[dict] = []
    errors: list[dict] = []
    for file in files:
        name = file.filename or "未命名"
        content = await file.read(MAX_FILE_BYTES + 1)
        try:
            item = await asyncio.to_thread(
                save_attachment,
                user_id=user["id"],
                original_name=name,
                content=content,
                content_type=file.content_type or "",
            )
            attachments.append(item)
        except Exception as exc:
            errors.append({"name": name, "message": str(exc)})
        finally:
            await file.close()
    if not attachments and errors:
        raise HTTPException(422, errors)
    return {"attachments": attachments, "errors": errors}


@router.delete("/attachments/{attachment_id}")
async def remove_attachment(
    attachment_id: str, user: dict = Depends(current_user)
) -> dict:
    if not await asyncio.to_thread(delete_attachment, user["id"], attachment_id):
        raise HTTPException(404, "附件不存在")
    return {"ok": True}


def _strip_pending_turn(history: list[dict] | None) -> list[dict]:
    items = list(history or [])
    if items and items[-1].get("role") == "assistant" and items[-1].get("pending"):
        items.pop()
        if items and items[-1].get("role") == "user":
            items.pop()
    return items


async def _load_history(session_id: str | None, user_id: str) -> list[dict]:
    if not session_id:
        return []
    session = await db.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(404, "会话不存在")
    return _strip_pending_turn(session.get("history") or [])


@router.post("/ask")
async def ask_once(form: QAForm, user: dict = Depends(current_user)) -> dict:
    history = await _load_history(form.session_id, user["id"])
    eval_task_ids = await _owned_eval_task_ids(user["id"], form.eval_task_ids)
    eval_contexts = await _pinned_eval_contexts(user["id"], eval_task_ids)
    eval_history = _eval_history_items(eval_contexts)
    attachment_contexts, attachment_history = await asyncio.to_thread(
        _attachment_contexts, user["id"], form.attachment_ids
    )
    pinned = _public_contexts(eval_contexts) + attachment_contexts
    result = await run_qa(
        ask,
        form.question,
        history,
        form.corpora,
        user["id"],
        eval_task_ids,
        pinned,
        form.mode,
    )

    history = _complete_history(
        history,
        form.question,
        answer=result["answer"],
        citations=result["citations"],
        plan=result.get("plan"),
        mode=form.mode,
        attachments=attachment_history + eval_history,
    )
    session_id = await db.save_session(
        form.session_id, history, user_id=user["id"]
    )
    return {**result, "session_id": session_id}


@router.post("/ask/stream")
async def ask_streaming(
    form: QAForm, user: dict = Depends(current_user)
) -> StreamingResponse:
    history = await _load_history(form.session_id, user["id"])
    eval_task_ids = await _owned_eval_task_ids(user["id"], form.eval_task_ids)
    eval_contexts = await _pinned_eval_contexts(user["id"], eval_task_ids)
    eval_history = _eval_history_items(eval_contexts)
    attachment_contexts, attachment_history = await asyncio.to_thread(
        _attachment_contexts, user["id"], form.attachment_ids
    )
    pinned = _public_contexts(eval_contexts) + attachment_contexts
    shown_attachments = attachment_history + eval_history
    pending = _pending_history(
        history, form.question, form.mode, shown_attachments
    )
    session_id = await db.save_session(
        form.session_id, pending, user_id=user["id"]
    )

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    result: dict = {"final": None, "error": None}

    def produce() -> None:
        try:
            for event in ask_stream(
                form.question,
                history,
                form.corpora,
                user["id"],
                eval_task_ids,
                pinned,
                form.mode,
            ):
                if event["type"] == "done":
                    result["final"] = event
                elif event["type"] == "error":
                    result["error"] = event.get("data") or "生成失败"
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as e:
            result["error"] = str(e)
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "error", "data": str(e)}
            )

    async def persist_job() -> None:
        try:
            await run_qa(produce)
            final = result["final"]
            if final:
                new_history = _complete_history(
                    history,
                    form.question,
                    answer=final.get("answer") or "",
                    citations=final.get("citations"),
                    plan=final.get("plan"),
                    mode=form.mode,
                    attachments=shown_attachments,
                )
            else:
                err = result["error"] or "生成失败"
                new_history = _complete_history(
                    history,
                    form.question,
                    answer=f"（请求失败：{err}）",
                    mode=form.mode,
                    attachments=shown_attachments,
                )
            await db.save_session(session_id, new_history, user_id=user["id"])
        finally:
            await queue.put(None)

    _spawn(persist_job())

    async def event_stream() -> AsyncIterator[str]:
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id}, ensure_ascii=False)}\n\n"
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions")
async def list_sessions(user: dict = Depends(current_user)) -> list[dict]:
    return await db.list_sessions(user_id=user["id"])


@router.get("/session/{session_id}")
async def get_session(
    session_id: str, user: dict = Depends(current_user)
) -> dict:
    session = await db.get_session(session_id, user_id=user["id"])
    if not session:
        raise HTTPException(404, "会话不存在")
    return session


@router.patch("/session/{session_id}")
async def patch_session(
    session_id: str, form: SessionPatch, user: dict = Depends(current_user)
) -> dict:
    if form.title is None and form.pinned is None:
        raise HTTPException(400, "没有要修改的字段")
    title = form.title.strip() if form.title is not None else None
    if title is not None and not title:
        raise HTTPException(400, "名称不能为空")
    session = await db.update_session(
        session_id, title=title, pinned=form.pinned, user_id=user["id"]
    )
    if not session:
        raise HTTPException(404, "会话不存在")
    session.pop("history", None)
    return session


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str, user: dict = Depends(current_user)
) -> dict:
    if not await db.delete_session(session_id, user_id=user["id"]):
        raise HTTPException(404, "会话不存在")
    async with session_scope() as session:
        await audit(
            session,
            None,
            action="delete",
            actor_user_id=user["_id"],
            resource_type="qa_session",
            resource_id=session_id,
        )
    return {"ok": True}
