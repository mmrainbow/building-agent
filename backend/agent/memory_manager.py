"""长期记忆管理 — 三层记忆模型中的 Consolidation + Retrieval。

Short-term (滑动窗口) → orchestrator._extract_memory
Long-term  (向量检索) → build_context + ChromaDB (Step 3)
Reflection (高阶洞察) → memory_reflection.py (Step 4)
"""

import json
import re
from typing import Any

from db.chat_crud import get_recent_messages
from db.memory_crud import record_memory_access, save_memory, search_memories_by_keyword

# ── Prompts ───────────────────────────────────────────────

_SHOULD_EXTRACT_PROMPT = """仅判断以下对话是否包含值得长期保存的信息（用户偏好、建筑事实、重要结论）。
只回答 YES 或 NO。"""

_MEMORY_EXTRACTION_PROMPT = """你是记忆提取分析员，从建筑巡检对话中提炼长期记忆。

## 提取范围
1. **preference**: 用户对报告风格、语气、格式、流程的稳定要求
2. **building_info**: 建筑的事实信息（年代、结构、材质类型、历史问题、地理位置等）
3. **user_fact**: 用户身份、角色、关注点
4. **summary**: 本段对话的关键结论摘要

## 禁止提取
- 单次巡检临时结论、工具输出原文、寒暄闲聊
- 模型推测、对话中未明确的信息

## 输出格式
若无值得保存的内容，输出: NONE
若有，输出 JSON 数组（不超过 3 条），每条包含:
- memory_type: preference / building_info / user_fact / summary
- key: 简短英文键，用于去重，如 report_style、building_age
- content: 中文记忆正文，一句话说清楚
- importance: 1-10 整数，9-10=极关键(用户明确要求/重大安全隐患), 5-8=重要(建筑核心信息), 1-4=参考

示例:
[{"memory_type":"preference","key":"report_tone","content":"用户要求巡检报告语气严厉且尽量简短","importance":8},
 {"memory_type":"building_info","key":"building_material","content":"该建筑为Face Brick材质外墙","importance":7}]"""


# ── MemoryManager ─────────────────────────────────────────

class MemoryManager:

    def build_context(
        self,
        db: Any,
        user_id: int,
        conversation_id: int,
        current_query: str,
    ) -> dict:
        """拉取近期消息 + 混合排序的长期记忆 (Top 5)。"""
        recent_messages = get_recent_messages(db, conversation_id, limit=20)

        # 语义检索 → 混合排序
        memories = _retrieve_memories_ranked(db, user_id, conversation_id, current_query)
        for m in memories:
            record_memory_access(db, m.id)

        return {"recent_messages": recent_messages, "memories": memories}


