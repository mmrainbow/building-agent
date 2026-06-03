import sys
from pathlib import Path

# 确保 backend/ 在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

# 必须在 import services/db 之前加载，否则 INSPECTION_DB_URL 等已在 import 时固化
load_dotenv(Path(__file__).resolve().parent / ".env")

import gradio as gr

from services import (
    TEXT,
    bootstrap_data,
    chat_with_llm_stream,
    delete_user_conversation,
    list_user_conversations,
    load_conversation_messages,
    reset_chat_session,
    do_logout,
    export_history_to_excel,
    handle_login,
    handle_register,
    load_history,
    show_record_detail,
)

bootstrap_data()


# ── Agent 监控面板工具函数 ────────────────────────────────

def _token_ring_html(current: int, threshold: int) -> str:
    pct = min(round(current / threshold * 100) if threshold > 0 else 0, 100)
    color = "#22c55e" if pct < 50 else ("#f59e0b" if pct < 80 else "#ef4444")
    return f"""
    <div style="text-align:center">
    <svg width="100" height="100" viewBox="0 0 36 36">
      <circle cx="18" cy="18" r="15.5" fill="none" stroke="#333" stroke-width="3"/>
      <circle cx="18" cy="18" r="15.5" fill="none" stroke="{color}" stroke-width="3"
        stroke-dasharray="{pct} {100-pct}" stroke-dashoffset="25" stroke-linecap="round"
        transform="rotate(-90 18 18)"/>
      <text x="18" y="16" text-anchor="middle" fill="white" font-size="7" font-weight="bold">{pct}%</text>
      <text x="18" y="23" text-anchor="middle" fill="#888" font-size="4">{current}/{threshold}</text>
    </svg></div>"""


def _agent_status_html(name: str, model: str, status: str, color: str) -> str:
    return f"""
    <div style="background:#1e1e1e;border:1px solid #333;border-radius:8px;padding:12px;text-align:center">
      <div style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{color};margin-right:6px"></div>
      <span style="font-weight:bold;color:white">{name}</span>
      <div style="color:#888;font-size:12px">{model}</div>
      <div style="margin-top:4px;font-size:13px;color:{color}">{status}</div>
    </div>"""


# ── UI 适配层（services 返回纯数据，此处转 gr.update）─────────

def _login_wrapper(username, password):
    msg, state, show_login, show_main = handle_login(username, password)
    return msg, state, gr.update(visible=show_login), gr.update(visible=show_main)


def _logout_wrapper():
    state, show_login, show_main = do_logout()
    return state, gr.update(visible=show_login), gr.update(visible=show_main)


# ── 智能问答回调 ───────────────────────────────────────────

