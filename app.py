import json
import os
import tempfile

import cv2
import gradio as gr
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests

from agent.graph import build_agent
from db import (
    SessionLocal,
    authenticate_user,
    create_user,
    get_all_records,
    get_daily_inspection_count,
    get_defect_type_distribution,
    get_material_distribution,
    get_overall_summary,
    get_record_detail,
    get_user_records,
    init_db,
    save_inspection,
)
from db.models import User, UserRole

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:1.5b")
INIT_ADMIN_USERNAME = os.getenv("INIT_ADMIN_USERNAME", "admin")
INIT_ADMIN_PASSWORD = os.getenv("INIT_ADMIN_PASSWORD")

TEXT = {
    "title": "建筑巡检智能助手",
    "login_required": "请先登录。",
    "invalid_credentials": "用户名或密码错误。",
    "login_success": "登录成功。",
    "register_success": "注册成功，请登录。",
    "register_exists": "用户名已存在。",
    "register_empty": "用户名和密码不能为空。",
    "register_mismatch": "两次输入的密码不一致。",
    "register_short_password": "密码长度至少为 6 位。",
    "no_image": "未接收到图片。",
    "encode_failed": "图片编码失败。",
    "inspect_failed": "巡检失败",
    "no_report": "未生成报告。",
    "llm_no_context": "请先完成一次巡检，再进行问答。",
}


def bootstrap_data() -> None:
    init_db()
    db = SessionLocal()
    try:
        has_user = db.query(User).first() is not None
        if has_user:
            return
        if not INIT_ADMIN_PASSWORD:
            print(
                "未检测到用户且未设置 INIT_ADMIN_PASSWORD，"
                "已跳过默认管理员创建。"
            )
            return
        user = create_user(
            db=db,
            username=INIT_ADMIN_USERNAME,
            password=INIT_ADMIN_PASSWORD,
            role=UserRole.admin,
        )
        if user:
            print(f"已创建初始管理员账户: {INIT_ADMIN_USERNAME}")
    finally:
        db.close()


bootstrap_data()
agent = build_agent()


