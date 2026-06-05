"""巡检记录 CRUD — 保存、查询、列表。"""

from sqlalchemy.orm import Session

from .models import Defect, ImageInspection, InspectionRecord


def save_inspection(
    db: Session,
    user_id: int,
    image_name: str,
    material: str,
    floor: str,
    has_extension: str,
    report: str,
    defects: list[dict],
    chat_image_id: int | None = None,
) -> InspectionRecord:
    record = InspectionRecord(user_id=user_id, report=report)
    db.add(record)
    db.flush()

    img = ImageInspection(
        record_id=record.id,
        image_name=image_name,
        chat_image_id=chat_image_id,
        material=material,
        floor=floor,
        has_extension=has_extension,
    )
    db.add(img)
    db.flush()

    for defect_input in defects or []:
        defect = Defect(
            chat_image_id=chat_image_id,
            defect_type=str(defect_input.get("type", "")),
            area=float(defect_input.get("area", 0) or 0),
            box_coords=defect_input.get("box", []),
        )
        db.add(defect)

    db.commit()
    db.refresh(record)
    return record


def get_user_records(db: Session, user_id: int, limit: int = 50, offset: int = 0):
    return (
        db.query(InspectionRecord)
        .filter(InspectionRecord.user_id == user_id)
        .order_by(InspectionRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_all_records(db: Session, limit: int = 50, offset: int = 0):
    return (
        db.query(InspectionRecord)
        .order_by(InspectionRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_record_detail(db: Session, record_id: int) -> InspectionRecord | None:
    return db.query(InspectionRecord).filter(InspectionRecord.id == record_id).first()
