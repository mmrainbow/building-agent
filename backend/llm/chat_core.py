"""对话核心逻辑 — 供 api/chat.py 直接导入，不经过 services/__init__.py。"""

import cv2
import numpy as np

from db import SessionLocal
from db.chat_crud import create_conversation, get_conversation
from llm.agent_factory import get_chat_agent


def decode_image(content: bytes) -> np.ndarray | None:
    """原始字节 → numpy 图像数组。解码失败返回 None。"""
    nparr = np.frombuffer(content, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img if img is not None else None


def decode_images(contents: list[bytes]) -> list[np.ndarray]:
    """批量解码 — 返回成功解码的图像列表（跳过失败项）。"""
    return [img for c in contents if (img := decode_image(c)) is not None]


def run_chat(
    user_id: int,
    message: str,
    conversation_id: int | None = None,
    images: list[np.ndarray] | None = None,
    image_blobs: list[bytes] | None = None,
) -> dict:
    """创建/续接对话 → 调用 Agent → 返回结果。

    Returns:
        {"response": str, "tool_log": list, "conversation_id": int}
    """
    db = SessionLocal()
    try:
        if conversation_id is not None:
            conv = get_conversation(db, conversation_id)
            if conv is None:
                raise ValueError(f"对话不存在: {conversation_id}")
        else:
            title = message[:40] + ("..." if len(message) > 40 else "")
            conv = create_conversation(db, user_id, title=title)
            conversation_id = conv.id

        result = get_chat_agent().run(
            user_id=user_id,
            conversation_id=conversation_id,
            message=message,
            db=db,
            images=images,
            image_blobs=image_blobs,
        )
        return {
            "response": (result.get("response") or "").strip() or "未生成报告。",
            "tool_log": result.get("tool_log", []),
            "conversation_id": conversation_id,
        }
    finally:
        db.close()
