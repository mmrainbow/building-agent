import os

import gradio as gr

from db import (
    SessionLocal,
    authenticate_user,
    create_user,
    init_db,
)
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


def handle_login(username, password):
    if not username or not password:
        return TEXT["register_empty"], None, gr.update(visible=True), gr.update(visible=False)

    db = SessionLocal()
    try:
        user = authenticate_user(db, username, password)
        if not user:
            return (
                TEXT["invalid_credentials"],
                None,
                gr.update(visible=True),
                gr.update(visible=False),
            )
        user_state = {
            "user_id": user.id,
            "username": user.username,
            "role": user.role.value if isinstance(user.role, UserRole) else user.role,
        }
        return (
            f"{TEXT['login_success']} 欢迎你，{user.username}。",
            user_state,
            gr.update(visible=False),
            gr.update(visible=True),
        )
    finally:
        db.close()


def handle_register(username, password, confirm_password):
    if not username or not password:
        return TEXT["register_empty"]
    if password != confirm_password:
        return TEXT["register_mismatch"]
    if len(password) < 6:
        return TEXT["register_short_password"]

    db = SessionLocal()
    try:
        user = create_user(db, username, password)
        if user:
            return TEXT["register_success"]
        return TEXT["register_exists"]
    finally:
        db.close()


def do_logout():
    return None, gr.update(visible=True), gr.update(visible=False)
