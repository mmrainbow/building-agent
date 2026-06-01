"""Gradio 智能问答 — 接入 InspectionAgent 与双层记忆。"""

import os
from typing import Any

from agent.orchestrator import InspectionAgent
from db import SessionLocal
from db.chat_crud import create_conversation
from llm.client import LLMClient
from llm.tools import build_tools

from .constants import TEXT

_agent: InspectionAgent | None = None


def _get_agent() -> InspectionAgent:
    global _agent
    if _agent is None:
        llm = LLMClient()
        agent = InspectionAgent(llm)
        agent.tools = build_tools()
        _agent = agent
    return _agent


def _ensure_conversation(db: Any, user_state: dict) -> int:
    conv_id = user_state.get("conversation_id")
    if conv_id:
        return conv_id
    conv = create_conversation(
        db,
        user_id=user_state["user_id"],
        title="智能问答",
    )
    user_state["conversation_id"] = conv.id
    return conv.id


def _compose_message(message: str, user_state: dict) -> str:
    text = (message or "").strip()
    report = user_state.get("last_report")
    if report:
        return (
            f"【最近一次巡检报告（供回答参考）】\n{report}\n\n"
            f"【用户问题】\n{text}"
        )
    return text


def chat_with_llm(message, history, user_state):
    """智能问答：自动 build_context、ReAct、短期落库、长期提炼。"""
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
        image = user_state.get("last_image")

        result = _get_agent().run(
            user_id=user_state["user_id"],
            conversation_id=conv_id,
            message=full_message,
            db=db,
            image=image,
        )
        return (result.get("response") or "").strip() or TEXT["no_report"]
    except Exception as e:
        return f"问答失败：{type(e).__name__}: {e}"
    finally:
        db.close()


def reset_chat_session(user_state):
    """清空界面聊天时开启新会话，短期记忆从新 conversation 开始。"""
    if user_state:
        user_state["conversation_id"] = None
    return user_state
