"""历史记录接口测试：CRUD 与权限隔离。"""
from .conftest import register_and_login, auth_header
from db import SessionLocal
from db.models import InspectionRecord, ImageInspection, Defect


def _create_test_record(user_id: int) -> int:
    """辅助函数：直接在 DB 中创建一条巡检记录，返回 record_id。"""
    db = SessionLocal()
    try:
        record = InspectionRecord(user_id=user_id, status="done", report="测试巡检报告")
        db.add(record)
        db.flush()
        img = ImageInspection(
            record_id=record.id,
            image_name="test.jpg",
            material="Face Brick",
            floor="5层",
            has_extension="无加层",
        )
        db.add(img)
        db.flush()
        defect = Defect(
            image_id=img.id,
            defect_type="裂缝",
            area=120.5,
            box_coords=[[0, 0], [10, 0], [10, 10], [0, 10]],
        )
        db.add(defect)
        db.commit()
        return record.id
    finally:
        db.close()


def _get_user_id(client, username: str = "testuser", password: str = "test123456") -> int:
    """注册并登录，返回 user_id。"""
    from db import SessionLocal as SL
    from db.models import User
    token = register_and_login(client, username, password)
    db = SL()
    try:
        user = db.query(User).filter(User.username == username).first()
        return user.id
    finally:
        db.close()


class TestHistory:
    def test_history_empty(self, client):
        token = register_and_login(client)
        resp = client.get("/history", headers=auth_header(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_after_inspection(self, client):
        token = register_and_login(client, "user1")
        # 直接在 DB 创建记录
        from db import SessionLocal as SL
        from db.models import User
        db = SL()
        try:
            user = db.query(User).filter(User.username == "user1").first()
            _create_test_record(user.id)
        finally:
            db.close()

        resp = client.get("/history", headers=auth_header(token))
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) == 1
        r = records[0]
        assert r["material"] == "Face Brick"
        assert len(r["defects"]) == 1
        assert r["defects"][0]["type"] == "裂缝"
        assert r["created_at"] is not None

    def test_record_detail_not_found(self, client):
        token = register_and_login(client)
        resp = client.get("/history/99999", headers=auth_header(token))
        assert resp.status_code == 404


class TestPermissionIsolation:
    """验证普通用户之间不能互相查看巡检记录。"""
    def test_user_cannot_see_others_records(self, client):
        # 用户 A 创建一条记录
        token_a = register_and_login(client, "user_a", "pass123")
        from db import SessionLocal as SL
        from db.models import User
        db = SL()
        try:
            user_a = db.query(User).filter(User.username == "user_a").first()
            record_id = _create_test_record(user_a.id)
        finally:
            db.close()

        # 用户 B 尝试查看 A 的记录
        token_b = register_and_login(client, "user_b", "pass456")
        resp = client.get(f"/history/{record_id}", headers=auth_header(token_b))
        assert resp.status_code == 403

    def test_admin_can_see_all_records(self, client):
        from db import create_user
        from db.models import User, UserRole

        # 手动创建 admin 用户
        db = SessionLocal()
        try:
            create_user(db, "admin_user", "admin123", role=UserRole.admin)
        finally:
            db.close()

        # 普通用户创建记录
        db = SessionLocal()
        try:
            normal_user = db.query(User).filter(User.username == "normal").first()
            if not normal_user:
                token = register_and_login(client, "normal", "pass123")
                normal_user = db.query(User).filter(User.username == "normal").first()
            record_id = _create_test_record(normal_user.id)
        finally:
            db.close()

        # Admin 可以查看
        resp = client.post("/login", json={"username": "admin_user", "password": "admin123"})
        admin_token = resp.json()["access_token"]
        resp = client.get(f"/history/{record_id}", headers=auth_header(admin_token))
        assert resp.status_code == 200
