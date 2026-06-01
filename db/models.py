import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserRole(str, enum.Enum):
    user = "user"  # 默认角色（普通用户）
    admin = "admin"  # 管理员


class MemoryType(str, enum.Enum):
    """长期记忆分类，LLM 自动提取时根据内容标注类型。"""
    user_fact = "user_fact"          # 用户身份/偏好/需求
    building_info = "building_info"  # 讨论过的建筑特征
    preference = "preference"        # 用户明确表达的偏好变更
    summary = "summary"              # 对话阶段摘要


class FeedbackType(str, enum.Enum):
    inspection_correction = "inspection_correction"  # 巡检结果纠错
    chat_rating = "chat_rating"                      # 对话质量评分
    report_rating = "report_rating"                  # 报告整体评价


# ── 用户 ─────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.user, nullable=False)
    is_active = Column(Boolean, default=True)  # 软删除标记
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime)

    records = relationship(
        "InspectionRecord", back_populates="user", cascade="all, delete-orphan"
    )
    conversations = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    memories = relationship(
        "ConversationMemory", back_populates="user", cascade="all, delete-orphan"
    )
    feedbacks = relationship(
        "Feedback", back_populates="user", cascade="all, delete-orphan"
    )
    preferences = relationship(
        "UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


# ── 巡检 ─────────────────────────────────────────────────


class InspectionRecord(Base):
    """一次巡检会话 — 对同一建筑的多张图片进行检测，汇总生成一份报告。"""
    __tablename__ = "inspection_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    report = Column(Text)  # 综合所有图片汇总生成的巡检报告
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="records")
    images = relationship(
        "ImageInspection", back_populates="record", cascade="all, delete-orphan"
    )


class ImageInspection(Base):
    """巡检中的单张图片 — 检测结果 + 指向 chat_images（图片本体不重复存）。"""
    __tablename__ = "image_inspection"

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(
        Integer, ForeignKey("inspection_records.id", ondelete="CASCADE"), nullable=False
    )
    chat_image_id = Column(
        Integer, ForeignKey("chat_images.id", ondelete="SET NULL"), nullable=True
    )
    image_name = Column(String(255))
    material = Column(String(100))
    floor = Column(String(20))
    has_extension = Column(String(20))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    record = relationship("InspectionRecord", back_populates="images")
    chat_image = relationship("ChatImage", backref="inspection_images")
    defects = relationship(
        "Defect", back_populates="image", cascade="all, delete-orphan"
    )


class Defect(Base):
    """图片级的隐患 — 每条缺陷属于某张巡检图片。"""
    __tablename__ = "defects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(
        Integer, ForeignKey("image_inspection.id", ondelete="CASCADE"), nullable=False
    )
    defect_type = Column(String(50))
    area = Column(Float)
    box_coords = Column(JSON)

    image = relationship("ImageInspection", back_populates="defects")


# ── 对话 ─────────────────────────────────────────────────


class Conversation(Base):
    """一次完整的对话会话。每个用户可以有多条对话。"""
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255))  # 由首次提问自动生成，用户可手动修改
    model = Column(String(100))
    message_count = Column(Integer, default=0)  # 冗余字段，避免频繁 COUNT 查询
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    """对话中的单条消息。按 created_at 正序排列即对话时间线。"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(20), nullable=False)  # 'user' | 'assistant' | 'system'
    content = Column(Text, nullable=False)
    # metadata 存储 tokens, latency_ms, sources (RAG引用) 等可选信息
    metadata_ = Column("metadata", JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    conversation = relationship("Conversation", back_populates="messages")
    images = relationship(
        "ChatImage", back_populates="message", cascade="all, delete-orphan"
    )


class ChatImage(Base):
    """用户上传的图片 — BLOB 存数据库，项目移动不丢数据。"""
    __tablename__ = "chat_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(
        Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False
    )
    mime_type = Column(String(50), default="image/jpeg")
    data = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    message = relationship("ChatMessage", back_populates="images")


# ── 长期记忆 ─────────────────────────────────────────────


class ConversationMemory(Base):
    """长期记忆 — SQLite 存元数据，向量存 ChromaDB (阶段1B)。

    key 相同的记忆会被 upsert（见 memory_crud.save_memory）。
    conversation_id 可为 NULL（跨对话记忆），删除对话时不级联删除记忆。
    """
    __tablename__ = "conversation_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id", ondelete="SET NULL")
    )
    memory_type = Column(String(30), nullable=False)
    key = Column(String(255))  # upsert 去重键 (user_id + memory_type + key)
    content = Column(Text, nullable=False)
    chroma_id = Column(String(255))  # 阶段1B 填充，当前阶段为 NULL
    importance = Column(Float, default=0.5)  # 0-1，影响检索优先级和记忆淘汰
    access_count = Column(Integer, default=0)  # 热度指标，辅助记忆淘汰
    last_accessed_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="memories")


# ── 用户偏好 ─────────────────────────────────────────────


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    language = Column(String(10), default="zh")
    report_style = Column(String(20), default="standard")
    preferred_model = Column(String(100))
    extra = Column(JSON)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="preferences")


# ── 反馈 ─────────────────────────────────────────────────


class Feedback(Base):
    """用户反馈 — 支持巡检纠错和对话评分两种场景。

    record_id 和 message_id 至少有一个非 NULL（取决于 feedback_type）。
    同用户对同目标同字段的反馈会 upsert，避免重复提交占满数据库。
    """
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    record_id = Column(
        Integer, ForeignKey("inspection_records.id", ondelete="SET NULL")
    )
    message_id = Column(
        Integer, ForeignKey("chat_messages.id", ondelete="SET NULL")
    )
    feedback_type = Column(String(30), nullable=False)
    target_field = Column(String(100))  # 被纠错的字段名，如 'material', 'defects[0].type'
    original_value = Column(Text)   # 模型原始输出
    corrected_value = Column(Text)  # 用户修正值，仅 inspection_correction 类型使用
    rating = Column(Integer)        # 1-5 星，仅 chat_rating / report_rating 类型使用
    comment = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="feedbacks")


# ── 知识库 ───────────────────────────────────────────────


class KnowledgeDocument(Base):
    """知识库文档元数据。实际向量存储在 ChromaDB（阶段1B）。"""
    __tablename__ = "knowledge_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    file_name = Column(String(255))
    file_type = Column(String(20))     # 'pdf' | 'md' | 'txt'
    source_type = Column(String(50))   # 'regulation' | 'manual' | 'report_template' | 'general'
    chunk_count = Column(Integer, default=0)  # 冗余字段，避免频繁 COUNT
    status = Column(String(20), default="active")  # 'active' | 'archived'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    chunks = relationship(
        "KnowledgeChunk", back_populates="document", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(
        Integer, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    chroma_id = Column(String(255))
    metadata_ = Column("metadata", JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document = relationship("KnowledgeDocument", back_populates="chunks")
