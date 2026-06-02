"""共享 Agent 单例 — api/chat.py 和 services/chat_service.py 共用。"""

from agent.orchestrator import InspectionAgent
from llm.client import LLMClient
from llm.tools import build_tools

_agent: InspectionAgent | None = None


def get_chat_agent() -> InspectionAgent:
    global _agent
    if _agent is None:
        _agent = InspectionAgent(LLMClient())
        _agent.tools = build_tools()
    return _agent
