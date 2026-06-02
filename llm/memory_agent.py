"""Memory Agent — 使用独立的廉价 API 模型做记忆提取，不占用 Manager 的额度。"""

import os

from llm.client import LLMClient


def get_memory_agent() -> LLMClient:
    """创建 Memory Agent 专用 LLMClient。

    使用 MEMORY_LLM_MODEL 指定模型（默认 qwen-turbo），
    记忆提取不需要 tools，纯文本任务即可完成。
    """
    model = os.getenv("MEMORY_LLM_MODEL", "qwen-turbo")
    return LLMClient(model=model)
