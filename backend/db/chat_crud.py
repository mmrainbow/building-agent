"""对话和消息 CRUD 操作。

约定：
- 所有查询按 updated_at/created_at 倒序，调用方自行反转
- add_message 自动更新 Conversation.message_count
- 删除对话时 SQLAlchemy cascade 自动删除所有消息
"""
from sqlalchemy.orm import Session

from .models import ChatMessage, Conversation


def create_conversation(
    db: Session, user_id: int, title: str | None = None, model: str | None = None
) -> Conversation:
    conv = Conversation(
        user_id=user_id,
        title=title or "新对话",
        model=model,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_conversation(db: Session, conversation_id: int) -> Conversation | None:
    return db.query(Conversation).filter(Conversation.id == conversation_id).first()


def get_user_conversations(
    db: Session, user_id: int, limit: int = 50, offset: int = 0
) -> list[Conversation]:
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .filter(Conversation.title != "__inspection__")
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def update_conversation_title(db: Session, conversation_id: int, title: str) -> None:
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv:
        conv.title = title
        db.commit()


def delete_conversation(db: Session, conversation_id: int) -> bool:
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conv:
        return False
    db.delete(conv)
    db.commit()
    return True


def add_message(
    db: Session,
    conversation_id: int,
    role: str,
    content: str,
    metadata: dict | None = None,
    image_blob: bytes | None = None,
    mime_type: str = "image/jpeg",
) -> ChatMessage:
    msg = ChatMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
        metadata_=metadata or {},
    )
    db.add(msg)
    db.flush()  # 获取 msg.id

    # 图片存入 chat_images 表
    if image_blob:
        from .models import ChatImage
        img = ChatImage(message_id=msg.id, mime_type=mime_type, data=image_blob)
        db.add(img)

    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv:
        conv.message_count = (conv.message_count or 0) + 1
    db.commit()
    db.refresh(msg)
    return msg


def get_conversation_messages(
    db: Session,
    conversation_id: int,
    limit: int = 100,
    before_id: int | None = None,
) -> list[ChatMessage]:
    """分页拉取消息，返回时间正序列表。

    before_id: 游标分页，传上次最后一条消息的 id 即可加载更早的消息。
    返回前 [::-1] 反转是因为数据库查询是倒序的，但调用方期望正序。
    """
    query = db.query(ChatMessage).filter(
        ChatMessage.conversation_id == conversation_id
    )
    if before_id is not None:
        query = query.filter(ChatMessage.id < before_id)
    return (
        query.order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()[::-1]
    )


def get_recent_messages(
    db: Session, conversation_id: int, limit: int = 20
) -> list[ChatMessage]:
    """获取最近 N 条消息，按时间正序返回。"""
    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return msgs[::-1]
