"""Tools 包 — Agent 可用的所有 Tool 及其管理函数。

用法:
    from llm.tools import build_tools, execute_tool, get_tool_schemas
    tools = build_tools()
    schemas = get_tool_schemas(tools)
    result = execute_tool(tools, "classify_material", images=images)
"""

from pathlib import Path
from typing import Any

# ── 构建工厂 ──────────────────────────────────────────────

from .base import (
    CVToolWrapper,
    DefectToolWrapper,
    MaterialToolWrapper,
    MODEL_DIR,
    _make_defect_predictor,
    _make_extension_predictor,
    _make_floor_predictor,
    _make_material_predictor,
)
from .knowledge import KnowledgeSearchTool
from .report import ReportAgentTool
from .schemas import (
    DEFECT_SCHEMA,
    EXTENSION_SCHEMA,
    FLOOR_SCHEMA,
    MATERIAL_SCHEMA,
)


def build_tools(model_dir: str | None = None) -> dict[str, Any]:
    """构建所有可用 Tool，返回 {tool_name: tool_instance}。

    CV Predictor 使用延迟加载，仅在首次被 LLM 调用时初始化。
    """
    if model_dir is None:
        model_dir = str(MODEL_DIR)

    return {
        "classify_material": MaterialToolWrapper(
            schema=MATERIAL_SCHEMA,
            predictor_factory=lambda: _make_material_predictor(model_dir),
        ),
        "estimate_floors": CVToolWrapper(
            schema=FLOOR_SCHEMA,
            predictor_factory=lambda: _make_floor_predictor(model_dir),
        ),
        "detect_extension": CVToolWrapper(
            schema=EXTENSION_SCHEMA,
            predictor_factory=lambda: _make_extension_predictor(model_dir),
        ),
        "detect_defects": DefectToolWrapper(
            schema=DEFECT_SCHEMA,
            predictor_factory=lambda: _make_defect_predictor(model_dir),
        ),
        "search_knowledge": KnowledgeSearchTool(),
        "generate_report": ReportAgentTool(),
    }


def get_tool_schemas(tools: dict) -> list[dict]:
    """提取所有 Tool 的 OpenAI schema，传给 LLM chat() 的 tools 参数。"""
    return [t.schema for t in tools.values()]


def execute_tool(tools: dict, name: str, images=None, db=None, chat_image_ids=None, **kwargs) -> str:
    """根据名称执行 Tool，返回结果字符串。

    Args:
        tools: build_tools() 返回的 tool 字典
        name: tool 名称
        images: numpy 图像列表 (多图)
        db: SQLAlchemy Session
        chat_image_ids: 每张图片的 ChatImage ID 列表
        **kwargs: 传递给 tool.execute() 的额外参数（含 LLM 传的 image_indices 等）
    """
    if name not in tools:
        return f"未知工具 '{name}'，可用: {', '.join(tools.keys())}"
    tool = tools[name]
    return tool.execute(images=images, db=db, chat_image_ids=chat_image_ids, **kwargs)


def format_tool_result_for_llm(tool_name: str, result: str) -> str:
    """将 Tool 执行结果包装为 LLM 可读的消息内容。"""
    return result
