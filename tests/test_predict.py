"""巡检预测接口测试。"""
import io
from .conftest import register_and_login, auth_header


class TestPredict:
    def test_predict_success(self, client):
        token = register_and_login(client)
        image_bytes = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01")  # 最小合法 JPEG

        resp = client.post(
            "/predict",
            files={"image": ("building.jpg", image_bytes, "image/jpeg")},
            headers=auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["material"] == "Face Brick"
        assert data["floor"] == "5层"
        assert data["has_extension"] == "无加层"
        assert len(data["defects"]) == 1
        assert data["defects"][0]["type"] == "裂缝"
        assert data["record_id"] is not None
        assert "测试巡检报告" in data["report"]

    def test_predict_saves_to_db(self, client):
        token = register_and_login(client)
        image_bytes = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01")

        client.post(
            "/predict",
            files={"image": ("b.jpg", image_bytes, "image/jpeg")},
            headers=auth_header(token),
        )
        # 检查历史记录中是否有刚才的巡检
        resp = client.get("/history", headers=auth_header(token))
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) == 1
        assert records[0]["material"] == "Face Brick"

    def test_predict_without_auth(self, client):
        image_bytes = io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01")
        resp = client.post(
            "/predict",
            files={"image": ("b.jpg", image_bytes, "image/jpeg")},
        )
        assert resp.status_code == 401