def respond_stream(message, chat_history, chat_image, sess):
    """流式响应 — 实时展示 Manager Agent 的思考过程。"""
    if not message.strip():
        yield "", chat_history, chat_image, sess
        return
    if chat_image is not None:
        sess["last_image"] = chat_image
    chat_history.append({"role": "user", "content": message})
    # 先显示"思考中"占位
    chat_history.append({"role": "assistant", "content": "🧠 **Manager Agent 思考中...**"})
    yield "", chat_history, None, sess
    # 调用 Agent（阻塞），但返回的已包含 CoT HTML
    bot_message = chat_with_llm_stream(message, chat_history, sess, image=chat_image)
    chat_history[-1] = {"role": "assistant", "content": bot_message}
    yield "", chat_history, None, sess


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
                gr.Markdown("对同一建筑上传至少 **3 张**不同角度的照片，点击开始巡检。")
                with gr.Row():
                    with gr.Column(scale=1):
                        image_input = gr.Image(type="numpy", label="上传图片")
                        with gr.Row():
                            add_btn = gr.Button("添加到列表", size="sm")
                            clear_btn = gr.Button("清空", size="sm")
                        status_md = gr.Markdown("📸 已收集 0 张 | 至少需要 3 张")
                        inspect_btn = gr.Button("开始巡检", variant="primary")

                    with gr.Column(scale=2):
                        gallery = gr.Gallery(label="已收集的图片", columns=3, height=300)
                        report_output = gr.HTML(label="巡检报告")

                images_state = gr.State(value=[])

                with gr.Row():
                    annotated_gallery = gr.Gallery(
                        label="缺陷标注", columns=3, height=300, visible=False
                    )

                def _add_image(img, imgs):
                    if img is None:
                        return imgs, imgs, f"📸 已收集 {len(imgs)} 张 | 至少需要 3 张"
                    imgs = imgs + [img]
                    return imgs, imgs, f"📸 已收集 {len(imgs)} 张 | 至少需要 {'3' if len(imgs) < 3 else '3，可以开始巡检'} ✅"

                add_btn.click(_add_image, [image_input, images_state], [images_state, gallery, status_md])

                clear_btn.click(lambda: ([], [], "📸 已收集 0 张 | 至少需要 3 张"), None, [images_state, gallery, status_md], queue=False)

                def _run_inspection(imgs, sess):
                    if not sess:
                        return "请先登录。", [], gr.update(visible=False)
                    if len(imgs) < 3:
                        return f"至少需要 3 张图片，当前只有 {len(imgs)} 张。", imgs, gr.update(visible=False)
                    from agent.skills.inspection_skill import InspectionSkill
                    import base64
                    skill = InspectionSkill()
                    skill._ensure_predictors()
                    from db import SessionLocal, InspectionRecord
                    db = SessionLocal()
                    try:
                        record = InspectionRecord(user_id=sess["user_id"], status="collecting")
                        db.add(record)
                        db.flush()
                        for img in imgs:
                            skill._add_image(db, record, img)
                        skill._run_inspection_on_all(db, record)
                        report = record.report or "报告生成失败。"
                        # 标注图片嵌入报告
                        anno_paths = getattr(record, "_annotated_paths", [])
                        img_tags = ""
                        for i, p in enumerate(anno_paths):
                            with open(p, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode()
                            img_tags += f'<img src="data:image/jpeg;base64,{b64}" style="max-width:400px;border:1px solid #ddd;margin:4px"><br><small>图{i+1} 缺陷标注</small><br>'
                        report_html = f"{img_tags}<hr><pre style='white-space:pre-wrap;font-family:sans-serif;font-size:14px'>{report}</pre>"
                        return report_html, [], gr.update(value=anno_paths, visible=True) if anno_paths else gr.update(visible=False)
                    finally:
                        db.close()

                inspect_btn.click(
                    _run_inspection,
                    [images_state, session_state],
                    [report_output, images_state, annotated_gallery],
                )

            with gr.TabItem("历史记录"):
                refresh_btn = gr.Button("刷新")
                history_table = gr.Dataframe(
                    label="巡检记录",
                    interactive=False,
                    headers=["ID", "时间", "图片数", "隐患数"],
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


            with gr.TabItem("智能问答"):
                with gr.Row():
                    # ── 左侧对话列表 ──
                    with gr.Column(scale=1):
                        gr.Markdown("### 对话列表")
                        conv_list = gr.Radio(
                            choices=[],
                            label="选择对话",
                            interactive=True,
                        )
                        with gr.Row():
                            new_conv_btn = gr.Button("+ 新建", size="sm")
                            del_conv_btn = gr.Button("删除", size="sm", variant="stop")

                    # ── 右侧聊天区 ──
                    with gr.Column(scale=3):
                        chatbot = gr.Chatbot(label="对话记录", height=450)
                        with gr.Row():
                            msg = gr.Textbox(
                                label="输入问题",
                                placeholder="例如：这栋楼有什么隐患？",
                                scale=4,
                            )
                            send_btn = gr.Button("发送", variant="primary", scale=1)
                        with gr.Row():
                            chat_image = gr.Image(
                                label="上传图片（可选）", type="numpy", height=180
                            )

                # ── 对话列表刷新 ──
                def _refresh_list(sess):
                    return gr.update(choices=list_user_conversations(sess))

                # 进入 Tab 时自动刷新列表
                conv_list.render = None
                # 用 login 后的 session_state 变化触发首次加载 —— 改成手动刷新

                # ── 选择对话 → 加载历史 ──
                def _select_conv(conv_id, sess):
                    if conv_id is None:
                        return [], sess
                    history, sess = load_conversation_messages(conv_id, sess)
                    return history, sess

                conv_list.change(
                    _select_conv,
                    [conv_list, session_state],
                    [chatbot, session_state],
                )

                # ── 新建对话 ──
                def _new_conv(sess):
                    sess = reset_chat_session(sess)
                    return (
                        [],
                        gr.update(choices=list_user_conversations(sess)),
                        sess,
                    )

                new_conv_btn.click(
                    _new_conv,
                    [session_state],
                    [chatbot, conv_list, session_state],
                    queue=False,
                )

                # ── 删除对话 ──
                def _del_conv(conv_id, sess):
                    choices, sess = delete_user_conversation(conv_id, sess)
                    next_conv_id = sess.get("conversation_id")
                    if next_conv_id:
                        history, sess = load_conversation_messages(next_conv_id, sess)
                    else:
                        history = []
                    return (
                        history,
                        gr.update(choices=choices, value=next_conv_id),
                        sess,
                    )

                del_conv_btn.click(
                    _del_conv,
                    [conv_list, session_state],
                    [chatbot, conv_list, session_state],
                    queue=False,
                )

                # ── 发送消息（流式 CoT）──
                def _handle_send(message, history, img, conv_id, sess):
                    if not message.strip():
                        yield "", history, img, conv_id, sess
                        return
                    # 流式输出中间状态
                    for msg_out, hist_out, _, sess_out in respond_stream(message, history, img, sess):
                        yield msg_out, hist_out, None, gr.update(choices=list_user_conversations(sess_out), value=sess_out.get("conversation_id")), sess_out

                send_btn.click(
                    _handle_send,
                    [msg, chatbot, chat_image, conv_list, session_state],
                    [msg, chatbot, chat_image, conv_list, session_state],
                )
                msg.submit(
                    _handle_send,
                    [msg, chatbot, chat_image, conv_list, session_state],
                    [msg, chatbot, chat_image, conv_list, session_state],
                )

            with gr.TabItem("Agent 监控"):
                _refresh_agent_btn = gr.Button("刷新状态")

                with gr.Row():
                    # Manager Agent 卡片
                    with gr.Column(scale=1):
                        gr.Markdown("### 🧠 Manager Agent")
                        manager_status = gr.HTML(_agent_status_html("manager", "通义千问 qwen3.6-flash", "在线", "#22c55e"))
                    # Memory Agent 卡片
                    with gr.Column(scale=1):
                        gr.Markdown("### 💾 Memory Agent")
                        memory_status = gr.HTML(_agent_status_html("memory", "qwen-turbo", "待命中", "#f59e0b"))
                    # Report Agent 卡片
                    with gr.Column(scale=1):
                        gr.Markdown("### 📋 Report Agent")
                        report_status = gr.HTML(_agent_status_html("report", "本地 Qwen2.5-VL", "检测中...", "#94a3b8"))

                gr.Markdown("---")
                token_ring = gr.HTML(_token_ring_html(0, 6000))
                gr.Markdown("<small style='color:#888'>上下文用量: 显示所有活跃对话的累积上下文字符数</small>")
                agent_log = gr.Textbox(label="Agent 日志", lines=5, interactive=False)

                def _refresh_agent_monitor():
                    import os, requests
                    # Report Agent 状态
                    report_url = os.getenv("REPORT_AGENT_URL", "http://localhost:8000")
                    try:
                        r = requests.get(f"{report_url}/health", timeout=3)
                        report_ok = r.status_code == 200
                    except Exception:
                        report_ok = False

                    # Token 统计 (从 DB 取最近对话)
                    from db import SessionLocal, get_recent_messages
                    from db.models import Conversation
                    db = SessionLocal()
                    try:
                        conv = db.query(Conversation).order_by(Conversation.updated_at.desc()).first()
                        if conv:
                            msgs = get_recent_messages(db, conv.id, limit=50)
                            total = sum(len(getattr(m, "content", "") or "") for m in msgs)
                        else:
                            total = 0
                    finally:
                        db.close()
                    threshold = int(os.getenv("MEMORY_EXTRACT_THRESHOLD", "6000"))

                    return (
                        _agent_status_html("manager", "通义千问 qwen3.6-flash", "在线", "#22c55e"),
                        _agent_status_html("memory", "qwen-turbo", f"{total}/{threshold} 字符" if total > 0 else "待命中", "#f59e0b"),
                        _agent_status_html("report", "本地 Qwen2.5-VL", "在线" if report_ok else "离线", "#22c55e" if report_ok else "#ef4444"),
                        _token_ring_html(total, threshold),
                        f"[Agent Monitor] Manager 在线 | Memory {total}chars | Report {'在线' if report_ok else '离线'}",
                    )

                _refresh_agent_btn.click(_refresh_agent_monitor, None, [manager_status, memory_status, report_status, token_ring, agent_log])

    # 认证操作不走队列，避免被「开始巡检」等耗时任务堵住导致登录一直 heartbeat
    login_btn.click(
        fn=_login_wrapper,
        inputs=[login_user, login_pass],
        outputs=[login_msg, session_state, login_block, main_block],
        queue=False,
    )
    reg_btn.click(
        fn=handle_register,
        inputs=[reg_user, reg_pass, reg_pass2],
        outputs=[reg_msg],
        queue=False,
    )
    logout_btn.click(
        fn=_logout_wrapper,
        inputs=[],
        outputs=[session_state, login_block, main_block],
        queue=False,
    )


if __name__ == "__main__":
    demo.launch(share=False)
