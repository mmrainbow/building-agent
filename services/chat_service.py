"""Gradio 智能问答适配 — session 状态管理 + 上下文拼接。"""

import os
import uuid
from pathlib import Path
from typing import Any

import cv2

from db import SessionLocal
from db.chat_crud import create_conversation
from llm.agent_factory import get_chat_agent

from .constants import TEXT

CHAT_IMAGES_DIR = Path(__file__).parent.parent / "chat_images"

# ── Gradio 适配层 ──────────────────────────────────────────


def _save_image(image) -> str | None:
    """numpy 图像 → chat_images/{uuid}.jpg，返回路径或 None。"""
    CHAT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    path = CHAT_IMAGES_DIR / f"{uuid.uuid4().hex}.jpg"
    cv2.imwrite(str(path), cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    return str(path)


def _ensure_conversation(db: Any, user_state: dict) -> int:
    conv_id = user_state.get("conversation_id")
    if conv_id:
        return conv_id
    conv = create_conversation(db, user_id=user_state["user_id"], title="智能问答")
    user_state["conversation_id"] = conv.id
    return conv.id


def _compose_message(message: str, user_state: dict) -> str:
    text = (message or "").strip()
    report = user_state.get("last_report")
    if report:
        return f"【最近一次巡检报告（供回答参考）】\n{report}\n\n【用户问题】\n{text}"
    return text


def chat_with_llm(message, history, user_state, image=None):
    """Gradio 智能问答回调 — 管理 session 状态 + 拼接上下文 + 调用 Agent。"""
    if not user_state or not user_state.get("user_id"):
        return TEXT["login_required"]
    if not (message or "").strip():
        return ""
    if not os.getenv("DASHSCOPE_API_KEY"):
        return TEXT["llm_no_api_key"]

    db = SessionLocal()
    try:
        conv_id = _ensure_conversation(db, user_state)
        full_message = _compose_message(message, user_state)
        img = image if image is not None else user_state.get("last_image")

        # 保存图片到本地
        image_path = _save_image(img) if img is not None else None

        result = get_chat_agent().run(
            user_id=user_state["user_id"],
            conversation_id=conv_id,
            message=full_message,
            db=db,
            image=img,
            user_image_path=image_path,
        )
        response = (result.get("response") or "").strip() or TEXT["no_report"]

        tool_log = result.get("tool_log", [])
        if tool_log:
            used = [t["name"] for t in tool_log]
            response += f"\n\n> 🔧 已调用: {', '.join(used)}"
        return response
    except Exception as e:
        return f"问答失败：{type(e).__name__}: {e}"
    finally:
        db.close()


def reset_chat_session(user_state):
    """开启新对话 — 清除 session 中的 conversation_id。"""
    if user_state:
        user_state["conversation_id"] = None
    return user_state


def list_user_conversations(user_state) -> list:
    """获取用户的对话列表，返回 [(label, id), ...] 供 Gradio Radio 使用。"""
    if not user_state or not user_state.get("user_id"):
        return []
    from db import SessionLocal, get_user_conversations

    db = SessionLocal()
    try:
        convs = get_user_conversations(db, user_state["user_id"], limit=50)
        return [
            (
                f"{c.title or '新对话'}  ({c.updated_at.strftime('%m-%d %H:%M') if c.updated_at else ''})",
                c.id,
            )
            for c in convs
        ]
    finally:
        db.close()


def load_conversation_messages(conv_id, user_state) -> tuple:
    """加载指定对话的消息到 Gradio Chatbot 格式，含图片。

    Gradio Chatbot 图片格式: {"role": "user", "content": {"path": "..."}}
    """
    if not user_state or not user_state.get("user_id") or conv_id is None:
        return [], user_state
    from db import SessionLocal, get_conversation_messages

    db = SessionLocal()
    try:
        msgs = get_conversation_messages(db, conv_id, limit=200)
        history = []
        for m in msgs:
            if m.role not in ("user", "assistant"):
                continue
            entry = {"role": m.role}
            # 有图片的用户消息 → Gradio 图片格式
            if m.role == "user" and m.image_path and os.path.exists(m.image_path):
                entry["content"] = {"path": m.image_path}
            else:
                entry["content"] = m.content or ""
            history.append(entry)
        user_state["conversation_id"] = int(conv_id)
        return history, user_state
    finally:
        db.close()


def delete_user_conversation(conv_id, user_state) -> tuple:
    """删除对话并刷新列表。"""
    if not user_state or not user_state.get("user_id") or conv_id is None:
        return list_user_conversations(user_state), user_state
    from db import SessionLocal, delete_conversation

    db = SessionLocal()
    try:
        delete_conversation(db, int(conv_id))
        if user_state.get("conversation_id") == int(conv_id):
            user_state["conversation_id"] = None
        choices = list_user_conversations(user_state)
        # 如果有剩余对话，自动选第一个
        if choices and not user_state.get("conversation_id"):
            user_state["conversation_id"] = choices[0][1]
        return choices, user_state
    finally:
        db.close()
