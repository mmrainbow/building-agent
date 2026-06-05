"""Chat API — 薄层：请求解析 + 认证 + 调用 service + 返回响应 (REST + SSE 流式)。"""

import asyncio
import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.auth import get_current_user
from db import (
    SessionLocal,
    delete_conversation,
    get_conversation,
    get_conversation_messages,
    get_user_conversations,
    update_conversation_title,
)
from llm.chat_core import decode_image, decode_images, run_chat

router = APIRouter(prefix="/chat", tags=["chat"])

# ── Schemas ─────────────────────────────────────────────────


class ToolCallLog(BaseModel):
    name: str
    arguments: dict
    result: str
    elapsed_ms: int


class ChatResponse(BaseModel):
    conversation_id: int
    response: str
    tool_log: list[ToolCallLog] = []


class ConversationItem(BaseModel):
    id: int
    title: str | None
    message_count: int
    created_at: str | None
    updated_at: str | None


class ConversationDetail(BaseModel):
    id: int
    title: str | None
    messages: list[dict]


# ── /chat/send ──────────────────────────────────────────────


@router.post("/send", response_model=ChatResponse)
async def chat_send(
    message: str = Query(..., description="用户输入文本"),
    conversation_id: int | None = Query(None),
    images: list[UploadFile] = File(default_factory=list),
    user: dict = Depends(get_current_user),
):
    # 图片解码 → JPEG 字节（入库用）
    np_images = []
    image_blobs = []
    for img in images:
        content = await img.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"图片 '{img.filename}' 为空")
        np_img = decode_image(content)
        if np_img is None:
            raise HTTPException(status_code=400, detail=f"无法解码图片 '{img.filename}'")
        np_images.append(np_img)
        image_blobs.append(content)

    # 已有对话权限校验
    if conversation_id is not None:
        db = SessionLocal()
        try:
            conv = get_conversation(db, conversation_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="对话不存在")
            if conv.user_id != user["user_id"]:
                raise HTTPException(status_code=403, detail="无权访问此对话")
        finally:
            db.close()

    # 核心逻辑委托给 service
    result = run_chat(
        user_id=user["user_id"],
        message=message,
        conversation_id=conversation_id,
        images=np_images if np_images else None,
        image_blobs=image_blobs if image_blobs else None,
    )

    # 首次对话自动设置标题
    db = SessionLocal()
    try:
        conv = get_conversation(db, result["conversation_id"])
        if conv and conv.message_count <= 2:
            title = (result["response"] or "新对话")[:40]
            update_conversation_title(db, result["conversation_id"], title)
    finally:
        db.close()

    return ChatResponse(
        conversation_id=result["conversation_id"],
        response=result["response"],
        tool_log=[ToolCallLog(**t) for t in result["tool_log"]],
    )


# ── /chat/conversations ─────────────────────────────────────


