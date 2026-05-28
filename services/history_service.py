import os
import tempfile

import pandas as pd

from db import SessionLocal, get_all_records, get_record_detail, get_user_records


def load_history(user_state):
    if not user_state:
        return pd.DataFrame(), pd.DataFrame()

    db = SessionLocal()
    try:
        if user_state.get("role") == "admin":
            records = get_all_records(db, limit=50)
        else:
            records = get_user_records(db, user_state["user_id"], limit=50)
        rows = [
            {
                "ID": record.id,
                "时间": record.created_at.strftime("%Y-%m-%d %H:%M") if record.created_at else "",
                "材质": record.material or "",
                "楼层": record.floor or "",
                "加层": record.has_extension or "",
                "隐患数": len(record.defects) if record.defects else 0,
            }
            for record in records
        ]
        columns = ["ID", "时间", "材质", "楼层", "加层", "隐患数"]
        table = pd.DataFrame(rows) if rows else pd.DataFrame(columns=columns)
        return table, pd.DataFrame()
    finally:
        db.close()


def show_record_detail(history_df, evt=None):
    """Gradio 6 的 Dataframe.select 有时只传入 DataFrame，evt 由框架作为第二参数注入。"""
    if history_df is None or (hasattr(history_df, "empty") and history_df.empty):
        return "", pd.DataFrame(), None
    if evt is None or evt.index is None:
        return "", pd.DataFrame(), None

    row_index = evt.index[0] if isinstance(evt.index, tuple) else evt.index
    if row_index is None:
        return "", pd.DataFrame(), None

    record_id = int(history_df.iloc[row_index]["ID"])
    db = SessionLocal()
    try:
        record = get_record_detail(db, record_id)
        if not record:
            return "未找到记录。", pd.DataFrame(), None

        report = record.report or "无报告。"
        if record.defects:
            defect_rows = [
                {
                    "序号": index + 1,
                    "类型": defect.defect_type,
                    "面积": round(defect.area or 0, 1),
                }
                for index, defect in enumerate(record.defects)
            ]
            defects_df = pd.DataFrame(defect_rows)
        else:
            defects_df = pd.DataFrame(columns=["序号", "类型", "面积"])
        return report, defects_df, record_id
    finally:
        db.close()


def export_history_to_excel(record_id):
    if record_id is None:
        return None

    db = SessionLocal()
    try:
        record = get_record_detail(db, record_id)
        if not record:
            return None

        if record.defects:
            defects_df = pd.DataFrame(
                [
                    {
                        "序号": i + 1,
                        "隐患类型": d.defect_type,
                        "面积": round(d.area or 0, 1),
                    }
                    for i, d in enumerate(record.defects)
                ]
            )
        else:
            defects_df = pd.DataFrame(columns=["序号", "隐患类型", "面积"])

        summary_df = pd.DataFrame(
            {
                "巡检项": ["材质", "楼层", "加层"],
                "结果": [
                    record.material or "",
                    record.floor or "",
                    record.has_extension or "",
                ],
            }
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            excel_path = tmp.name
        with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
            summary_df.to_excel(writer, sheet_name="汇总", index=False)
            defects_df.to_excel(writer, sheet_name="隐患详情", index=False)
        return excel_path
    finally:
        db.close()
