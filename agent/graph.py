from langgraph.graph import StateGraph, END
from .state import InspectionState
from .nodes import load_image_node, material_node, floor_node, extension_node, defect_node, report_node


def build_agent():
    workflow = StateGraph(InspectionState)

    workflow.add_node("load_image", load_image_node)
    workflow.add_node("material", material_node)
    workflow.add_node("floor", floor_node)
    workflow.add_node("extension", extension_node)
    workflow.add_node("defect", defect_node)
    workflow.add_node("report", report_node)

    # 先加载图像，再并行执行 4 个独立检测
    workflow.set_entry_point("load_image")
    workflow.add_edge("load_image", "material")
    workflow.add_edge("load_image", "floor")
    workflow.add_edge("load_image", "extension")
    workflow.add_edge("load_image", "defect")

    # 所有检测完成后汇总到报告节点
    workflow.add_edge("material", "report")
    workflow.add_edge("floor", "report")
    workflow.add_edge("extension", "report")
    workflow.add_edge("defect", "report")
    workflow.add_edge("report", END)

    return workflow.compile()
