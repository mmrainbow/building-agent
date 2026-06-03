"""数据模型和新增 CRUD 测试。"""
from sqlalchemy import inspect

from db import (
    add_message,
    create_conversation,
    create_feedback,
    delete_conversation,
    get_conversation_messages,
    get_recent_messages,
    get_user_conversations,
    get_user_memories,
    get_memory_stats,
    save_memory,
    search_memories_by_keyword,
)
from db.database import engine
from .conftest import register_and_login


class TestNewModelsExist:
    """验证所有新表可被 SQLAlchemy 识别。"""

    def test_all_tables_created(self):
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        expected = {
            "users",
            "inspection_records",
            "defects",
            "conversations",
            "chat_messages",
            "conversation_memories",
            "user_preferences",
            "feedbacks",
            "knowledge_documents",
            "knowledge_chunks",
        }
        missing = expected - tables
        assert not missing, f"Missing tables: {missing}"

    def test_user_has_new_columns(self):
        inspector = inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("users")}
        assert "last_login_at" in cols
        assert "is_active" in cols


class TestConversationCRUD:
    def test_create_and_list_conversations(self, client):
        token = register_and_login(client, "chat_user", "pass123")

        from db import SessionLocal
        db = SessionLocal()
        try:
            from db import get_user_by_id
            # 通过 API 登录后 user 已创建，查一下 id
            from jose import jwt as jose_jwt
            payload = jose_jwt.decode(token, "", options={"verify_signature": False})
            user_id = payload["sub"]

            conv = create_conversation(db, int(user_id), title="测试对话")
            assert conv.id is not None
            assert conv.title == "测试对话"

            convs = get_user_conversations(db, int(user_id))
            assert len(convs) == 1
        finally:
            db.close()

    def test_delete_conversation(self, client):
        token = register_and_login(client, "del_user", "pass123")
        from jose import jwt as jose_jwt
        from db import SessionLocal
        payload = jose_jwt.decode(token, "", options={"verify_signature": False})
        user_id = payload["sub"]

        db = SessionLocal()
        try:
            conv = create_conversation(db, int(user_id), title="待删除")
            assert delete_conversation(db, conv.id) is True
            assert delete_conversation(db, 99999) is False
        finally:
            db.close()


class TestChatMessageCRUD:
    def test_add_and_retrieve_messages(self, client):
        token = register_and_login(client, "msg_user", "pass123")
        from jose import jwt as jose_jwt
        from db import SessionLocal
        payload = jose_jwt.decode(token, "", options={"verify_signature": False})
        user_id = payload["sub"]

        db = SessionLocal()
        try:
            conv = create_conversation(db, int(user_id), title="消息测试")
            add_message(db, conv.id, "user", "这栋楼的材质是什么？")
            add_message(db, conv.id, "assistant", "材质是 Face Brick")

            msgs = get_conversation_messages(db, conv.id)
            assert len(msgs) == 2
            assert msgs[0].role == "user"
            assert msgs[1].role == "assistant"

            recent = get_recent_messages(db, conv.id, limit=1)
            assert len(recent) == 1
            assert recent[0].role == "assistant"
        finally:
            db.close()


class TestConversationMemory:
    def test_save_and_retrieve_memories(self):
        from db import SessionLocal
        db = SessionLocal()
        try:
            # 先建一个 user
            from db import create_user
            user = create_user(db, "mem_user", "pass123")
            assert user is not None

            save_memory(db, user.id, "用户偏好简短报告", "user_fact", key="report_style")
            save_memory(db, user.id, "讨论过北京朝阳区住宅楼", "building_info", importance=0.9)

            mems = get_user_memories(db, user.id, min_importance=0.5)
            assert len(mems) >= 1

            all_mems = get_user_memories(db, user.id)
            assert len(all_mems) >= 2

            # 关键词检索
            results = search_memories_by_keyword(db, user.id, "北京")
            assert len(results) >= 1
            assert "北京" in results[0].content

            # 统计
            stats = get_memory_stats(db, user.id)
            assert stats["total"] >= 2
        finally:
            db.close()

    def test_upsert_memory_by_key(self):
        from db import SessionLocal
        db = SessionLocal()
        try:
            from db import create_user
            user = create_user(db, "upsert_user", "pass123")

            save_memory(db, user.id, "v1", "user_fact", key="version")
            save_memory(db, user.id, "v2", "user_fact", key="version")

            mems = get_user_memories(db, user.id, memory_type="user_fact")
            version_mems = [m for m in mems if m.key == "version"]
            assert len(version_mems) == 1
            assert version_mems[0].content == "v2"
        finally:
            db.close()


class TestFeedback:
    def test_create_and_retrieve_feedback(self):
        from db import SessionLocal
        db = SessionLocal()
        try:
            from db import create_user
            user = create_user(db, "fb_user", "pass123")

            fb = create_feedback(
                db,
                user.id,
                feedback_type="inspection_correction",
                target_field="material",
                original_value="Coating",
                corrected_value="Face Brick",
                rating=4,
            )
            assert fb.id is not None
            assert fb.rating == 4

            # 重复提交同字段 → upsert
            fb2 = create_feedback(
                db,
                user.id,
                feedback_type="inspection_correction",
                target_field="material",
                rating=5,
            )
            assert fb2.id == fb.id
            assert fb2.rating == 5
        finally:
            db.close()
