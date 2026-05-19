from typing import Any, Dict, List, Optional, TypedDict


class InspectionState(TypedDict):
    image_path: str
    image: Optional[Any]
    material: Optional[str]
    defects: Optional[List[Dict]]
    floor: Optional[str]
    has_extension: Optional[str]
    report: Optional[str]
    error: Optional[str]
