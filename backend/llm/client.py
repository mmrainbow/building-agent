"""LLM 客户端 — OpenAI 兼容格式，支持 function calling + prompt 回退。

支持两种 tool calling 模式:
    native:  原生 function calling (DashScope / vLLM 新版)
    prompt:  ReAct 文本解析 (vLLM 旧版 / 不支持 tool calling 的模型)

环境变量:
    LLM_API_KEY            API 密钥
    LLM_MODEL              模型名称，默认 qwen-plus
    LLM_BASE_URL           API 地址，默认 DashScope 兼容端点
    LLM_TOOL_CALL_MODE     工具调用模式: "native" (默认) 或 "prompt" (文本解析回退)
"""

import os
from typing import Any

import requests

from llm.react_parser import (
    build_tool_prompt,
    parse_tool_calls,
    strip_tool_calls,
)

LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("EMBEDDING_API_KEY", ""))
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-plus")
LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
LLM_TOOL_CALL_MODE = os.getenv("LLM_TOOL_CALL_MODE", "prompt").lower()


class LLMClient:
    """OpenAI 兼容 Chat Completions 客户端。

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

    tool_call_mode:
        "native" (默认): 直接传 OpenAI tools 参数，依赖 API 原生 function calling
        "prompt" (回退): 将 tools 注入 system prompt，解析模型输出中的 <tool_call> 标记
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        tool_call_mode: str | None = None,
    ):
        self.api_key = api_key or LLM_API_KEY
        self.base_url = (base_url or LLM_BASE_URL).rstrip("/")
        self.model = model or LLM_MODEL
        self.tool_call_mode = (tool_call_mode or LLM_TOOL_CALL_MODE)

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> dict:
        """发送 chat completion 请求，返回统一格式。

        当 tool_call_mode="prompt" 且传入了 tools 参数时:
            - 将 tool schemas 注入 system prompt (或追加第一个 user 消息之前)
            - 去掉 API 请求中的 tools 参数
            - 从响应文本中解析 <tool_call> 标记

        Returns:
            {
                "content": str | None,
                "tool_calls": list[dict] | None,
                "finish_reason": str,
                "usage": {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int},
                "model": str,
            }
        """
        if tools and self.tool_call_mode == "prompt":
            return self._chat_with_prompt_tools(
                messages, tools, temperature, max_tokens
            )
        return self._chat_native(messages, tools, temperature, max_tokens)

    def _chat_native(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """原生 function calling 模式 — 直接传 tools 参数给 API。"""
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

    def _chat_with_prompt_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """Prompt 回退模式 — 将 tools 以文本注入，解析模型输出。"""
        tool_prompt = build_tool_prompt(tools)

        # 在 system prompt 后、对话历史之前插入工具 prompt
        modified_messages = []
        for msg in messages:
            modified_messages.append(dict(msg))
            if msg.get("role") == "system":
                # 追加工具描述到 system prompt
                modified_messages[-1]["content"] = (
                    f"{msg['content']}\n\n{tool_prompt}"
                )

        # 如果没有任何 system 消息 (不应该发生)，插入一个
        if not any(m["role"] == "system" for m in modified_messages):
            modified_messages.insert(0, {
                "role": "system",
                "content": tool_prompt,
            })

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "messages": modified_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # 注意: 不传 tools 参数

        resp = requests.post(url, headers=headers, json=body, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        msg = choice["message"]
        raw_content = msg.get("content") or ""

        # 解析 <tool_call> 标记
        parsed_tool_calls = parse_tool_calls(raw_content)
        clean_content = strip_tool_calls(raw_content) if parsed_tool_calls else raw_content

        return {
            "content": clean_content or None,
            "tool_calls": parsed_tool_calls if parsed_tool_calls else None,
            "finish_reason": "tool_calls" if parsed_tool_calls else choice.get("finish_reason"),
            "usage": data.get("usage", {}),
            "model": data.get("model"),
        }

