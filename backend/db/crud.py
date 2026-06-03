import bcrypt
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Defect, ImageInspection, InspectionRecord, User, UserRole

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


