"""健康检查接口测试。"""
from unittest.mock import patch


class TestHealth:
    def test_health_structure(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "database" in data
        assert "ollama" in data
        assert "models" in data
        # status 要么是 ok 要么是 degraded
        assert data["status"] in ("ok", "degraded")

    def test_health_db_ok(self, client):
        resp = client.get("/health")
        assert resp.json()["database"] == "ok"

    def test_health_without_auth(self, client):
        """health 端点不需要认证。"""
        resp = client.get("/health")
        assert resp.status_code == 200
