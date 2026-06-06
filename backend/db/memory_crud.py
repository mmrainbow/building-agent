"""长期记忆 CRUD — SQLite 存储元数据，ChromaDB 存储向量。

分层策略:
- 当前阶段 (0.5): SQLite LIKE 做关键词检索过渡
- 阶段 1B: ChromaDB 接管向量检索，search_memories_by_keyword 替换为向量相似度

Upsert 策略:
- save_memory 按 (user_id, memory_type, key) 去重
- 无 key 的记忆每次新增（如 conversation_summary）
- 有 key 的记忆覆盖更新（如 report_style 偏好只保留最新值）

淘汰策略 (预留):
- importance + access_count + last_accessed_at 三因子
- 阶段 1.5 实现：记忆总数超阈值时淘汰低重要度+低热度记忆
"""
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import ConversationMemory


def save_memory(
    db: Session,
    user_id: int,
    content: str,
    memory_type: str,
    key: str | None = None,
    conversation_id: int | None = None,
    importance: float = 0.5,
    chroma_id: str | None = None,
) -> tuple:
    """保存长期记忆。按 (user_id, memory_type, key) 去重，返回 (memory, created)。"""
    existing = None
    if key:
        existing = (
            db.query(ConversationMemory)
            .filter(
                ConversationMemory.user_id == user_id,
                ConversationMemory.memory_type == memory_type,
                ConversationMemory.key == key,
            )
            .first()
        )

    if existing:
        old = existing.content[:40] if existing.content else ""
        existing.content = content
        existing.importance = importance
        existing.chroma_id = chroma_id
        if conversation_id is not None:
            existing.conversation_id = conversation_id
        db.commit()
        db.refresh(existing)
        if old != content[:40]:
            print(f"[Memory] 冲突更新 [{key}]: {old}... → {content[:40]}...")
        return existing, False

    mem = ConversationMemory(
        user_id=user_id,
        conversation_id=conversation_id,
        memory_type=memory_type,
        key=key,
        content=content,
        importance=importance,
        chroma_id=chroma_id,
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    # 异步写入向量索引（非阻塞，失败不影响主流程）
    try:
        from agent.rag import index_memory_vector
        cid = index_memory_vector(mem.id, content, user_id, conversation_id or 0)
        if cid:
            mem.chroma_id = cid
            db.commit()
    except Exception:
        pass
    return mem, True


def get_user_memories(
    db: Session,
    user_id: int,
    memory_type: str | None = None,
    min_importance: float = 0.0,
    limit: int = 50,
    offset: int = 0,
) -> list[ConversationMemory]:
    query = db.query(ConversationMemory).filter(
        ConversationMemory.user_id == user_id,
        ConversationMemory.importance >= min_importance,
    )
    if memory_type:
        query = query.filter(ConversationMemory.memory_type == memory_type)
    return (
        query.order_by(ConversationMemory.importance.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def search_memories_by_keyword(
    db: Session,
    user_id: int,
    keyword: str,
    conversation_id: int | None = None,
    limit: int = 10,
) -> list[ConversationMemory]:
    """基于 SQLite LIKE 的简单关键词检索（阶段 0.5 方案）。"""
    pattern = f"%{keyword}%"
    query = (
        db.query(ConversationMemory)
        .filter(
            ConversationMemory.user_id == user_id,
            ConversationMemory.content.like(pattern)
            | ConversationMemory.key.like(pattern),
        )
    )
    if conversation_id is not None:
        query = query.filter(ConversationMemory.conversation_id == conversation_id)
    return (
        query.order_by(ConversationMemory.importance.desc())
        .limit(limit)
        .all()
    )


def record_memory_access(db: Session, memory_id: int) -> None:
    mem = (
        db.query(ConversationMemory)
        .filter(ConversationMemory.id == memory_id)
        .first()
    )
    if mem:
        mem.access_count = (mem.access_count or 0) + 1
        mem.last_accessed_at = datetime.now(timezone.utc)
        db.commit()


def delete_memory(db: Session, memory_id: int) -> bool:
    mem = (
        db.query(ConversationMemory)
        .filter(ConversationMemory.id == memory_id)
        .first()
    )
    if not mem:
        return False
    db.delete(mem)
    db.commit()
    return True


def get_memory_stats(db: Session, user_id: int) -> dict:
    total = (
        db.query(func.count(ConversationMemory.id))
        .filter(ConversationMemory.user_id == user_id)
        .scalar()
    )
    by_type = (
        db.query(
            ConversationMemory.memory_type,
            func.count(ConversationMemory.id),
        )
        .filter(ConversationMemory.user_id == user_id)
        .group_by(ConversationMemory.memory_type)
        .all()
    )
    return {
        "total": total or 0,
        "by_type": [{"type": t, "count": c} for t, c in by_type],
    }
