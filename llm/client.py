"""通义千问 API 客户端 — OpenAI 兼容格式，支持 function calling。

环境变量:
    EMBEDDING_API_KEY  通义千问 API 密钥（LLM + Embedding 共用）
    LLM_MODEL          模型名称，默认 qwen-plus
    LLM_BASE_URL       API 地址，默认 DashScope 兼容端点
"""

import json
import os
from typing import Any

import requests

LLM_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)


class LLMClient:
    """通义千问 Chat Completions 客户端。

    用法:
        client = LLMClient()
        resp = client.chat(
            messages=[{"role": "user", "content": "你好"}],
            tools=[...],  # OpenAI function call schema
        )
        if resp["tool_calls"]:
            ...  # 执行工具，结果回传给 LLM
        else:
            print(resp["content"])
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or LLM_API_KEY
        self.base_url = (base_url or LLM_BASE_URL).rstrip("/")
        self.model = model or LLM_MODEL

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict:
        """发送 chat completion 请求，返回统一格式。

        Returns:
            {
                "content": str | None,        # LLM 文本回复
                "tool_calls": list[dict] | None,  # 格式: [{id, function:{name, arguments}}]
                "finish_reason": str,
                "usage": {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int},
                "model": str,
            }
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        resp = requests.post(url, headers=headers, json=body, timeout=120)
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

    def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        tool_executor: callable,
        max_rounds: int = 10,
    ) -> list[dict]:
        """ReAct 循环: 自动执行 tool_calls 直到 LLM 生成最终文本回复。

        tool_executor(name, arguments) -> str  # 返回工具执行结果文本

        Returns:
            [
                {"role": "assistant", "content": None, "tool_calls": [...]},
                {"role": "tool", "tool_call_id": "...", "content": "结果"},
                {"role": "assistant", "content": "最终文本回复"},
            ]
        """
        response_messages = []

        for _ in range(max_rounds):
            resp = self.chat(messages, tools=tools)
            response_messages.append(resp)

            if resp["tool_calls"]:
                # 添加 assistant 消息（含 tool_calls）
                messages.append({
                    "role": "assistant",
                    "content": resp["content"],
                    "tool_calls": resp["tool_calls"],
                })
                # 执行每个 tool_call 并添加 tool 消息
                for tc in resp["tool_calls"]:
                    fn_name = tc["function"]["name"]
                    fn_args = json.loads(tc["function"]["arguments"])
                    result = tool_executor(fn_name, **fn_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result, ensure_ascii=False),
                    })
            else:
                # 没有 tool_calls → LLM 生成最终回答
                return response_messages

        # 达到最大轮数仍未结束
        return response_messages
