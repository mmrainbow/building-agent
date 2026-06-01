import plotly.express as px
import plotly.graph_objects as go

from db import (
    SessionLocal,
    get_daily_inspection_count,
    get_defect_type_distribution,
    get_material_distribution,
    get_overall_summary,
)

from .constants import TEXT


def load_statistics(user_state):
    if not user_state:
        return go.Figure(), go.Figure(), go.Figure(), TEXT["login_required"]

    db = SessionLocal()
    try:
        user_id = user_state["user_id"]
        role = user_state.get("role", "user")
        query_user_id = None if role == "admin" else user_id

        summary = get_overall_summary(db, query_user_id)
        defects = get_defect_type_distribution(db, query_user_id)
        materials = get_material_distribution(db, query_user_id)
        daily = get_daily_inspection_count(db, 30)

        pie = (
            px.pie(
                names=[item["type"] for item in defects],
                values=[item["count"] for item in defects],
                title="隐患类型分布",
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            if defects
            else go.Figure()
        )
        bar = (
            px.bar(
                x=[item["material"] for item in materials],
                y=[item["count"] for item in materials],
                title="材质分布",
                labels={"x": "材质", "y": "数量"},
            )
            if materials
            else go.Figure()
        )
        line = (
            px.line(
                x=[item["date"] for item in daily],
                y=[item["count"] for item in daily],
                title="近30天巡检趋势",
                labels={"x": "日期", "y": "数量"},
                markers=True,
            )
            if daily
            else go.Figure()
        )

        summary_text = (
            f"巡检总数：{summary['total_inspections']} | "
            f"隐患总数：{summary['total_defects']} | "
            f"加层数量：{summary['extension_count']}（{summary['extension_rate']}%）"
        )
        return pie, bar, line, summary_text
    finally:
        db.close()
