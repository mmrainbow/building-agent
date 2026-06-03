"""认证逻辑 — 返回纯数据，UI 组件由 app.py 处理。"""
import os

from db import SessionLocal, authenticate_user, create_user, init_db
from db.models import User, UserRole

from .constants import TEXT

INIT_ADMIN_USERNAME = os.getenv("INIT_ADMIN_USERNAME", "admin")
INIT_ADMIN_PASSWORD = os.getenv("INIT_ADMIN_PASSWORD")


def bootstrap_data() -> None:
    init_db()
    db = SessionLocal()
    try:
        has_user = db.query(User).first() is not None
        if has_user:
            return
        if not INIT_ADMIN_PASSWORD:
            print(
                "未检测到用户且未设置 INIT_ADMIN_PASSWORD，"
                "已跳过默认管理员创建。"
            )
            return
        user = create_user(
            db=db,
            username=INIT_ADMIN_USERNAME,
            password=INIT_ADMIN_PASSWORD,
            role=UserRole.admin,
        )
        if user:
            print(f"已创建初始管理员账户: {INIT_ADMIN_USERNAME}")
    finally:
        db.close()


def handle_login(username, password) -> tuple[str, dict | None, bool, bool]:
    """登录验证，返回 (消息, user_state, 显示登录页, 显示主页)。"""
    if not username or not password:
        return TEXT["register_empty"], None, True, False

    db = SessionLocal()
    try:
        user = authenticate_user(db, username, password)
        if not user:
            return TEXT["invalid_credentials"], None, True, False

        user_state = {
            "user_id": user.id,
            "username": user.username,
            "role": user.role.value if isinstance(user.role, UserRole) else user.role,
        }
        return (
            f"{TEXT['login_success']} 欢迎你，{user.username}。",
            user_state,
            False,
            True,
        )
    finally:
        db.close()


def handle_register(username, password, confirm_password) -> str:
    """注册，返回结果消息。"""
    if not username or not password:
        return TEXT["register_empty"]
    if password != confirm_password:
        return TEXT["register_mismatch"]
    if len(password) < 6:
        return TEXT["register_short_password"]

    db = SessionLocal()
    try:
        user = create_user(db, username, password)
        return TEXT["register_success"] if user else TEXT["register_exists"]
    finally:
        db.close()


def do_logout() -> tuple[None, bool, bool]:
    """登出，返回 (None, 显示登录页, 显示主页)。"""
    return None, True, False
