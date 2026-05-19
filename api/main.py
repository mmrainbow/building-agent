import os
import tempfile

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agent.graph import build_agent
from db import (
    SessionLocal,
    authenticate_user,
    get_all_records,
    get_daily_inspection_count,
    get_defect_type_distribution,
    get_material_distribution,
    get_overall_summary,
    get_record_detail,
    get_user_records,
    init_db,
    save_inspection,
)

app = FastAPI(title="Building Inspection API")
security = HTTPBasic()
agent = build_agent()


@app.on_event("startup")
def startup() -> None:
    init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"user_id": user.id, "username": user.username, "role": user.role.value}


def _can_access_record(user: dict, record) -> bool:
    if user["role"] == "admin":
        return True
    return record.user_id == user["user_id"]


def _record_to_dict(record) -> dict:
    return {
        "id": record.id,
        "image_name": record.image_name,
        "material": record.material,
        "floor": record.floor,
        "has_extension": record.has_extension,
        "report": record.report,
        "defects": [
            {"type": defect.defect_type, "area": defect.area, "box": defect.box_coords}
            for defect in (record.defects or [])
        ],
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


class InspectionResult(BaseModel):
    report: str | None
    material: str | None
    floor: str | None
    has_extension: str | None
    defects: list[dict]
    record_id: int | None


@app.post("/predict", response_model=InspectionResult)
async def predict(
    image: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        tmp.write(await image.read())
        tmp_path = tmp.name

    try:
        result = agent.invoke({"image_path": tmp_path})
        record = save_inspection(
            db=db,
            user_id=user["user_id"],
            image_name=image.filename or "api_upload.jpg",
            material=result.get("material", ""),
            floor=result.get("floor", ""),
            has_extension=result.get("has_extension", ""),
            report=result.get("report"),
            defects=result.get("defects", []),
        )
        return InspectionResult(
            report=result.get("report"),
            material=result.get("material", ""),
            floor=result.get("floor", ""),
            has_extension=result.get("has_extension", ""),
            defects=result.get("defects", []),
            record_id=record.id,
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.get("/history")
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


@app.get("/history/{record_id}")
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


@app.get("/statistics")
def statistics(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    query_user_id = None if user["role"] == "admin" else user["user_id"]
    return {
        "summary": get_overall_summary(db, query_user_id),
        "defect_distribution": get_defect_type_distribution(db, query_user_id),
        "material_distribution": get_material_distribution(db, query_user_id),
        "daily_trend": get_daily_inspection_count(db, 30),
    }
