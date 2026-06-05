"""建筑规范知识检索 Tool — ChromaDB 语义检索 + SQLite 用户记忆回退。"""

from .schemas import KNOWLEDGE_SCHEMA


class KnowledgeSearchTool:
    """建筑规范知识检索 — ChromaDB 语义检索为主，SQLite 用户记忆为回退。"""

    @property
    def schema(self):
        return KNOWLEDGE_SCHEMA

    def execute(self, query=None, user_id=None, **kwargs) -> str:
        if not query:
            return "错误：请提供检索关键词。"

        try:
            from agent.rag import search_regulations
            regs = search_regulations(query, k=5)
            if regs:
                return f"📋 建筑规范条文:\n\n{regs}"
        except Exception as e:
            print(f"[KnowledgeSearch] ChromaDB 检索异常: {e}")

        try:
            from db import SessionLocal, search_memories_by_keyword
            db = SessionLocal()
            try:
                results = search_memories_by_keyword(
                    db, user_id or 0, query, limit=5
                )
                if results:
                    items = [
                        f"- [{m.memory_type}] {m.content[:200]}" for m in results
                    ]
                    return "💾 用户记忆（规范库不可用时的回退）:\n" + "\n".join(items)
            finally:
                db.close()
        except Exception:
            pass

        return f"未找到与'{query}'相关的规范或记忆。"
