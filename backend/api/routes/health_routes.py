"""运维路由 — /health, /agent/status。"""

import os

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.auth import get_current_user
from api.schemas import HealthResponse
from db import get_db

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=HealthResponse)
def health():
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


@router.get("/agent/status")
def agent_status(
    conversation_id: int | None = None,
    user: dict = Depends(get_current_user),
):
    """Agent 监控: Manager / Memory / Report 三 Agent 状态。传入 conversation_id 则只统计该对话。"""
    import os
    import requests as req

    report_url = os.getenv("REPORT_AGENT_URL", "http://localhost:8000")
    report_online = False
    try:
        r = req.get(f"{report_url}/health", timeout=3)
        report_online = r.status_code == 200
    except Exception:
        pass

    from db import SessionLocal, get_recent_messages
    db = SessionLocal()
    try:
        if conversation_id:
            msgs = get_recent_messages(db, conversation_id, limit=50)
        else:
            from db.models import Conversation
            conv = db.query(Conversation).filter(
                Conversation.title != "__inspection__"
            ).order_by(Conversation.updated_at.desc()).first()
            msgs = get_recent_messages(db, conv.id, limit=50) if conv else []
        total_chars = sum(len(getattr(m, "content", "") or "") for m in msgs)
    finally:
        db.close()
    threshold = int(os.getenv("MEMORY_EXTRACT_THRESHOLD", "6000"))

    return {
        "manager": {"status": "online", "model": os.getenv("LLM_MODEL", "qwen3.6-flash")},
        "memory": {"total_chars": total_chars, "threshold": threshold, "pct": round(min(total_chars / threshold * 100, 100)) if threshold else 0},
        "report": {"status": "online" if report_online else "offline", "url": report_url},
    }
