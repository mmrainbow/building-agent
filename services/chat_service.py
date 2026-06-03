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

_CACHE_DIR = Path(__file__).parent.parent / "chat_images"

# ── 图片存储（BLOB 入库 + 缓存文件渲染）───────────────


def _image_to_blob(image) -> bytes:
    """numpy RGB → JPEG 字节。"""
    _, buf = cv2.imencode(".jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    return buf.tobytes()


def _blob_to_cache(message_id: int, blob: bytes) -> str:
    """BLOB → chat_images/{id}.jpg 缓存文件，返回绝对路径供 Gradio 渲染。"""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / f"{message_id}.jpg"
    if not path.exists():
        path.write_bytes(blob)
    return str(path)


def _load_image_by_index(db, conversation_id: int, index: int | None = None):
    """从对话历史中加载第 N 张图片（1-based）。index=None 时取最后一张。"""
    import numpy, cv2
    from db.models import ChatMessage
    msgs = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.role == "user",
            ChatMessage.metadata_.contains("has_image"),
        )
        .order_by(ChatMessage.created_at.asc())  # 正序: 第1张, 第2张...
        .all()
    )
    if not msgs:
        return None, None, len(msgs)
    if index is not None and 1 <= index <= len(msgs):
        msg = msgs[index - 1]
    else:
        msg = msgs[-1]  # 默认取最后一张
    if msg and msg.images:
        blob = msg.images[0].data
        nparr = numpy.frombuffer(blob, numpy.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is not None:
            return cv2.cvtColor(img, cv2.COLOR_BGR2RGB), blob, len(msgs)
    return None, None, len(msgs)


def _parse_image_ref(text: str) -> int | None:
    """解析'第N张图片'/'第2张'等引用，返回 1-based 索引；无引用返回 None。"""
    import re
    m = re.search(r'第\s*(\d+)\s*[张幅个]', text)
    return int(m.group(1)) if m else None


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


def chat_with_llm_stream(message, history, user_state, image=None):
    """Gradio 流式问答 — 实时展示 Manager Agent 的思考过程 (CoT)。"""
    if not user_state or not user_state.get("user_id"):
        yield TEXT["login_required"]
        return
    if not (message or "").strip():
        yield ""
        return
    if not (os.getenv("LLM_API_KEY") or os.getenv("EMBEDDING_API_KEY")):
        yield TEXT["llm_no_api_key"]
        return

    db = SessionLocal()
    try:
        conv_id = _ensure_conversation(db, user_state)
        full_message = _compose_message(message, user_state)
        # 当前未上传图片时，尝试从历史消息恢复图片
        img = image if image is not None else user_state.get("last_image")
        if img is None and conv_id:
            ref_idx = _parse_image_ref(message)
            img, image_blob, total = _load_image_by_index(db, conv_id, ref_idx)
            if img is not None:
                idx_label = f"第{ref_idx}张" if ref_idx else "上一张"
                full_message = f"[已从历史恢复{idx_label}图片(共{total}张)]\n\n{full_message}"
        else:
            image_blob = _image_to_blob(img) if img is not None else None

        steps = []
        def _on_step(event: dict):
            steps.append(event)

        result = get_chat_agent().run(
            user_id=user_state["user_id"],
            conversation_id=conv_id,
            message=full_message,
            db=db,
            image=img,
            image_blob=image_blob,
            on_step=_on_step,
        )

        # 生成带 CoT 可视化的最终消息
        cot_html = _build_cot_html(steps)
        response = (result.get("response") or "").strip() or TEXT["no_report"]
        tool_log = result.get("tool_log", [])
        if tool_log:
            used = [t["name"] for t in tool_log]
            response += f"\n\n> 🔧 已调用: {', '.join(used)}"
        yield f"{cot_html}\n\n{response}"
    except Exception as e:
        yield f"问答失败：{type(e).__name__}: {e}"
    finally:
        db.close()


def _build_cot_html(steps: list[dict]) -> str:
    """将 ReAct 步骤渲染为可视化 HTML。"""
    if not steps:
        return ""
    html = '<div style="background:#111;border:1px solid #333;border-radius:8px;padding:10px;margin-bottom:8px;font-size:12px;font-family:monospace">'
    html += '<div style="color:#f59e0b;font-weight:bold;margin-bottom:6px">🧠 Manager Agent 思考过程</div>'
    for s in steps:
        if s["type"] == "think":
            txt = (s.get("content") or "")[:80]
            html += f'<div style="color:#94a3b8">  💭 第{s["round"]}轮: {txt}</div>'
        elif s["type"] == "tool":
            if s["status"] == "running":
                html += f'<div style="color:#60a5fa">  🔧 调用 {s["name"]}...</div>'
            else:
                html += f'<div style="color:#22c55e">  ✅ {s["name"]} 完成 ({s["elapsed_ms"]}ms)</div>'
        elif s["type"] == "done":
            html += f'<div style="color:#a78bfa">  📝 共 {s["rounds"]} 步 → 生成最终回答</div>'
    html += '</div>'
    return html


def chat_with_llm(message, history, user_state, image=None):
    """Gradio 智能问答回调 — 管理 session 状态 + 拼接上下文 + 调用 Agent。"""
    if not user_state or not user_state.get("user_id"):
        return TEXT["login_required"]
    if not (message or "").strip():
        return ""
    if not (os.getenv("LLM_API_KEY") or os.getenv("EMBEDDING_API_KEY")):
        return TEXT["llm_no_api_key"]

    db = SessionLocal()
    try:
        conv_id = _ensure_conversation(db, user_state)
        full_message = _compose_message(message, user_state)
        img = image if image is not None else user_state.get("last_image")

        # 图片转 BLOB，传给 agent（由 _save_turn → add_message 入库）
        image_blob = _image_to_blob(img) if img is not None else None

        result = get_chat_agent().run(
            user_id=user_state["user_id"],
            conversation_id=conv_id,
            message=full_message,
            db=db,
            image=img,
            image_blob=image_blob,
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
    """加载对话历史到 Gradio Chatbot 格式。图片从 DB BLOB → 缓存文件 → 渲染。"""
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
            # 有图片的消息 → BLOB 写缓存文件 → Gradio 渲染
            if m.role == "user" and m.images:
                blob = m.images[0].data
                cache_path = _blob_to_cache(m.id, blob)
                entry["content"] = {"path": cache_path}
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
