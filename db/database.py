import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .models import Base

DATABASE_URL = os.getenv("INSPECTION_DB_URL", "sqlite:///./inspection.db")

engine_kwargs = {"pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update({"pool_size": 5, "max_overflow": 10})

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _create_mysql_database_if_needed() -> None:
    database_name = engine.url.database
    if not database_name:
        return

    create_db_url = DATABASE_URL.rsplit(f"/{database_name}", 1)[0]
    tmp_engine = create_engine(create_db_url, pool_pre_ping=True)
    try:
        with tmp_engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                    f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            conn.commit()
    finally:
        tmp_engine.dispose()


def init_db() -> None:
    try:
        if engine.url.get_backend_name() == "mysql":
            _create_mysql_database_if_needed()

        Base.metadata.create_all(bind=engine)
        print(f"Database initialized: {engine.url.database or 'default'}")
    except Exception as e:
        print(f"Database initialization failed: {e}")
        print(f"Current DSN: {DATABASE_URL}")
        print("Set INSPECTION_DB_URL to override, for example:")
        print("INSPECTION_DB_URL=mysql+pymysql://user:pass@localhost:3306/building_inspection")
        sys.exit(1)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