def draw_defects(image, defects):
    rendered = image.copy()
    for defect in defects:
        box = defect.get("box", [])
        if len(box) != 4:
            continue
        points = np.array(box, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(rendered, [points], isClosed=True, color=(0, 0, 255), thickness=2)

        label = str(defect.get("id", "?"))
        x, y = points[0][0]
        (text_w, text_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(rendered, (x, y - text_h - 4), (x + text_w, y), (255, 255, 255), -1)
        cv2.putText(rendered, label, (x, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return rendered


def do_inspect(image):
    if image is None:
        return None, TEXT["no_image"]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        success, encoded = cv2.imencode(".jpg", image)
        if not success:
            return None, TEXT["encode_failed"]
        tmp.write(encoded.tobytes())
        tmp_path = tmp.name

    try:
        result = agent.invoke({"image_path": tmp_path})
        if result.get("error"):
            return None, f"{TEXT['inspect_failed']}: {result['error']}"
        return {
            "annotated": draw_defects(image, result.get("defects", [])),
            "report": result.get("report", TEXT["no_report"]),
            "material": result.get("material", ""),
            "floor": result.get("floor", ""),
            "has_extension": result.get("has_extension", ""),
            "defects": result.get("defects", []),
        }, None
    except Exception as e:
        return None, f"{TEXT['inspect_failed']}: {e}"
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def handle_login(username, password):
    if not username or not password:
        return TEXT["register_empty"], None, gr.update(visible=True), gr.update(visible=False)

    db = SessionLocal()
    try:
        user = authenticate_user(db, username, password)
        if not user:
            return (
                TEXT["invalid_credentials"],
                None,
                gr.update(visible=True),
                gr.update(visible=False),
            )
        user_state = {
            "user_id": user.id,
            "username": user.username,
            "role": user.role.value if isinstance(user.role, UserRole) else user.role,
        }
        return (
            f"{TEXT['login_success']} 欢迎你，{user.username}。",
            user_state,
            gr.update(visible=False),
            gr.update(visible=True),
        )
    finally:
        db.close()


def handle_register(username, password, confirm_password):
    if not username or not password:
        return TEXT["register_empty"]
    if password != confirm_password:
        return TEXT["register_mismatch"]
    if len(password) < 6:
        return TEXT["register_short_password"]

    db = SessionLocal()
    try:
        user = create_user(db, username, password)
        if user:
            return TEXT["register_success"]
        return TEXT["register_exists"]
    finally:
        db.close()


def inspect_and_save(image, user_state):
    if image is None:
        return None, TEXT["no_image"], user_state
    if not user_state:
        return None, TEXT["login_required"], user_state

    result, error = do_inspect(image)
    if error:
        return None, error, user_state

    db = SessionLocal()
    try:
        save_inspection(
            db=db,
            user_id=user_state["user_id"],
            image_name=f"inspection_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}",
            material=result["material"],
            floor=result["floor"],
            has_extension=result["has_extension"],
            report=result["report"],
            defects=result["defects"],
        )
    finally:
        db.close()

    next_state = {
        **user_state,
        "last_material": result["material"],
        "last_floor": result["floor"],
        "last_has_extension": result["has_extension"],
        "last_defects": result["defects"],
        "last_report": result["report"],
    }
    return result["annotated"], result["report"], next_state


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


def show_record_detail(history_df, evt: gr.SelectData):
    if history_df is None or history_df.empty or evt is None or evt.index is None:
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
                {"序号": index + 1, "类型": defect.defect_type, "面积": round(defect.area or 0, 1)}
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
                    {"序号": i + 1, "隐患类型": d.defect_type, "面积": round(d.area or 0, 1)}
                    for i, d in enumerate(record.defects)
                ]
            )
        else:
            defects_df = pd.DataFrame(columns=["序号", "隐患类型", "面积"])

        summary_df = pd.DataFrame(
            {
                "巡检项": ["材质", "楼层", "加层"],
                "结果": [record.material or "", record.floor or "", record.has_extension or ""],
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


def load_statistics(user_state):
    if not user_state:
        return go.Figure(), go.Figure(), go.Figure(), TEXT["login_required"]

    db = SessionLocal()
    try:
        user_id = user_state["user_id"]
        role = user_state.get("role", "inspector")
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


def chat_with_llm(message, history, user_state):
    if not user_state or not user_state.get("last_report"):
        return TEXT["llm_no_context"]

    report_content = str(user_state["last_report"])
    system_prompt = (
        "你是建筑巡检助手，只能基于最新一次巡检报告回答问题。"
        "若问题与报告无关，请礼貌说明范围限制。\n\n"
        f"最新报告：\n{report_content}"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for turn in history or []:
        if isinstance(turn, dict):
            role = turn.get("role")
            content = turn.get("content")
            if role and content is not None:
                if isinstance(content, (list, dict)):
                    content = json.dumps(content, ensure_ascii=False)
                messages.append({"role": role, "content": str(content)})
        elif isinstance(turn, (list, tuple)) and len(turn) == 2:
            messages.append({"role": "user", "content": str(turn[0])})
            messages.append({"role": "assistant", "content": str(turn[1])})

    messages.append({"role": "user", "content": str(message)})
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.7},
            },
            timeout=60,
        )
        if response.status_code == 200:
            return response.json().get("message", {}).get("content", "")
        return f"模型请求失败：HTTP {response.status_code}"
    except Exception as e:
        return f"模型请求失败：{e}"


with gr.Blocks(title=TEXT["title"]) as demo:
    session_state = gr.State(value=None)

    with gr.Column() as login_block:
        gr.Markdown(f"# {TEXT['title']} - 登录")
        with gr.Row():
            with gr.Column(scale=1):
                login_user = gr.Textbox(label="用户名")
                login_pass = gr.Textbox(label="密码", type="password")
                login_btn = gr.Button("登录", variant="primary")
                login_msg = gr.Markdown("")
            with gr.Column(scale=1):
                reg_user = gr.Textbox(label="注册用户名")
                reg_pass = gr.Textbox(label="注册密码", type="password")
                reg_pass2 = gr.Textbox(label="确认密码", type="password")
                reg_btn = gr.Button("注册")
                reg_msg = gr.Markdown("")

    with gr.Column(visible=False) as main_block:
        gr.Markdown(f"# {TEXT['title']}")
        logout_btn = gr.Button("退出登录")

        with gr.Tabs():
            with gr.TabItem("图像巡检"):
                with gr.Row():
                    with gr.Column():
                        image_input = gr.Image(type="numpy", label="上传建筑图片")
                        detect_btn = gr.Button("开始巡检", variant="primary")
                    with gr.Column():
                        report_output = gr.Textbox(label="巡检报告", lines=15)
                        annotated_output = gr.Image(label="隐患标注图", type="numpy")

                detect_btn.click(
                    fn=inspect_and_save,
                    inputs=[image_input, session_state],
                    outputs=[annotated_output, report_output, session_state],
                )

            with gr.TabItem("历史记录"):
                refresh_btn = gr.Button("刷新")
                history_table = gr.Dataframe(
                    label="巡检记录",
                    interactive=False,
                    headers=["ID", "时间", "材质", "楼层", "加层", "隐患数"],
                )
                with gr.Row():
                    with gr.Column():
                        history_report = gr.Textbox(label="报告详情", lines=12)
                    with gr.Column():
                        history_defects = gr.Dataframe(
                            label="隐患详情",
                            interactive=False,
                            headers=["序号", "类型", "面积"],
                        )
                history_export_btn = gr.Button("导出当前记录为 Excel")
                history_export_file = gr.File(label="下载 Excel")
                history_record_id = gr.State(value=None)

                refresh_btn.click(
                    fn=load_history,
                    inputs=[session_state],
                    outputs=[history_table, history_defects],
                )
                history_table.select(
                    fn=show_record_detail,
                    inputs=[history_table],
                    outputs=[history_report, history_defects, history_record_id],
                )
                history_export_btn.click(
                    fn=export_history_to_excel,
                    inputs=[history_record_id],
                    outputs=[history_export_file],
                )

            with gr.TabItem("统计分析"):
                stats_btn = gr.Button("刷新统计")
                stats_summary = gr.Markdown("")
                with gr.Row():
                    stats_pie = gr.Plot(label="隐患类型分布")
                    stats_bar = gr.Plot(label="材质分布")
                stats_line = gr.Plot(label="近30天巡检趋势")

                stats_btn.click(
                    fn=load_statistics,
                    inputs=[session_state],
                    outputs=[stats_pie, stats_bar, stats_line, stats_summary],
                )

            with gr.TabItem("智能问答"):
                gr.Markdown("基于最新巡检报告进行问答。")
                chatbot = gr.Chatbot(label="对话记录")
                msg = gr.Textbox(label="问题", placeholder="例如：这个裂缝是否严重？")
                clear = gr.Button("清空")

                def respond(message, chat_history, sess):
                    if not message.strip():
                        return "", chat_history, sess
                    bot_message = chat_with_llm(message, chat_history, sess)
                    chat_history.append({"role": "user", "content": message})
                    chat_history.append({"role": "assistant", "content": bot_message})
                    return "", chat_history, sess

                msg.submit(respond, [msg, chatbot, session_state], [msg, chatbot, session_state])
                clear.click(lambda: [], None, chatbot, queue=False)

    login_btn.click(
        fn=handle_login,
        inputs=[login_user, login_pass],
        outputs=[login_msg, session_state, login_block, main_block],
    )
    reg_btn.click(
        fn=handle_register,
        inputs=[reg_user, reg_pass, reg_pass2],
        outputs=[reg_msg],
    )

    def do_logout():
        return None, gr.update(visible=True), gr.update(visible=False)

    logout_btn.click(
        fn=do_logout,
        inputs=[],
        outputs=[session_state, login_block, main_block],
    )


if __name__ == "__main__":
    demo.launch(share=False)
