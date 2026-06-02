"""Chat API 集成测试 — 验证 ReAct Agent 智能 Tool 调用。"""
import io
from unittest.mock import patch

import pytest

from .conftest import auth_header, register_and_login


def _fake_run(user_id, conversation_id, message, db, image=None, **kwargs):
    """模拟 agent.run() — 持久化消息到真实 DB，返回固定响应。"""
    from db.chat_crud import add_message

    add_message(db, conversation_id, "user", message)
    tool_log = [
        {"name": "classify_material", "arguments": {}, "result": "Face Brick", "elapsed_ms": 150},
    ]
    add_message(
        db,
        conversation_id,
        "assistant",
        "这是模拟的巡检报告。建筑状况良好。",
        metadata={"tool_calls": tool_log},
    )
    return {
        "response": "这是模拟的巡检报告。建筑状况良好。",
        "tool_log": tool_log,
        "rounds": 1,
        "usage": {"total_tokens": 300},
    }


class _MockAgent:
    """模拟 InspectionAgent — 持久化消息到真实 DB。"""
    tools = {}

    def run(self, **kwargs):
        return _fake_run(**kwargs)


@pytest.fixture(autouse=True)
def mock_agent():
    with patch("llm.agent_factory._agent", _MockAgent()):
        yield


class TestChatSend:
    def test_chat_send_text_only(self, client):
        token = register_and_login(client, "chatter", "pass123")
        resp = client.post(
            "/chat/send?message=你好，请介绍一下你自己",
            headers=auth_header(token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["conversation_id"] > 0
        assert "巡检报告" in data["response"]

    def test_chat_conversation_list_and_detail(self, client):
        token = register_and_login(client, "lister", "pass123")

        resp = client.post("/chat/send?message=你好", headers=auth_header(token))
        assert resp.status_code == 200
        conv_id = resp.json()["conversation_id"]

        resp = client.get("/chat/conversations", headers=auth_header(token))
        assert resp.status_code == 200
        assert any(c["id"] == conv_id for c in resp.json())

        resp = client.get(f"/chat/conversations/{conv_id}", headers=auth_header(token))
        assert resp.status_code == 200
        assert len(resp.json()["messages"]) == 2  # user + assistant

    def test_chat_continue_conversation(self, client):
        token = register_and_login(client, "continuer", "pass123")

        resp = client.post("/chat/send?message=第一条", headers=auth_header(token))
        conv_id = resp.json()["conversation_id"]

        resp = client.post(
            f"/chat/send?message=第二条&conversation_id={conv_id}",
            headers=auth_header(token),
        )
        assert resp.status_code == 200
        assert resp.json()["conversation_id"] == conv_id

        resp = client.get(f"/chat/conversations/{conv_id}", headers=auth_header(token))
        assert len(resp.json()["messages"]) == 4

    def test_chat_delete(self, client):
        token = register_and_login(client, "deleter", "pass123")

        resp = client.post("/chat/send?message=待删除", headers=auth_header(token))
        conv_id = resp.json()["conversation_id"]

        resp = client.delete(f"/chat/conversations/{conv_id}", headers=auth_header(token))
        assert resp.status_code == 204

        resp = client.get(f"/chat/conversations/{conv_id}", headers=auth_header(token))
        assert resp.status_code == 404

    def test_chat_permission_isolation(self, client):
        token_a = register_and_login(client, "user_a", "pass_a")
        token_b = register_and_login(client, "user_b", "pass_b")

        resp = client.post("/chat/send?message=A的对话", headers=auth_header(token_a))
        conv_a = resp.json()["conversation_id"]

        resp = client.get(f"/chat/conversations/{conv_a}", headers=auth_header(token_b))
        assert resp.status_code == 403

    def test_chat_without_auth(self, client):
        resp = client.post("/chat/send?message=hi")
        assert resp.status_code == 401

    def test_chat_with_image(self, client):
        token = register_and_login(client, "imguser", "pass123")

        # 生成一个 1x1 黑色 JPEG（cv2 可正确解码）
        import cv2
        import numpy as np

        img_arr = np.zeros((1, 1, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".jpg", img_arr)
        img = io.BytesIO(buf.tobytes())

        resp = client.post(
            "/chat/send?message=这栋楼有什么隐患？",
            files={"image": ("building.jpg", img, "image/jpeg")},
            headers=auth_header(token),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "tool_log" in data
        assert "response" in data
