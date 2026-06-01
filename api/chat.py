"""Chat API — 薄层：请求解析 + 认证 + 调用 service + 返回响应。"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
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
from llm.chat_core import decode_image, run_chat

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
    image: UploadFile | None = File(None),
    user: dict = Depends(get_current_user),
):
    # 图片解码 + 存储
    np_image = None
    image_path = None
    if image is not None:
        content = await image.read()
        if not content:
            raise HTTPException(status_code=400, detail="上传的图片为空")
        np_image = decode_image(content)
        if np_image is None:
            raise HTTPException(status_code=400, detail="无法解码图片")
        # 保存到 chat_images/
        from services.chat_service import _save_image
        image_path = _save_image(np_image)

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
        image=np_image,
        user_image_path=image_path,
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
