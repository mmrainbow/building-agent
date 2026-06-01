"""Gradio 智能问答适配 — session 状态管理 + 上下文拼接。"""

import os
from typing import Any

from db import SessionLocal
from db.chat_crud import create_conversation
from llm.agent_factory import get_chat_agent

from .constants import TEXT

# ── Gradio 适配层 ──────────────────────────────────────────


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

        result = get_chat_agent().run(
            user_id=user_state["user_id"],
            conversation_id=conv_id,
            message=full_message,
            db=db,
            image=img,
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
