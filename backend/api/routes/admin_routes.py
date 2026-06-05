"""管理路由 — /admin/users。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.auth import require_admin
from api.schemas import UserResponse
from db import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


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
