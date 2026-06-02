"""共享 Agent 单例 — Manager Agent (通义千问 API 推理 + 工具调度)。

多 Agent 架构:
    Manager Agent (本模块)  — 通义千问 API, 负责任务理解 + 工具选择 + 结果解读
    Report Agent (独立进程) — 本地微调 Qwen2.5-VL, 负责专业报告生成
                            启动: python scripts/launch_local_llm.py
                            调用: Manager 通过 generate_report 工具访问

环境变量:
    USE_LOCAL_LLM=false       Manager 使用远程 API (默认)
    LLM_API_KEY               DashScope API 密钥
    LLM_MODEL                 Manager 模型 (默认 qwen3.6-flash)
    LLM_TOOL_CALL_MODE        Manager 工具调用: native (默认)
    REPORT_AGENT_URL          Report Agent 地址 (默认 http://localhost:8000)
"""

import os

from agent.orchestrator import InspectionAgent
from llm.client import LLMClient
from llm.tools import build_tools

_agent: InspectionAgent | None = None


def _is_local_llm_enabled() -> bool:
    """检查是否启用本地 LLM 作为 Manager。默认 false (使用远程 API)。"""
    val = os.getenv("USE_LOCAL_LLM", "false").lower()
    return val in ("true", "1", "yes", "on")


def _create_llm_client() -> LLMClient:
    """创建 Manager Agent 的 LLMClient。"""
    if _is_local_llm_enabled():
        # 单 Agent 模式: 本地模型同时做推理和报告 (不推荐)
        api_key = os.getenv("LLM_API_KEY", "not-needed")
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
        model = os.getenv("LLM_MODEL", "qwen2.5-vl-building")
        mode = os.getenv("LLM_TOOL_CALL_MODE", "prompt")
        print(f"[AgentFactory] Manager: 本地模型 {base_url} tool_mode={mode}")
        return LLMClient(api_key=api_key, base_url=base_url, model=model, tool_call_mode=mode)
    else:
        # 多 Agent 模式: Manager 使用远程 API + Report Agent 处理报告
        print(f"[AgentFactory] Manager: 远程 API (Report Agent @ {os.getenv('REPORT_AGENT_URL', 'http://localhost:8000')})")
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
