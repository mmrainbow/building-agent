import json
import os

import requests

from .constants import TEXT

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:1.5b")


def chat_with_llm(message, history, user_state):
    if not user_state or not user_state.get("last_report"):
        return TEXT["llm_no_context"]

    report_content = str(user_state["last_report"])
    system_prompt = (
        "你是建筑巡检助手，只能基于最新一次巡检报告回答问题。"
        "若问题与报告无关，请礼貌说明范围限制。\n\n"
        f"最新报告：\n{report_content}"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for turn in history or []:
        if isinstance(turn, dict):
            role = turn.get("role")
            content = turn.get("content")
            if role and content is not None:
                if isinstance(content, (list, dict)):
                    content = json.dumps(content, ensure_ascii=False)
                messages.append({"role": role, "content": str(content)})
        elif isinstance(turn, (list, tuple)) and len(turn) == 2:
            messages.append({"role": "user", "content": str(turn[0])})
            messages.append({"role": "assistant", "content": str(turn[1])})

    messages.append({"role": "user", "content": str(message)})
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.7},
            },
            timeout=60,
        )
        if response.status_code == 200:
            return response.json().get("message", {}).get("content", "")
        return f"模型请求失败：HTTP {response.status_code}"
    except Exception as e:
        return f"模型请求失败：{e}"
