"""Inspection API — 多图巡检 + SSE 流式进度。"""

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth import get_current_user

router = APIRouter(prefix="/inspection", tags=["inspection"])


class ImageResult(BaseModel):
    index: int
    material: str = ""
    floor: str = ""
    has_extension: str = ""
    defects: list[dict] = []


class InspectionResponse(BaseModel):
    record_id: int
    report: str
    annotated_images: list[str]  # base64 JPEG (with defect boxes)
    images: list[ImageResult]    # per-image CV results


async def _decode_images(images: list[UploadFile]) -> list:
    import cv2
    import numpy as np
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
    return decoded


def _run_inspection(decoded: list, user_id: int) -> dict:
    """执行完整巡检流程，返回 {record_id, report, annotated_images, images}。"""
    import base64
    import cv2
    import numpy as np

    from agent.skills.inspection_skill import InspectionSkill, draw_defects
    from db import InspectionRecord, SessionLocal

    skill = InspectionSkill()
    skill._ensure_predictors()

    db = SessionLocal()
    try:
        record = InspectionRecord(user_id=user_id, status="collecting")
        db.add(record)
        db.flush()

        for img in decoded:
            skill._add_image(db, record, img)
        skill._run_inspection_on_all(db, record)

        report = record.report or "报告生成失败。"
        record_id = record.id

        # 逐图采集 CV 结果 + 标注图
        annotated_b64 = []
        image_results = []
        for i, img_entry in enumerate(record.images or []):
            defects = []
            if img_entry.chat_image and img_entry.chat_image.defects:
                defects = [{"id": j + 1, "type": d.defect_type, "area": d.area, "box": d.box_coords}
                           for j, d in enumerate(img_entry.chat_image.defects)]

            image_results.append(ImageResult(
                index=i + 1,
                material=img_entry.material or "",
                floor=img_entry.floor or "",
                has_extension=img_entry.has_extension or "",
                defects=defects,
            ))

            # 标注图
            if img_entry.chat_image and img_entry.chat_image.data:
                nparr = np.frombuffer(img_entry.chat_image.data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    annotated = draw_defects(img_rgb, defects)
                    _, buf = cv2.imencode(".jpg", cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR))
                    annotated_b64.append(base64.b64encode(buf.tobytes()).decode("utf-8"))

        return {
            "record_id": record_id,
            "report": report,
            "annotated_images": annotated_b64,
            "images": [r.model_dump() for r in image_results],
        }
    finally:
        db.close()


@router.post("/multi", response_model=InspectionResponse)
async def inspect_multi(
    message: str = Query(default="", description="用户附加说明"),
    stream: bool = Query(default=False, description="SSE 流式进度"),
    user: dict = Depends(get_current_user),
    images: list[UploadFile] = File(..., min_length=3, max_length=10),
):
    """多图巡检: 上传 >=3 张图 → CV 检测 → Report Agent → 报告+标注图+逐图结果。"""
    if len(images) < 3:
        raise HTTPException(status_code=400, detail="至少需要 3 张图片")

    decoded = await _decode_images(images)

    if stream:
        # SSE 流式进度
        event_queue: asyncio.Queue = asyncio.Queue()

        def _on_progress(step: str, detail: str = ""):
            try:
                event_queue.put_nowait({"step": step, "detail": detail})
            except Exception:
                pass

        async def event_stream():
            import concurrent.futures
            loop = asyncio.get_event_loop()
            # 发送开始事件
            _on_progress("start", f"共 {len(decoded)} 张图片")
            yield f"data: {json.dumps({'type':'start','total':len(decoded)}, ensure_ascii=False)}\n\n"

            # 逐图 CV
            from agent.skills.inspection_skill import InspectionSkill
            skill = InspectionSkill()
            skill._ensure_predictors()
            step_names = [("material", "材质"), ("floor", "楼层"), ("extension", "加层"), ("defect", "隐患")]
            cv_results = []
            for i, img in enumerate(decoded):
                result = {"index": i + 1}
                for name, label in step_names:
                    _on_progress(name, f"图{i+1} {label}")
                    yield f"data: {json.dumps({'type':'step','image':i+1,'total':len(decoded),'tool':name,'label':label}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)
                r = skill._inspect_single(img)
                cv_results.append(r)
                yield f"data: {json.dumps({'type':'cv_done','image':i+1,'material':r['material'],'floor':r['floor'],'extension':r['has_extension'],'defects':len(r.get('defects',[]) or [])}, ensure_ascii=False)}\n\n"

            # 报告生成
            _on_progress("report", "Report Agent 生成中...")
            yield f"data: {json.dumps({'type':'step','tool':'report','label':'Report Agent 生成报告中...'}, ensure_ascii=False)}\n\n"

            # Run blocking inspection in thread
            future = loop.run_in_executor(None, _run_inspection, decoded, user["user_id"])

            while not future.done():
                try:
                    await asyncio.wait_for(event_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    yield ":keepalive\n\n"

            result = future.result()
            yield f"data: {json.dumps({'type':'done','record_id':result['record_id'],'report':result['report'],'annotated_images':result['annotated_images'],'images':result['images']}, ensure_ascii=False)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # 非流式
    result = _run_inspection(decoded, user["user_id"])
    return InspectionResponse(
        record_id=result["record_id"],
        report=result["report"],
        annotated_images=result["annotated_images"],
        images=[ImageResult(**r) for r in result["images"]],
    )
