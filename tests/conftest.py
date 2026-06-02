import os
import tempfile

import pytest

# ⚠️ 必须在导入任何 db 模块前设置，确保 engine/SessionLocal 指向测试数据库
TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "building_agent_test.db")
os.environ["INSPECTION_DB_URL"] = f"sqlite:///{TEST_DB_PATH}"

from fastapi.testclient import TestClient  # noqa: E402

from db import get_db as original_get_db  # noqa: E402
from db.models import Base  # noqa: E402


def _get_test_session():
    from db.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


override_get_db = _get_test_session


@pytest.fixture(autouse=True)
def setup_db():
    from db.database import engine

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists(TEST_DB_PATH):
        try:
            os.unlink(TEST_DB_PATH)
        except OSError:
            pass


@pytest.fixture
def client():
    """FastAPI TestClient。"""
    from api.main import app

    # 覆盖 get_db 依赖，确保每次请求都使用测试数据库的新会话
    app.dependency_overrides[original_get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def register_and_login(client: TestClient, username: str = "testuser", password: str = "test123456") -> str:
    """辅助函数：注册并登录，返回 access_token。"""
    client.post("/register", json={"username": username, "password": password})
    resp = client.post("/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    """辅助函数：生成 Authorization header。"""
    return {"Authorization": f"Bearer {token}"}
