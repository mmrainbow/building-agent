"""向后兼容重导出 — 已拆分到 crud_user.py 和 crud_inspection.py。"""

from .crud_user import authenticate_user, create_user, get_user_by_id
from .crud_inspection import get_all_records, get_record_detail, get_user_records, save_inspection

# 重新导出，保持外部 import 路径不变
__all__ = [
    "create_user",
    "authenticate_user",
    "get_user_by_id",
    "save_inspection",
    "get_user_records",
    "get_all_records",
    "get_record_detail",
]
