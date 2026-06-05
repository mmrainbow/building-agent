"""用户 CRUD — 注册、认证、查询。"""

import bcrypt
from sqlalchemy.orm import Session

from .models import User, UserRole


def create_user(
    db: Session,
    username: str,
    password: str,
    role: UserRole = UserRole.user,
) -> User | None:
    username = (username or "").strip()
    if not username or not password:
        return None
    if db.query(User).filter(User.username == username).first():
        return None

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = User(username=username, password_hash=hashed.decode("utf-8"), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == (username or "").strip()).first()
    if not user:
        return None
    if not bcrypt.checkpw((password or "").encode("utf-8"), user.password_hash.encode("utf-8")):
        return None
    return user


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()
