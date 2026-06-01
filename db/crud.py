import bcrypt
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Defect, ImageInspection, InspectionRecord, User, UserRole

HAS_EXTENSION_YES = {"有加层", "存在加层", "yes", "true", "1", "has extension"}


def _is_extension_yes(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {x.lower() for x in HAS_EXTENSION_YES}


def create_user(
    db: Session,
    username: str,
    password: str,
    role: UserRole = UserRole.user,
) -> User | None:
    username = (username or "").strip()
    if not username or not password:
        return None
    if db.query(User).filter(User.username == username).first():
        return None

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    user = User(username=username, password_hash=hashed.decode("utf-8"), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.query(User).filter(User.username == (username or "").strip()).first()
    if not user:
        return None
    if not bcrypt.checkpw((password or "").encode("utf-8"), user.password_hash.encode("utf-8")):
        return None
    return user


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


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
    # 巡检会话
    record = InspectionRecord(user_id=user_id, report=report)
    db.add(record)
    db.flush()

    # 图片级检测结果（图片本体引用 chat_images）
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
            image_id=img.id,
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


def get_defect_type_distribution(db: Session, user_id: int | None = None):
    query = db.query(Defect.defect_type, func.count(Defect.id).label("cnt"))
    if user_id is not None:
        query = (
            query.join(ImageInspection)
            .join(InspectionRecord)
            .filter(InspectionRecord.user_id == user_id)
        )
    rows = query.group_by(Defect.defect_type).all()
    return [{"type": row[0], "count": row[1]} for row in rows]


def get_material_distribution(db: Session, user_id: int | None = None):
    query = db.query(ImageInspection.material)
    if user_id is not None:
        query = query.join(InspectionRecord).filter(InspectionRecord.user_id == user_id)
    materials = [row[0] for row in query.all() if row[0] and row[0] != "未知"]

    counter: dict[str, int] = {}
    for material in materials:
        for part in material.split(","):
            token = part.strip()
            if token:
                counter[token] = counter.get(token, 0) + 1

    return [
        {"material": key, "count": value}
        for key, value in sorted(counter.items(), key=lambda x: x[1], reverse=True)
    ]


def get_daily_inspection_count(db: Session, days: int = 30):
    rows = (
        db.query(
            func.date(InspectionRecord.created_at).label("date"),
            func.count(InspectionRecord.id).label("cnt"),
        )
        .group_by(func.date(InspectionRecord.created_at))
        .order_by(func.date(InspectionRecord.created_at).desc())
        .limit(days)
        .all()
    )
    return [{"date": str(row[0]), "count": row[1]} for row in reversed(rows)]


def get_overall_summary(db: Session, user_id: int | None = None):
    query = db.query(InspectionRecord)
    if user_id is not None:
        query = query.filter(InspectionRecord.user_id == user_id)

    total = query.count()
    defects_query = db.query(func.count(Defect.id))
    if user_id is not None:
        defects_query = defects_query.join(InspectionRecord).filter(InspectionRecord.user_id == user_id)
    total_defects = defects_query.scalar() or 0

    extension_count = 0
    if total > 0:
        records = query.with_entities(InspectionRecord.has_extension).all()
        extension_count = sum(1 for row in records if _is_extension_yes(row[0]))

    return {
        "total_inspections": total,
        "total_defects": total_defects,
        "extension_count": extension_count,
        "extension_rate": round(extension_count / total * 100, 1) if total > 0 else 0,
    }
