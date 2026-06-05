"""历史记录路由 — /history, /history/{id}, /history/{id}/export。"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.auth import get_current_user, require_admin
from api.schemas import DefectInfo, RecordResponse
from db import get_all_records, get_db, get_record_detail, get_user_records

router = APIRouter(tags=["history"])


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
        for defect in ((img.chat_image.defects if img.chat_image else []) or []):
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


@router.get("/history", response_model=list[RecordResponse])
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


@router.get("/history/{record_id}", response_model=RecordResponse)
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


@router.get("/history/{record_id}/export")
def history_export(
    record_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出巡检记录为 Excel 文件。"""
    import io
    import openpyxl

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
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=inspection_{record_id}.xlsx"},
    )
