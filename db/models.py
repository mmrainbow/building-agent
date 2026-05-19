from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime, timezone
import enum

Base = declarative_base()


class UserRole(str, enum.Enum):
    inspector = "inspector"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.inspector, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    records = relationship("InspectionRecord", back_populates="user", cascade="all, delete-orphan")


class InspectionRecord(Base):
    __tablename__ = "inspection_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    image_name = Column(String(255))
    material = Column(String(100))
    floor = Column(String(20))
    has_extension = Column(String(20))
    report = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="records")
    defects = relationship("Defect", back_populates="record", cascade="all, delete-orphan")


class Defect(Base):
    __tablename__ = "defects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(Integer, ForeignKey("inspection_records.id", ondelete="CASCADE"), nullable=False)
    defect_type = Column(String(50))
    area = Column(Float)
    box_coords = Column(JSON)

    record = relationship("InspectionRecord", back_populates="defects")