def _retrieve_memories_ranked(db, user_id, conversation_id, query, k=5) -> list:
    """多路召回 + 混合排序: 0.3×recency + 0.5×relevance + 0.2×importance。

    ChromaDB 可用 → 语义检索；不可用 → 回退 keyword LIKE。
    """
    from datetime import datetime, timezone

    try:
        from agent.rag import search_memories_semantic
        semantic = search_memories_semantic(query, user_id, conversation_id, k=10)
        if semantic:
            # 从 SQLite 加载完整记忆对象
            from db.models import ConversationMemory
            ids = [s["memory_id"] for s in semantic]
            score_map = {s["memory_id"]: s["relevance"] for s in semantic}
            memories = db.query(ConversationMemory).filter(ConversationMemory.id.in_(ids)).all()
            # 计算混合分数
            now = datetime.now(timezone.utc)
            for m in memories:
                rel = score_map.get(m.id, 0.5)
                # recency: 越新越高, 30天衰减到 0
                days = max((now - (m.created_at or now)).days, 0)
                rec = max(1.0 - days / 30.0, 0.0)
                imp = (m.importance or 0.5)
                m._score = 0.3 * rec + 0.5 * rel + 0.2 * imp
            ranked = sorted(memories, key=lambda m: getattr(m, "_score", 0), reverse=True)
            return ranked[:k]
    except Exception as e:
        print(f"[Memory] 语义检索不可用，回退 keyword: {e}")

    # 回退
    return search_memories_by_keyword(db, user_id=user_id, keyword="", conversation_id=conversation_id, limit=k)

    # ── 提取判断 ──────────────────────────────────────────

    def should_extract(
        self,
        db: Any,
        conversation_id: int,
        llm_client: Any,
    ) -> bool:
        """LLM 轻量判断：最近对话是否包含值得长期记忆的信息。"""
        recent = get_recent_messages(db, conversation_id, limit=6)
        if len(recent) < 2:
            return False

        lines = []
        for m in recent[-4:]:  # 只看最近 2 轮
            role = getattr(m, "role", "")
            if role == "tool":
                continue
            content = (getattr(m, "content", "") or "")[:300]
            if content.strip():
                lines.append(f"{role}: {content}")
        if not lines:
            return False

        try:
            resp = llm_client.chat(
                messages=[
                    {"role": "system", "content": _SHOULD_EXTRACT_PROMPT},
                    {"role": "user", "content": "\n".join(lines)},
                ],
                tools=None,
                temperature=0,
                max_tokens=5,
            )
            answer = (resp.get("content") or "").strip().upper()
            return answer.startswith("YES")
        except Exception:
            # LLM 不可用 → 回退字符数阈值
            total = sum(len(getattr(m, "content", "") or "") for m in recent)
            return total > 500

    # ── 记忆提取 ──────────────────────────────────────────

    def extract_and_save_memory(
        self,
        db: Any,
        user_id: int,
        conversation_id: int,
        llm_client: Any,
        recent_messages: list,
    ) -> int:
        """从近期对话中提取 ≤3 条长期记忆并落库。返回提取条数。"""
        if len(recent_messages) < 2:
            return 0

        dialogue_lines: list[str] = []
        for msg in recent_messages:
            role = getattr(msg, "role", None)
            if role == "tool":
                continue
            content = (getattr(msg, "content", None) or "")[:500]
            if content.strip():
                dialogue_lines.append(f"{role}: {content}")
        if not dialogue_lines:
            return 0

        dialogue_text = "\n".join(dialogue_lines)
        try:
            resp = llm_client.chat(
                messages=[
                    {"role": "system", "content": _MEMORY_EXTRACTION_PROMPT},
                    {"role": "user", "content": f"从以下对话提取长期记忆（最多3条，无则输出NONE）:\n\n{dialogue_text}"},
                ],
                tools=None,
                temperature=0,
                max_tokens=500,
            )
            raw = (resp.get("content") or "").strip()
            items = _parse_memory_array(raw)
            if not items:
                return 0

            saved = 0
            for item in items:
                _, created = save_memory(
                    db,
                    user_id=user_id,
                    content=item["content"],
                    memory_type=item["memory_type"],
                    key=item.get("key"),
                    conversation_id=conversation_id,
                    importance=float(item.get("importance", 5)),
                )
                action = "新增" if created else "更新"
                print(f"[Memory] {action}: [{item['memory_type']}] {item.get('key','')} → {item['content'][:60]}...")
                saved += 1
            return saved
        except Exception as e:
            print(f"[Memory] 提取失败: {e}")
            return 0


# ── Payload 解析 ──────────────────────────────────────────

def _parse_memory_array(text: str) -> list[dict] | None:
    """解析 LLM 返回的 NONE 或 JSON 记忆数组。"""
    cleaned = text.strip()
    if not cleaned:
        return None

    upper = cleaned.upper()
    if upper == "NONE" or (upper.startswith("NONE") and "[" not in cleaned):
        return None

    # 清理 markdown 代码块
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    # 解析 JSON
    data = None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # 尝试提取 [...] 或 {...}
        for pat in (r"\[.*\]", r"\{.*\}"):
            match = re.search(pat, cleaned, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    break
                except json.JSONDecodeError:
                    continue

    if data is None:
        return None

    # 兼容单对象 → 包装为数组
    if isinstance(data, dict):
        data = [data]

    if not isinstance(data, list):
        return None

    valid_types = {"user_fact", "building_info", "preference", "summary"}
    result = []
    for item in data[:3]:  # 最多 3 条
        if not isinstance(item, dict):
            continue
        mt = str(item.get("memory_type", "")).strip()
        ct = str(item.get("content", "")).strip()
        if mt not in valid_types or not ct:
            continue
        result.append({
            "memory_type": mt,
            "key": str(item.get("key", "")).strip() or None,
            "content": ct,
            "importance": min(max(int(item.get("importance", 5)), 1), 10),
        })
    return result if result else None
