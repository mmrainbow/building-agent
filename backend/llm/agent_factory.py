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
    REPORT_AGENT_URL          Report Agent 地址 (默认 http://localhost:8000)
"""

import os

from agent.orchestrator import ManagerAgent
from llm.client import LLMClient
from llm.tools import build_tools

_agent: ManagerAgent | None = None


def _is_local_llm_enabled() -> bool:
    val = os.getenv("USE_LOCAL_LLM", "false").lower()
    return val in ("true", "1", "yes", "on")


def _create_llm_client() -> LLMClient:
    if _is_local_llm_enabled():
        api_key = os.getenv("LLM_API_KEY", "not-needed")
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:8000/v1")
        model = os.getenv("LLM_MODEL", "qwen2.5-vl-building")
        print(f"[AgentFactory] Manager: 本地模型 {base_url}")
        return LLMClient(api_key=api_key, base_url=base_url, model=model)
    else:
        print(f"[AgentFactory] Manager: 远程 API (Report Agent @ {os.getenv('REPORT_AGENT_URL', 'http://localhost:8000')})")
        return LLMClient()


def reset_agent() -> None:
    global _agent
    _agent = None


def get_chat_agent() -> ManagerAgent:
    global _agent
    if _agent is None:
        _agent = ManagerAgent(_create_llm_client())
        _agent.tools = build_tools()
    return _agent
