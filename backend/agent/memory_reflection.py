"""Reflection Module — 记忆累计 ≥20 条时自动生成高阶洞察。

借鉴 Stanford Generative Agents 的反思机制:
  低阶记忆 (具体对话事件) → LLM 反思 → 高阶洞察 (Insight)
  高阶洞察以 memory_type="insight", importance≥8 存储
"""

import json
import re
import threading
from datetime import datetime, timezone
from typing import Any

_REFLECTION_PROMPT = """你是用户行为分析专家。回顾以下用户在建筑巡检对话中积累的记忆，总结 2-3 条深度洞察。

## 记忆列表
{memories}

## 输出格式
JSON 数组（不超过 3 条），每条:
- key: insight_{timestamp} 格式
- content: 中文洞察，一句话说明白
- importance: 8-10 整数

示例:
[{{"key":"insight_20260606_001","content":"用户高度关注建筑外立面防水问题，每次巡检都会详细询问渗水检测结果","importance":9}},
 {{"key":"insight_20260606_002","content":"用户偏好结构化的分项报告，不喜冗长的综合描述","importance":8}}]"""


def maybe_reflect(db, user_id: int, conversation_id: int) -> int:
    """触发条件：当前对话记忆 ≥20 条且每 +10 条触发一次。返回生成的洞察数。"""
    from db.models import ConversationMemory

    count = db.query(ConversationMemory).filter(
        ConversationMemory.conversation_id == conversation_id,
        ConversationMemory.memory_type != "insight",
    ).count()

    if count < 20 or count % 10 != 0:
        return 0

    insight_count = db.query(ConversationMemory).filter(
        ConversationMemory.conversation_id == conversation_id,
        ConversationMemory.memory_type == "insight",
    ).count()

    if insight_count >= 10:
        return 0  # 反思上限

    t = threading.Thread(
        target=_run_reflection, args=(user_id, conversation_id), daemon=True
    )
    t.start()
    return 0


def _run_reflection(user_id: int, conversation_id: int) -> None:
    """异步执行反思（独立 DB session，不干扰主流程）。"""
    from db import SessionLocal
    from db.memory_crud import save_memory
    from llm.memory_agent import get_memory_agent

    db = SessionLocal()
    try:
        from db.models import ConversationMemory

        memories = db.query(ConversationMemory).filter(
            ConversationMemory.conversation_id == conversation_id,
            ConversationMemory.memory_type != "insight",
        ).order_by(ConversationMemory.created_at.desc()).limit(50).all()

        if len(memories) < 20:
            return

        mem_text = "\n".join(
            f"- [{m.memory_type}] {m.content}" for m in memories
        )

        llm = get_memory_agent()
        resp = llm.chat(
            messages=[
                {"role": "system", "content": _REFLECTION_PROMPT.format(memories=mem_text)},
                {"role": "user", "content": "请生成洞察。"},
            ],
            tools=None,
            temperature=0.3,
            max_tokens=500,
        )

        raw = (resp.get("content") or "").strip()
        items = _parse_insights(raw)
        if not items:
            return

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        saved = 0
        for i, item in enumerate(items):
            key = item.get("key") or f"insight_{ts}_{i}"
            content = item.get("content", "")
            imp = min(max(int(item.get("importance", 9)), 8), 10)
            if not content:
                continue
            save_memory(db, user_id=user_id, content=content,
                        memory_type="insight", key=key,
                        conversation_id=conversation_id, importance=float(imp))
            saved += 1

        if saved > 0:
            print(f"[Reflection] 生成 {saved} 条洞察 (共 {len(memories)} 条记忆)")
    except Exception as e:
        print(f"[Reflection] 失败: {e}")
    finally:
        db.close()


def _parse_insights(text: str) -> list[dict] | None:
    cleaned = text.strip()
    if not cleaned or cleaned.upper() == "NONE":
        return None
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return None
        else:
            return None
    if isinstance(data, dict):
        data = [data]
    return data if isinstance(data, list) else None
