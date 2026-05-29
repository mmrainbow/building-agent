from typing import Any, Dict, List, Optional, TypedDict


class InspectionState(TypedDict):
    image_path: str
    image: Optional[Any]
    material: Optional[str]
    defects: Optional[List[Dict]]
    floor: Optional[str]
    has_extension: Optional[str]
    regulations: Optional[str]
    report: Optional[str]          # 有 RAG 规范引用的报告
    report_no_rag: Optional[str]   # 无 RAG 规范引用的报告
    error: Optional[str]
