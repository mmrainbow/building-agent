"""LLM 客户端 — OpenAI 兼容 Chat Completions。"""

import os
from typing import Any

import requests

LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("EMBEDDING_API_KEY", ""))
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")


class LLMClient:
    """OpenAI 兼容 Chat Completions 客户端（原生 function calling）。"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key or LLM_API_KEY
        self.base_url = (base_url or LLM_BASE_URL).rstrip("/")
        self.model = model or LLM_MODEL

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             temperature: float = 0.7, max_tokens: int = 2000) -> dict:
        url = f"{self.base_url}/chat/completions"
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=body, timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]

        return {
            "content": msg.get("content"),
            "tool_calls": msg.get("tool_calls"),
            "finish_reason": choice.get("finish_reason"),
            "usage": data.get("usage", {}),
            "model": data.get("model"),
        }
