"""反馈数据 CRUD 操作。

Upsert 策略:
- create_feedback 按 (user_id, feedback_type, target_field, record_id/message_id) 去重
- 同一用户对同一字段重复提交时覆盖旧值（避免刷评分）
- 微调数据导出时只取有 corrected_value 的 inspection_correction 记录
"""
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Feedback


def create_feedback(
    db: Session,
    user_id: int,
    feedback_type: str,
    record_id: int | None = None,
    message_id: int | None = None,
    target_field: str | None = None,
    original_value: str | None = None,
    corrected_value: str | None = None,
    rating: int | None = None,
    comment: str | None = None,
) -> Feedback:
    # 同一用户对同一目标的同类型反馈，以最新为准
    existing = (
        db.query(Feedback)
        .filter(
            Feedback.user_id == user_id,
            Feedback.feedback_type == feedback_type,
            Feedback.target_field == target_field,
        )
    )
    if record_id is not None:
        existing = existing.filter(Feedback.record_id == record_id)
    if message_id is not None:
        existing = existing.filter(Feedback.message_id == message_id)
    existing = existing.first()

    if existing:
        existing.rating = rating
        existing.corrected_value = corrected_value
        existing.comment = comment
        existing.created_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing

    fb = Feedback(
        user_id=user_id,
        record_id=record_id,
        message_id=message_id,
        feedback_type=feedback_type,
        target_field=target_field,
        original_value=original_value,
        corrected_value=corrected_value,
        rating=rating,
        comment=comment,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def get_feedback_list(
    db: Session,
    feedback_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Feedback]:
    query = db.query(Feedback)
    if feedback_type:
        query = query.filter(Feedback.feedback_type == feedback_type)
    return (
        query.order_by(Feedback.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_user_feedback(
    db: Session,
    user_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[Feedback]:
    return (
        db.query(Feedback)
        .filter(Feedback.user_id == user_id)
        .order_by(Feedback.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_feedback_stats(db: Session) -> dict:
    total = db.query(func.count(Feedback.id)).scalar() or 0
    avg_rating = (
        db.query(func.avg(Feedback.rating))
        .filter(Feedback.rating.isnot(None))
        .scalar()
    )
    by_type = (
        db.query(Feedback.feedback_type, func.count(Feedback.id))
        .group_by(Feedback.feedback_type)
        .all()
    )
    return {
        "total": total,
        "average_rating": round(float(avg_rating), 2) if avg_rating else None,
        "by_type": [{"type": t, "count": c} for t, c in by_type],
    }


def export_feedback_for_finetune(
    db: Session,
    feedback_type: str = "inspection_correction",
    limit: int = 1000,
) -> list[dict]:
    """导出反馈数据为微调格式 (JSONL-ready)。"""
    rows = (
        db.query(Feedback)
        .filter(Feedback.feedback_type == feedback_type)
        .filter(Feedback.corrected_value.isnot(None))
        .order_by(Feedback.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "prompt": f"识别建筑{fb.target_field or '特征'}",
            "input": fb.original_value,
            "completion": fb.corrected_value,
        }
        for fb in rows
    ]
