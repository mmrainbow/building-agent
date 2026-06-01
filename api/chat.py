"""Chat API — ReAct Agent 智能 Tool 调用入口。

端点:
    POST /chat/send              发送消息（文本 + 可选图片），AI 自主选择 Tool
    GET  /chat/conversations      我的对话列表
    GET  /chat/conversations/{id} 对话详情（含所有消息）
    DELETE /chat/conversations/{id} 删除对话
"""

import io
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from api.auth import get_current_user
from api.schemas import TokenResponse  # noqa: keep for re-export
from db import (
    SessionLocal,
    add_message,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_conversation_messages,
    get_user_conversations,
    update_conversation_title,
)
from db import get_db as _get_db
from pydantic import BaseModel, Field

router = APIRouter(prefix="/chat", tags=["chat"])

# ── Agent 懒加载（避免 import 时依赖 torch）─────────────────

_agent: Any = None
_tools: dict | None = None


def _get_agent():
    global _agent, _tools
    if _agent is None:
        from llm.client import LLMClient
        from llm.tools import build_tools
        from agent.orchestrator import InspectionAgent

        _agent = InspectionAgent(LLMClient())
        _tools = build_tools()
        _agent.tools = _tools
    return _agent


# ── Response Schemas ───────────────────────────────────────


class ToolCallLog(BaseModel):
    name: str
    arguments: dict
    result: str
    elapsed_ms: int


class ChatResponse(BaseModel):
    conversation_id: int
    response: str
    tool_log: list[ToolCallLog] = []
    rounds: int = 0


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


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: int | None = Field(None, description="续接已有对话时传入")


# ── 端点 ───────────────────────────────────────────────────


@router.post("/send", response_model=ChatResponse)
async def chat_send(
    message: str = Query(..., description="用户输入文本"),
    conversation_id: int | None = Query(None, description="续接已有对话"),
    image: UploadFile | None = File(None),
    user: dict = Depends(get_current_user),
):
    """发送消息，AI 自主选择 Tool 执行分析。首次对话不传 conversation_id。"""
    db = SessionLocal()
    try:
        # 1. 对话管理
        if conversation_id is not None:
            conv = get_conversation(db, conversation_id)
            if conv is None:
                raise HTTPException(status_code=404, detail="对话不存在")
            if conv.user_id != user["user_id"]:
                raise HTTPException(status_code=403, detail="无权访问此对话")
        else:
            title = message[:40] + ("..." if len(message) > 40 else "")
            conv = create_conversation(db, user["user_id"], title=title)
            conversation_id = conv.id

        # 2. 图片处理
        np_image = None
        if image is not None:
            content = await image.read()
            if not content:
                raise HTTPException(status_code=400, detail="上传的图片为空")
            nparr = np.frombuffer(content, np.uint8)
            np_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if np_image is None:
                raise HTTPException(status_code=400, detail="无法解码图片")

        # 3. Agent 执行
        agent = _get_agent()
        result = agent.run(
            user_id=user["user_id"],
            conversation_id=conversation_id,
            message=message,
            db=db,
            image=np_image,
        )

        # 4. 自动设置对话标题（首次对话用 LLM 回复的前 40 字）
        if conv.message_count <= 2 and conv.title and len(conv.title) <= 41:
            title = (result["response"] or "新对话")[:40]
            update_conversation_title(db, conversation_id, title)

        return ChatResponse(
            conversation_id=conversation_id,
            response=result["response"],
            tool_log=[ToolCallLog(**t) for t in result["tool_log"]],
            rounds=result["rounds"],
        )
    finally:
        db.close()


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
