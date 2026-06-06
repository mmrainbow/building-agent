"""FastAPI 应用入口 — 仅负责 app 创建、中间件、路由注册。"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.chat import router as chat_router
from api.inspection import router as inspection_router
from api.routes.admin_routes import router as admin_router
from api.routes.auth_routes import router as auth_router
from api.routes.health_routes import router as health_router
from api.routes.history_routes import router as history_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap_data()
    yield


def _bootstrap_data() -> None:
    """初始化数据库，并确保初始普通用户和管理员存在。"""
    from db import SessionLocal, create_user, init_db
    from db.models import User, UserRole

    init_db()
    db = SessionLocal()
    try:
        # 已有记忆未向量化的 → 迁移
        try:
            from agent.rag import migrate_memories_to_chroma
            migrate_memories_to_chroma(db)
        except Exception:
            pass
        username = os.getenv("INIT_USERNAME", "user123")
        password = os.getenv("INIT_PASSWORD", "user123")
        user = None
        if not db.query(User).filter(User.username == username).first():
            user = create_user(db=db, username=username, password=password)
        if user:
            print(f"已创建初始用户: {username} / {password}")

        admin_username = os.getenv("INIT_ADMIN_USERNAME", "admin")
        admin_password = os.getenv("INIT_ADMIN_PASSWORD", "admin123456")
        admin = db.query(User).filter(User.username == admin_username).first()
        if admin is None:
            admin = create_user(
                db=db,
                username=admin_username,
                password=admin_password,
                role=UserRole.admin,
            )
            if admin:
                print(f"已创建初始管理员: {admin_username} / {admin_password}")
        elif admin.role != UserRole.admin:
            admin.role = UserRole.admin
            db.commit()
            print(f"已将用户 {admin_username} 设置为管理员")
    finally:
        db.close()


app = FastAPI(title="Building Inspection API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 路由注册
app.include_router(auth_router)       # /register, /token, /login, /token/refresh
app.include_router(chat_router)       # /chat/*
app.include_router(inspection_router) # /inspection/*
app.include_router(history_router)    # /history/*
app.include_router(admin_router)      # /admin/*
app.include_router(health_router)     # /health, /agent/status
