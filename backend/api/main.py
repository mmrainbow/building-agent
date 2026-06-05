import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from api.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    require_admin,
)
from api.chat import router as chat_router
from api.inspection import router as inspection_router
from api.schemas import (
    HealthResponse,
    LoginRequest,
    RecordResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from db import (
    authenticate_user,
    create_user,
    get_all_records,
    get_db,
    get_record_detail,
    get_user_records,
    init_db,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Building Inspection API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(chat_router)
app.include_router(inspection_router)


def _can_access_record(user: dict, record) -> bool:
    if user["role"] == "admin":
        return True
    return record.user_id == user["user_id"]


def _record_to_dict(record) -> dict:
    images = record.images or []
    all_defects = []
    materials = []
    floors = []
    extensions = []
    for img in images:
        materials.append(img.material or "")
        floors.append(img.floor or "")
        extensions.append(img.has_extension or "")
        for defect in (img.defects or []):
            all_defects.append({
                "type": defect.defect_type,
                "area": defect.area,
                "box": defect.box_coords,
                "image_id": img.id,
            })

    return {
        "id": record.id,
        "image_count": len(images),
        "material": ", ".join(set(m for m in materials if m)) or "未知",
        "floor": ", ".join(set(f for f in floors if f)) or "未知",
        "has_extension": ", ".join(set(e for e in extensions if e)) or "未知",
        "report": record.report,
        "defects": all_defects,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


# ── 认证端点 ──────────────────────────────────────────────


@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    user = create_user(db, body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )
    return UserResponse(id=user.id, username=user.username, role=user.role.value)


# 双登录端点设计:
#   /token — OAuth2 form 格式 (Swagger UI 的 Authorize 按钮使用)
#   /login — JSON 格式 (curl/Postman/前端 fetch 使用)
# 两者返回相同的 TokenResponse

@app.post("/token", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    role = user.role.value if hasattr(user.role, "value") else user.role
    token_data = {"sub": str(user.id), "username": user.username, "role": role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@app.post("/login", response_model=TokenResponse)
def login_json(body: LoginRequest, db: Session = Depends(get_db)):
    """JSON 格式登录接口，方便 API 客户端使用。"""
    user = authenticate_user(db, body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    role = user.role.value if hasattr(user.role, "value") else user.role
    token_data = {"sub": str(user.id), "username": user.username, "role": role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@app.post("/token/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )
    user_id = int(payload["sub"])
    user_data = {"sub": str(user_id), "username": payload["username"], "role": payload["role"]}
    return TokenResponse(
        access_token=create_access_token(user_data),
        refresh_token=create_refresh_token(user_data),
    )


# ── 核心业务端点 ──────────────────────────────────────────


@app.get("/history", response_model=list[RecordResponse])
def history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user["role"] == "admin":
        records = get_all_records(db, limit=limit, offset=offset)
    else:
        records = get_user_records(db, user["user_id"], limit=limit, offset=offset)
    return [_record_to_dict(record) for record in records]


@app.get("/history/{record_id}", response_model=RecordResponse)
def record_detail(
    record_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = get_record_detail(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if not _can_access_record(user, record):
        raise HTTPException(status_code=403, detail="No permission to access this record")
    return _record_to_dict(record)


# ── 管理端点 ──────────────────────────────────────────────


@app.get("/admin/users", response_model=list[UserResponse])
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


# ── 健康检查 ──────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse)
def health():
    """健康检查 — 数据库连通性 + Ollama 可达性 + 模型文件完整性。

    模型检查仅验证文件存在，不验证权重完整性（避免加载大文件）。
    """
    import requests as req
    from sqlalchemy import text

    model_dir = os.path.join(os.path.dirname(__file__), "..", "..", "model_weights")
    required_models = [
        "add_predict.pth",
        "best.pt",
        "main_building.pt",
        "material.pth",
        "outer_obj.pt",
    ]
    models_status = {
        name: os.path.exists(os.path.join(model_dir, name))
        for name in required_models
    }

    db_status = "ok"
    try:
        db = next(get_db())
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unavailable"

    ollama_status = "ok"
    try:
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        resp = req.get(f"{ollama_url}/api/tags", timeout=5)
        if resp.status_code != 200:
            ollama_status = "unavailable"
    except Exception:
        ollama_status = "unavailable"

    overall = (
        "ok"
        if db_status == "ok" and ollama_status == "ok" and all(models_status.values())
        else "degraded"
    )
    return HealthResponse(
        status=overall,
        database=db_status,
        ollama=ollama_status,
        models=models_status,
    )


# ── Agent 监控 ──────────────────────────────────────────────


@app.get("/agent/status")
def agent_status(user: dict = Depends(get_current_user)):
    """Agent 监控: Manager / Memory / Report 三 Agent 状态。"""
    import os
    import requests as req

    # Report Agent 状态
    report_url = os.getenv("REPORT_AGENT_URL", "http://localhost:8000")
    report_online = False
    try:
        r = req.get(f"{report_url}/health", timeout=3)
        report_online = r.status_code == 200
    except Exception:
        pass

    # Memory Agent 字符统计
    from db import SessionLocal, get_recent_messages
    from db.models import Conversation
    db = SessionLocal()
    try:
        conv = db.query(Conversation).order_by(Conversation.updated_at.desc()).first()
        if conv:
            msgs = get_recent_messages(db, conv.id, limit=50)
            total_chars = sum(len(getattr(m, "content", "") or "") for m in msgs)
        else:
            total_chars = 0
    finally:
        db.close()
    threshold = int(os.getenv("MEMORY_EXTRACT_THRESHOLD", "6000"))

    return {
        "manager": {"status": "online", "model": os.getenv("LLM_MODEL", "qwen3.6-flash")},
        "memory": {"total_chars": total_chars, "threshold": threshold, "pct": round(min(total_chars / threshold * 100, 100)) if threshold else 0},
        "report": {"status": "online" if report_online else "offline", "url": report_url},
    }


# ── 历史导出 ────────────────────────────────────────────────


@app.get("/history/{record_id}/export")
def history_export(
    record_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出巡检记录为 Excel 文件。"""
    import io
    import openpyxl
    from fastapi.responses import StreamingResponse

    record = get_record_detail(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if record.user_id != user["user_id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="No permission")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "巡检报告"
    ws.append(["ID", record.id])
    ws.append(["时间", record.created_at.isoformat() if record.created_at else ""])
    ws.append(["报告", record.report or ""])
    ws.append([])
    ws.append(["图片", "材质", "楼层", "加层", "隐患数"])
    for img in record.images or []:
        ws.append([img.image_name, img.material, img.floor, img.has_extension, len(img.defects or [])])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=inspection_{record_id}.xlsx"})
