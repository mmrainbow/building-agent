"""认证相关测试：注册、登录、令牌刷新、权限拦截。"""
from .conftest import register_and_login, auth_header


class TestRegister:
    def test_register_success(self, client):
        resp = client.post("/register", json={"username": "tester", "password": "123456"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "tester"
        assert data["role"] == "user"
        assert "id" in data

    def test_register_duplicate_username(self, client):
        client.post("/register", json={"username": "dup", "password": "123456"})
        resp = client.post("/register", json={"username": "dup", "password": "654321"})
        assert resp.status_code == 409
        assert "已存在" in resp.json()["detail"]

    def test_register_short_password(self, client):
        resp = client.post("/register", json={"username": "user", "password": "12345"})
        assert resp.status_code == 422  # Pydantic validation: min_length=6

    def test_register_empty_username(self, client):
        resp = client.post("/register", json={"username": "", "password": "123456"})
        assert resp.status_code == 422


class TestLogin:
    def test_login_json_success(self, client):
        client.post("/register", json={"username": "dev", "password": "pass123"})
        resp = client.post("/login", json={"username": "dev", "password": "pass123"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_form_success(self, client):
        client.post("/register", json={"username": "dev2", "password": "pass123"})
        resp = client.post("/token", data={"username": "dev2", "password": "pass123"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password(self, client):
        client.post("/register", json={"username": "dev", "password": "correct"})
        resp = client.post("/login", json={"username": "dev", "password": "wrong"})
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        resp = client.post("/login", json={"username": "ghost", "password": "123456"})
        assert resp.status_code == 401


class TestTokenRefresh:
    def test_refresh_valid_token(self, client):
        resp = client.post("/register", json={"username": "r", "password": "123456"})
        assert resp.status_code == 201
        resp = client.post("/login", json={"username": "r", "password": "123456"})
        refresh = resp.json()["refresh_token"]

        resp = client.post("/token/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_with_access_token_fails(self, client):
        resp = client.post("/register", json={"username": "r2", "password": "123456"})
        resp = client.post("/login", json={"username": "r2", "password": "123456"})
        access = resp.json()["access_token"]

        resp = client.post("/token/refresh", json={"refresh_token": access})
        assert resp.status_code == 401

    def test_refresh_bogus_token(self, client):
        resp = client.post("/token/refresh", json={"refresh_token": "not.a.real.token"})
        assert resp.status_code == 401


class TestAuthRequired:
    def test_history_without_token_returns_401(self, client):
        resp = client.get("/history")
        assert resp.status_code == 401

    def test_statistics_without_token_returns_401(self, client):
        resp = client.get("/statistics")
        assert resp.status_code == 401

    def test_chat_with_token_succeeds(self, client):
        token = register_and_login(client)
        resp = client.post(
            "/chat/send",
            json={"message": "你好"},
            headers=auth_header(token),
        )
        # 无 LLM 后端时可能 500，但不应该是 401
        assert resp.status_code != 401


class TestAdminRequired:
    def test_regular_user_cannot_list_users(self, client):
        token = register_and_login(client)
        resp = client.get("/admin/users", headers=auth_header(token))
        assert resp.status_code == 403