@router.get("/conversations", response_model=list[ConversationItem])
def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        convs = get_user_conversations(db, user["user_id"], limit=limit, offset=offset)
        return [
            ConversationItem(
                id=c.id,
                title=c.title,
                message_count=c.message_count or 0,
                created_at=c.created_at.isoformat() if c.created_at else None,
                updated_at=c.updated_at.isoformat() if c.updated_at else None,
            )
            for c in convs
        ]
    finally:
        db.close()


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
def conversation_detail(
    conv_id: int,
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        conv = get_conversation(db, conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        if conv.user_id != user["user_id"]:
            raise HTTPException(status_code=403, detail="无权访问此对话")
        msgs = get_conversation_messages(db, conv_id, limit=limit)
        return ConversationDetail(
            id=conv.id,
            title=conv.title,
            messages=[
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "metadata": m.metadata_,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in msgs
            ],
        )
    finally:
        db.close()


@router.get("/images/{message_id}")
def get_chat_images(
    message_id: int,
    idx: int = Query(0, ge=0, description="图片索引（0=第一张）"),
    user: dict = Depends(get_current_user),
):
    """获取对话消息中的图片。idx 参数指定第几张（从 0 开始）。"""
    from fastapi.responses import Response
    from db.models import ChatImage, ChatMessage
    db = SessionLocal()
    try:
        msg = db.query(ChatMessage).filter(ChatMessage.id == message_id).first()
        if not msg:
            raise HTTPException(status_code=404, detail="消息不存在")
        # 权限校验
        conv = get_conversation(db, msg.conversation_id)
        if not conv or conv.user_id != user["user_id"]:
            raise HTTPException(status_code=403, detail="无权访问")
        images = msg.images or []
        if idx >= len(images):
            raise HTTPException(status_code=404, detail=f"图片索引 {idx} 超出范围 (共 {len(images)} 张)")
        img = images[idx]
        return Response(content=img.data, media_type=img.mime_type or "image/jpeg")
    finally:
        db.close()


@router.delete("/conversations/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation_endpoint(
    conv_id: int,
    user: dict = Depends(get_current_user),
):
    db = SessionLocal()
    try:
        conv = get_conversation(db, conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        if conv.user_id != user["user_id"]:
            raise HTTPException(status_code=403, detail="无权访问此对话")
        delete_conversation(db, conv_id)
    finally:
        db.close()


# ── SSE 流式问答 ───────────────────────────────────────────


@router.post("/send/stream")
async def chat_send_stream(
    message: str = Query(..., description="用户输入文本"),
    conversation_id: int | None = Query(None),
    images: list[UploadFile] = File(default_factory=list),
    user: dict = Depends(get_current_user),
):
    """SSE 流式问答 — 通过 asyncio.Queue 实现真正的实时 CoT 推送。"""

    np_images = []
    image_blobs = []
    for img in images:
        content = await img.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"图片 '{img.filename}' 为空")
        np_img = decode_image(content)
        if np_img is None:
            raise HTTPException(status_code=400, detail=f"无法解码图片 '{img.filename}'")
        np_images.append(np_img)
        image_blobs.append(content)

    if conversation_id is not None:
        from db import SessionLocal, get_conversation
        db = SessionLocal()
        try:
            conv = get_conversation(db, conversation_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="对话不存在")
            if conv.user_id != user["user_id"]:
                raise HTTPException(status_code=403, detail="无权访问此对话")
        finally:
            db.close()
    else:
        # 新对话 — 预先创建 Conversation 记录
        from db import SessionLocal, create_conversation
        db = SessionLocal()
        try:
            conv = create_conversation(db, user["user_id"], title=message[:40])
            conversation_id = conv.id
        finally:
            db.close()

    event_queue: asyncio.Queue = asyncio.Queue()

    def _on_step(event: dict):
        """线程安全: put 协程不安全但 Queue.put_nowait 是线程安全的。"""
        try:
            event_queue.put_nowait(event)
        except Exception:
            pass

    async def event_stream():
        from db import SessionLocal
        from llm.agent_factory import get_chat_agent
        import concurrent.futures

        db = SessionLocal()
        try:
            # 在独立线程中运行阻塞的 Agent，on_step 实时 push 事件
            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(
                None,
                lambda: get_chat_agent().run(
                    user_id=user["user_id"],
                    conversation_id=conversation_id,
                    message=message,
                    db=db,
                    images=np_images if np_images else None,
                    image_blobs=image_blobs if image_blobs else None,
                    on_step=_on_step,
                )
            )

            # 持续读取事件直到 Agent 完成
            while not future.done():
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                    yield f"data: {json.dumps({'type': 'step', 'data': event}, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ":keepalive\n\n"

            result = future.result()
            # 消费剩余事件
            while not event_queue.empty():
                event = event_queue.get_nowait()
                yield f"data: {json.dumps({'type': 'step', 'data': event}, ensure_ascii=False)}\n\n"

            response_text = (result.get("response") or "").strip()
            yield f"data: {json.dumps({'type': 'done', 'response': response_text, 'conversation_id': conversation_id, 'tool_log': result.get('tool_log', [])}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
