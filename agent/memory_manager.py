"""长期记忆管理 — 为 ReAct Agent 组装上下文并自动提取落库。"""

import json
import re
from typing import Any

from db.chat_crud import get_recent_messages
from db.memory_crud import save_memory, search_memories_by_keyword

MEMORY_EXTRACTION_SYSTEM_PROMPT = """你是记忆提取分析员，专门从建筑巡检对话中提炼可长期复用的信息。

## 提取范围（仅限以下两类）
1. **长期偏好**：用户对报告风格、语气、格式、工作流程的稳定要求（非一次性指令）。
2. **客观事实**：关于用户身份、建筑物业、历史施工/翻新等可重复引用的客观信息。

## 禁止提取
- 单次巡检的临时结论、工具输出原文、寒暄、无关闲聊。
- 模型推测、未在对话中明确的信息。

## 输出格式（必须严格遵守）
- 若**没有**值得长期保存的内容，只输出一行：`NONE`（不要输出其它文字）。
- 若有，只输出一个 JSON 对象（不要 Markdown 代码块），字段如下：
  - `memory_type`：只能是 `user_fact`、`building_info`、`preference`、`summary` 之一。
  - `key`：简短英文或拼音键，用于去重（如 `report_style`、`building_waterproof_2025`）。
  - `content`：中文记忆正文，一句话说清楚。

示例：
{"memory_type": "preference", "key": "report_tone", "content": "用户要求巡检报告语气严厉且尽量简短。"}
"""


class MemoryManager:
    """对话上下文构建 + LLM 驱动记忆提取。"""

    def build_context(
        self,
        db: Any,
        user_id: int,
        conversation_id: int,
        current_query: str,
    ) -> dict:
        """拉取近期消息与关键词相关的长期记忆。"""
        # get_recent_messages 在 chat_crud 内已用 [::-1] 转为时间正序
        recent_messages = get_recent_messages(db, conversation_id, limit=20)

        memories: list = []
        query = (current_query or "").strip()
        if query:
            memories = search_memories_by_keyword(
                db, user_id=user_id, keyword=query, conversation_id=conversation_id, limit=10
            )

        return {
            "recent_messages": recent_messages,
            "memories": memories,
        }

    def extract_and_save_memory(
        self,
        db: Any,
        user_id: int,
        conversation_id: int,
        llm_client: Any,
        recent_messages: list,
    ) -> None:
        """从近期对话中提取一条长期记忆并落库（隔离在对话范围内）。"""
        if len(recent_messages) < 2:
            return

        dialogue_lines: list[str] = []
        for msg in recent_messages:
            role = getattr(msg, "role", None)
            if role == "tool":
                continue
            content = (getattr(msg, "content", None) or "").strip()
            if content:
                dialogue_lines.append(f"{role}: {content}")

        if not dialogue_lines:
            return

        dialogue_text = "\n".join(dialogue_lines)
        messages = [
            {"role": "system", "content": MEMORY_EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "请从以下对话中提取至多一条最值得长期保存的记忆；"
                    "若无则输出 NONE。\n\n"
                    f"{dialogue_text}"
                ),
            },
        ]

        try:
            resp = llm_client.chat(messages=messages, tools=None)
            raw = (resp.get("content") or "").strip()
            payload = _parse_memory_payload(raw)
            if payload is None:
                return

            save_memory(
                db,
                user_id=user_id,
                content=payload["content"],
                memory_type=payload["memory_type"],
                key=payload.get("key"),
                conversation_id=conversation_id,
                importance=0.6,
            )
        except Exception:
            return


def _parse_memory_payload(text: str) -> dict | None:
    """解析 LLM 返回的 NONE 或 JSON 记忆对象。"""
    cleaned = text.strip()
    if not cleaned:
        return None

    upper = cleaned.upper()
    if upper == "NONE" or (upper.startswith("NONE") and "{" not in cleaned):
        return None

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    data: dict | None = None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return None

    if not isinstance(data, dict):
        return None

    memory_type = data.get("memory_type")
    content = data.get("content")
    key = data.get("key")

    if not memory_type or not content:
        return None

    memory_type = str(memory_type).strip()
    content = str(content).strip()
    key = str(key).strip() if key else None

    valid_types = {"user_fact", "building_info", "preference", "summary"}
    if memory_type not in valid_types:
        return None

    return {
        "memory_type": memory_type,
        "key": key,
        "content": content,
    }
