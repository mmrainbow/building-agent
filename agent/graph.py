from langgraph.graph import StateGraph, END
from .state import InspectionState
from .nodes import (
    load_image_node,
    material_node,
    floor_node,
    extension_node,
    defect_node,
    rag_node,
    report_node,
)


def build_agent():
    workflow = StateGraph(InspectionState)

    workflow.add_node("load_image", load_image_node)
    workflow.add_node("material", material_node)
    workflow.add_node("floor", floor_node)
    workflow.add_node("extension", extension_node)
    workflow.add_node("defect", defect_node)
    workflow.add_node("rag", rag_node)
    workflow.add_node("report", report_node)

    # 先加载图像，再并行执行 4 个独立检测
    workflow.set_entry_point("load_image")
    workflow.add_edge("load_image", "material")
    workflow.add_edge("load_image", "floor")
    workflow.add_edge("load_image", "extension")
    workflow.add_edge("load_image", "defect")

    # 所有检测完成后先做 RAG 检索，再汇总到报告节点
    workflow.add_edge("material", "rag")
    workflow.add_edge("floor", "rag")
    workflow.add_edge("extension", "rag")
    workflow.add_edge("defect", "rag")
    workflow.add_edge("rag", "report")
    workflow.add_edge("report", END)

    return workflow.compile()
