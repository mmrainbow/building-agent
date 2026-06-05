"""Inspection API — 多图巡检接口。"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from api.auth import get_current_user

router = APIRouter(prefix="/inspection", tags=["inspection"])


class InspectionResponse(BaseModel):
    record_id: int
    report: str
    annotated_images: list[str]  # base64 JPEG


@router.post("/multi", response_model=InspectionResponse)
async def inspect_multi(
    message: str = Query(default="", description="用户附加说明"),
    user: dict = Depends(get_current_user),
    images: list[UploadFile] = File(..., min_length=3, max_length=10),
):
    """多图巡检: 上传 >=3 张图 → CV 检测 → Report Agent → 返回报告+标注图片。"""
    import base64
    import cv2
    import numpy as np

    from agent.skills.inspection_skill import InspectionSkill, draw_defects
    from db import InspectionRecord, SessionLocal

    if len(images) < 3:
        raise HTTPException(status_code=400, detail="至少需要 3 张图片")

    # 读取并解码所有图片
    decoded = []
    for img_file in images:
        content = await img_file.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"图片 {img_file.filename} 为空")
        nparr = np.frombuffer(content, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(status_code=400, detail=f"无法解码图片 {img_file.filename}")
        decoded.append(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    skill = InspectionSkill()
    skill._ensure_predictors()

    db = SessionLocal()
    try:
        record = InspectionRecord(user_id=user["user_id"], status="collecting")
        db.add(record)
        db.flush()

        for img in decoded:
            skill._add_image(db, record, img)
        skill._run_inspection_on_all(db, record)

        report = record.report or "报告生成失败。"
        # 生成标注图片 base64
        annotated_b64 = _get_annotated_images(db, record, skill)

        return InspectionResponse(
            record_id=record.id,
            report=report,
            annotated_images=annotated_b64,
        )
    finally:
        db.close()


def _get_annotated_images(db, record, skill) -> list[str]:
    """从已检测的 record 生成标注图片 base64 列表。"""
    import base64
    import cv2
    import numpy as np

    from agent.skills.inspection_skill import draw_defects

    results = []
    for img_entry in record.images or []:
        if img_entry.chat_image and img_entry.chat_image.data:
            nparr = np.frombuffer(img_entry.chat_image.data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                defects = [{"id": i + 1, "type": d.defect_type, "area": d.area, "box": d.box_coords}
                           for i, d in enumerate((img_entry.chat_image.defects if img_entry.chat_image else []) or [])]
                annotated = draw_defects(img_rgb, defects)
                _, buf = cv2.imencode(".jpg", cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR))
                results.append(base64.b64encode(buf.tobytes()).decode("utf-8"))
    return results
