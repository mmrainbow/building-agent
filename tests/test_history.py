"""历史记录接口测试：CRUD 与权限隔离。"""
import io
from .conftest import register_and_login, auth_header


class TestHistory:
    def test_history_empty(self, client):
        token = register_and_login(client)
        resp = client.get("/history", headers=auth_header(token))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_after_predict(self, client):
        token = register_and_login(client)
        # 先做一次巡检
        img = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01")
        client.post(
            "/predict",
            files={"image": ("a.jpg", img, "image/jpeg")},
            headers=auth_header(token),
        )
        # 查历史
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
        # 用户 A 做一次巡检
        token_a = register_and_login(client, "user_a", "pass123")
        img = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01")
        resp = client.post(
            "/predict",
            files={"image": ("a.jpg", img, "image/jpeg")},
            headers=auth_header(token_a),
        )
        record_id = resp.json()["record_id"]

        # 用户 B 尝试查看 A 的记录
        token_b = register_and_login(client, "user_b", "pass456")
        resp = client.get(f"/history/{record_id}", headers=auth_header(token_b))
        assert resp.status_code == 403

    def test_admin_can_see_all_records(self, client):
        from db.models import User, UserRole
        from db import SessionLocal, create_user

        # 手动创建 admin 用户
        db = SessionLocal()
        try:
            create_user(db, "admin_user", "admin123", role=UserRole.admin)
        finally:
            db.close()

        # 普通用户做巡检
        token_user = register_and_login(client, "normal", "pass123")
        img = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01")
        resp = client.post(
            "/predict",
            files={"image": ("a.jpg", img, "image/jpeg")},
            headers=auth_header(token_user),
        )
        record_id = resp.json()["record_id"]

        # Admin 可以查看
        resp = client.post("/login", json={"username": "admin_user", "password": "admin123"})
        admin_token = resp.json()["access_token"]
        resp = client.get(f"/history/{record_id}", headers=auth_header(admin_token))
        assert resp.status_code == 200
