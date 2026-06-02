"""共享 Agent 单例 — api/chat.py 和 services/chat_service.py 共用。

默认使用本地 vLLM 微调 Qwen2.5-VL 模型 (模式 2)。
如需切回远程 DashScope API，设置 USE_LOCAL_LLM=false。

环境变量:
    USE_LOCAL_LLM=true        默认启用本地 vLLM
    LLM_BASE_URL              本地 vLLM 地址 (默认 http://localhost:8000/v1)
    LLM_MODEL                 模型名 (默认 qwen2.5-vl-building)
    LLM_TOOL_CALL_MODE        工具调用模式: prompt (默认) 或 native

切换方式:
    # 本地 vLLM (默认，无需设置)
    python scripts/launch_vllm.py    # 先启动 vLLM
    python app.py                    # 启动应用

    # 切回远程 DashScope API
    set USE_LOCAL_LLM=false
    set LLM_API_KEY=sk-xxx
    set LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
    set LLM_MODEL=qwen3.6-flash-2026-04-16
"""

import os

from agent.orchestrator import InspectionAgent
from llm.client import LLMClient, LLM_TOOL_CALL_MODE
from llm.tools import build_tools

_agent: InspectionAgent | None = None

# 本地 vLLM 默认配置
_LOCAL_VLLM_BASE_URL = "http://localhost:8000/v1"
_LOCAL_VLLM_MODEL = "qwen2.5-vl-building"


def _is_local_llm_enabled() -> bool:
    """检查是否启用本地 LLM (vLLM 服务)。默认启用。"""
    val = os.getenv("USE_LOCAL_LLM", "true").lower()
    return val in ("true", "1", "yes", "on")


def _create_llm_client() -> LLMClient:
    """根据环境变量创建 LLMClient 实例。"""
    if _is_local_llm_enabled():
        api_key = os.getenv("LLM_API_KEY", "not-needed")
        base_url = os.getenv("LLM_BASE_URL", _LOCAL_VLLM_BASE_URL)
        model = os.getenv("LLM_MODEL", _LOCAL_VLLM_MODEL)
        mode = os.getenv("LLM_TOOL_CALL_MODE", "prompt")   # 本地 vLLM 默认 prompt
        print(f"[AgentFactory] 本地 LLM 模式: {base_url} 模型: {model} tool_mode: {mode}")
        return LLMClient(api_key=api_key, base_url=base_url, model=model, tool_call_mode=mode)
    else:
        # 远程 API 始终使用 native function calling
        return LLMClient(tool_call_mode="native")


def reset_agent() -> None:
    """重置 Agent 单例 (切换 LLM 后端后调用)。"""
    global _agent
    _agent = None


def get_chat_agent() -> InspectionAgent:
    """获取共享的 InspectionAgent 单例。"""
    global _agent
    if _agent is None:
        _agent = InspectionAgent(_create_llm_client())
        _agent.tools = build_tools()
    return _agent
