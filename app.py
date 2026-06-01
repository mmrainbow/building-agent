from pathlib import Path

from dotenv import load_dotenv

# 必须在 import services/db 之前加载，否则 INSPECTION_DB_URL 等已在 import 时固化
load_dotenv(Path(__file__).resolve().parent / ".env")

import gradio as gr

from services import (
    TEXT,
    bootstrap_data,
    chat_with_llm,
    reset_chat_session,
    do_logout,
    export_history_to_excel,
    handle_login,
    handle_register,
    inspect_and_save,
    load_history,
    load_statistics,
    show_record_detail,
)

bootstrap_data()


def respond(message, chat_history, chat_image, sess):
    if not message.strip():
        return "", chat_history, chat_image, sess
    # 如果上传了图片，将图片存入 session 供后续对话使用
    if chat_image is not None:
        sess["last_image"] = chat_image
    bot_message = chat_with_llm(message, chat_history, sess, image=chat_image)
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": bot_message})
    return "", chat_history, None, sess


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
                gr.Markdown(
                    "**ReAct Agent** — AI 自主选择调用 CV 工具。"
                    "可上传图片让 AI 分析，也可纯文本咨询建筑巡检问题。"
                )
                chatbot = gr.Chatbot(label="对话记录", height=450)
                with gr.Row():
                    msg = gr.Textbox(
                        label="输入问题",
                        placeholder="例如：这栋楼有什么隐患？全面检测一下",
                        scale=4,
                    )
                    send_btn = gr.Button("发送", variant="primary", scale=1)
                with gr.Row():
                    chat_image = gr.Image(label="上传图片（可选）", type="numpy", height=200)
                    clear = gr.Button("新建对话", scale=1)

                def _handle_send(message, history, img, sess):
                    return respond(message, history, img, sess)

                send_btn.click(
                    _handle_send,
                    [msg, chatbot, chat_image, session_state],
                    [msg, chatbot, chat_image, session_state],
                )
                msg.submit(
                    respond,
                    [msg, chatbot, chat_image, session_state],
                    [msg, chatbot, chat_image, session_state],
                )

                def _clear_chat(sess):
                    return [], reset_chat_session(sess)

                clear.click(
                    _clear_chat,
                    inputs=[session_state],
                    outputs=[chatbot, session_state],
                    queue=False,
                )

    # 认证操作不走队列，避免被「开始巡检」等耗时任务堵住导致登录一直 heartbeat
    login_btn.click(
        fn=handle_login,
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
        fn=do_logout,
        inputs=[],
        outputs=[session_state, login_block, main_block],
        queue=False,
    )


if __name__ == "__main__":
    demo.launch(share=False)
