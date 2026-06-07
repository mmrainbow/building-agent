"""管理路由 — /admin/users, /admin/feedbacks。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.auth import require_admin
from api.schemas import UserResponse
from db import get_db
from utils.materials import material_to_zh

router = APIRouter(prefix="/admin", tags=["admin"])


class FeedbackItem(BaseModel):
    id: int
    user_id: int
    username: str | None = None
    message_id: int | None = None
    conversation_id: int | None = None
    feedback_type: str
    rating: int | None = None
    comment: str | None = None
    original_value: str | None = None
    created_at: str | None = None


class FeedbackStats(BaseModel):
    total: int
    average_rating: float | None = None
    rating_counts: dict[int, int]


class AdminDashboardStats(BaseModel):
    user_count: int
    inspection_count: int
    average_rating: float | None = None
    model_call_count: int
    defect_distribution: list[dict]
    material_distribution: list[dict]


@router.get("/users", response_model=list[UserResponse])
def list_users(
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from db.models import User
    users = db.query(User).all()
    return [
        UserResponse(
            id=u.id,
            username=u.username,
            role=u.role.value if hasattr(u.role, "value") else u.role,
        )
        for u in users
    ]


@router.get("/dashboard", response_model=AdminDashboardStats)
def dashboard_stats(
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from db.models import ChatMessage, Defect, Feedback, ImageInspection, InspectionRecord, User

    user_count = db.query(func.count(User.id)).scalar() or 0
    inspection_count = db.query(func.count(InspectionRecord.id)).scalar() or 0
    avg_rating = (
        db.query(func.avg(Feedback.rating))
        .filter(Feedback.rating.isnot(None))
        .scalar()
    )
    assistant_count = (
        db.query(func.count(ChatMessage.id))
        .filter(ChatMessage.role == "assistant")
        .scalar()
        or 0
    )
    report_count = (
        db.query(func.count(InspectionRecord.id))
        .filter(InspectionRecord.report.isnot(None))
        .scalar()
        or 0
    )
    defect_rows = (
        db.query(Defect.defect_type, func.count(Defect.id))
        .group_by(Defect.defect_type)
        .all()
    )
    material_rows = (
        db.query(ImageInspection.material, func.count(ImageInspection.id))
        .filter(ImageInspection.material.isnot(None))
        .group_by(ImageInspection.material)
        .all()
    )
    material_counts = {}
    for name, count in material_rows:
        key = material_to_zh(name)
        material_counts[key] = material_counts.get(key, 0) + int(count)

    return AdminDashboardStats(
        user_count=int(user_count),
        inspection_count=int(inspection_count),
        average_rating=round(float(avg_rating), 2) if avg_rating else None,
        model_call_count=int(assistant_count + report_count),
        defect_distribution=[
            {"name": name or "未知", "count": int(count)} for name, count in defect_rows
        ],
        material_distribution=[
            {"name": name, "count": count} for name, count in material_counts.items()
        ],
    )


@router.get("/feedbacks", response_model=list[FeedbackItem])
def list_feedbacks(
    feedback_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from db.models import ChatMessage, Feedback, User

    query = (
        db.query(Feedback, User.username, ChatMessage.conversation_id)
        .join(User, User.id == Feedback.user_id)
        .outerjoin(ChatMessage, ChatMessage.id == Feedback.message_id)
    )
    if feedback_type:
        query = query.filter(Feedback.feedback_type == feedback_type)

    rows = (
        query.order_by(Feedback.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        FeedbackItem(
            id=fb.id,
            user_id=fb.user_id,
            username=username,
            message_id=fb.message_id,
            conversation_id=conversation_id,
            feedback_type=fb.feedback_type,
            rating=fb.rating,
            comment=fb.comment,
            original_value=fb.original_value,
            created_at=fb.created_at.isoformat() if fb.created_at else None,
        )
        for fb, username, conversation_id in rows
    ]


@router.get("/feedbacks/stats", response_model=FeedbackStats)
def feedback_stats(
    feedback_type: str | None = None,
    admin: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from db.models import Feedback

    query = db.query(Feedback)
    if feedback_type:
        query = query.filter(Feedback.feedback_type == feedback_type)

    total = query.count()
    avg_rating = query.with_entities(func.avg(Feedback.rating)).filter(
        Feedback.rating.isnot(None)
    ).scalar()
    rating_rows = (
        query.with_entities(Feedback.rating, func.count(Feedback.id))
        .filter(Feedback.rating.isnot(None))
        .group_by(Feedback.rating)
        .all()
    )
    return FeedbackStats(
        total=total,
        average_rating=round(float(avg_rating), 2) if avg_rating else None,
        rating_counts={int(r): int(c) for r, c in rating_rows},
    )
