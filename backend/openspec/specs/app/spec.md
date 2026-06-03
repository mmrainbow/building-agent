# App (Gradio Web UI)

## Purpose
Gradio 6 Web 界面 — 4 Tab 交互入口，session 状态管理，service 层适配。提供图像巡检、历史记录、统计分析、智能问答四大功能。

## Requirements

### Requirement: Four-Tab Structure
The app SHALL provide 4 tabs: 图像巡检 (multi-image CV), 历史记录 (history browser), 统计分析 (charts), 智能问答 (ReAct chat).

#### Scenario: Tab switching
- **WHEN** user clicks a different tab
- **THEN** each tab SHALL load its own data independently via its specific service callbacks

### Requirement: Login/Registration Flow
The app SHALL show a login/register form on startup, hiding main content until authentication succeeds. `services/auth_service.py` SHALL return pure data; UI visibility SHALL be toggled in `app.py`.

#### Scenario: First startup
- **WHEN** no users exist and `INIT_ADMIN_USERNAME` / `INIT_ADMIN_PASSWORD` are set
- **THEN** `bootstrap_data()` SHALL create the initial admin account

#### Scenario: Successful login
- **WHEN** user enters correct credentials
- **THEN** `_login_wrapper()` SHALL call `handle_login()`, populate `session_state` with `{user_id, username, role}`, hide login_block, show main_block

#### Scenario: Wrong credentials
- **WHEN** user enters wrong password
- **THEN** SHALL show error message via `login_msg` Markdown, keep login_block visible

#### Scenario: Registration
- **WHEN** user submits registration form
- **THEN** `handle_register()` SHALL validate passwords match, create user with `role="user"`, and return status message

#### Scenario: Logout
- **WHEN** user clicks "退出登录"
- **THEN** `_logout_wrapper()` SHALL reset `session_state` to None, show login_block, hide main_block

### Requirement: Session State Management
`session_state` SHALL be a `gr.State` dict holding `{user_id, username, role, conversation_id, last_image?}`. Service functions SHALL receive and return session_state dicts. Passwords or tokens SHALL NOT be stored in session_state.

#### Scenario: After login
- **WHEN** authentication succeeds
- **THEN** `session_state` SHALL contain at minimum `{user_id, username, role}`

#### Scenario: After logout
- **WHEN** user logs out
- **THEN** `session_state` SHALL be set to `None`

### Requirement: Service Layer Abstraction
`services/` SHALL contain independent modules that return pure Python data (strings, dicts, DataFrames, Plotly figures) without depending on Gradio components. `app.py` SHALL wrap service responses with `gr.update()` as needed.

#### Scenario: Adding a new service
- **WHEN** a new feature needs a service module
- **THEN** developer SHALL create it in `services/` without importing Gradio

#### Scenario: Avoid import chain
- **WHEN** new modules import from `services/__init__.py`
- **THEN** SHALL NOT trigger a cascade that loads `agent.graph` → YOLO/torch

### Requirement: Inspection Tab
The 图像巡检 Tab SHALL support multi-image collection with Gallery preview, enforcing minimum 3 images before triggering CV pipeline via `InspectionSkill`.

#### Scenario: Adding images
- **WHEN** user uploads an image and clicks "添加到列表"
- **THEN** image SHALL be appended to `images_state`, Gallery SHALL update, status SHALL show "📸 已收集 N 张 | 至少需要 3 张"

#### Scenario: Minimum image requirement met
- **WHEN** 3 images are collected
- **THEN** status SHALL show "📸 已收集 3 张 | 至少需要 3，可以开始巡检 ✅"

#### Scenario: Trigger inspection
- **WHEN** user clicks "开始巡检" with ≥3 images
- **THEN** SHALL create `InspectionRecord`, call `InspectionSkill._add_image()` for each image, call `_run_inspection_on_all()`, return the generated Chinese report

#### Scenario: Insufficient images
- **WHEN** user clicks "开始巡检" with <3 images
- **THEN** SHALL return error message "至少需要 3 张图片，当前只有 N 张。"

#### Scenario: Not logged in
- **WHEN** user clicks "开始巡检" without authentication
- **THEN** SHALL return "请先登录。"

#### Scenario: Clear gallery
- **WHEN** user clicks "清空"
- **THEN** `images_state` SHALL reset to empty list, Gallery SHALL clear, status SHALL reset (no queue blocking)

### Requirement: History Tab
The 历史记录 Tab SHALL show a Dataframe of past inspections with row selection for detail viewing and Excel export.

#### Scenario: Loading history
- **WHEN** user clicks "刷新"
- **THEN** `load_history()` SHALL query inspection records and return a Dataframe with columns [ID, 时间, 图片数, 隐患数]

#### Scenario: Viewing record detail
- **WHEN** user selects a table row
- **THEN** `show_record_detail()` SHALL populate the report Textbox and defects Dataframe for that record

#### Scenario: Excel export
- **WHEN** user clicks "导出当前记录为 Excel"
- **THEN** `export_history_to_excel()` SHALL generate an `.xlsx` file (via openpyxl) for the selected record

### Requirement: Statistics Tab
The 统计分析 Tab SHALL render Plotly charts and summary text from aggregated inspection data.

#### Scenario: Loading statistics
- **WHEN** user clicks "刷新统计"
- **THEN** `load_statistics()` SHALL return: a pie chart (defect type distribution), a bar chart (material distribution), a line chart (30-day inspection trend), and summary Markdown text

#### Scenario: No data
- **WHEN** user has no inspection records
- **THEN** charts SHALL show empty placeholders

### Requirement: Smart Q&A Tab
The 智能问答 Tab SHALL provide a conversation sidebar + chat interface backed by the ReAct Agent.

#### Scenario: Conversation sidebar
- **WHEN** user clicks "智能问答" tab
- **THEN** left sidebar SHALL show a `gr.Radio` list of conversations with "+ 新建" and "删除" buttons

#### Scenario: New conversation
- **WHEN** user clicks "+ 新建"
- **THEN** `reset_chat_session()` SHALL clear chat history and create a new conversation in the database

#### Scenario: Switch conversation
- **WHEN** user selects a conversation from the radio list
- **THEN** `load_conversation_messages()` SHALL populate the chatbot with full message history (including images via blob retrieval)

#### Scenario: Delete conversation
- **WHEN** user selects a conversation and clicks "删除"
- **THEN** `delete_user_conversation()` SHALL cascade-delete messages, images, and memories; sidebar SHALL refresh

#### Scenario: Send message with image
- **WHEN** user types a message and attaches an image
- **THEN** `respond()` SHALL store image in `sess["last_image"]`, call `chat_with_llm()`, append user + assistant messages to chat_history

#### Scenario: Tool call display
- **WHEN** ReAct Agent calls CV tools during a conversation
- **THEN** assistant response SHALL include tool call summary (e.g., "> 🔧 已调用: classify_material, detect_defects")

### Requirement: Queue Strategy
Authentication operations (login, register, logout, clear gallery) SHALL use `queue=False` to prevent blocking by long-running CV inference tasks. Inspection and chat operations SHALL use default queue behavior.

#### Scenario: Login during inspection
- **WHEN** a long CV inspection is running and another user tries to log in
- **THEN** login SHALL respond immediately without waiting for the inspection to complete

### Requirement: Chinese Localization
All labels, messages, and button text SHALL be in Chinese. `services/constants.py` TEXT dictionary SHALL be the single source of truth for user-facing strings.

#### Scenario: Add new UI text
- **WHEN** a new label or message is needed
- **THEN** developer SHALL add it to `services/constants.py` TEXT dict and reference via `TEXT["key"]`

## Dependencies
- **Depends on**: `services/` (6 modules: auth, inspection, history, statistics, chat, constants), `agent/skills/inspection_skill.py` (CV pipeline), `agent/orchestrator.py` (ReAct agent), `db/` (data persistence), Gradio 6, Plotly (charts), openpyxl (Excel export)
- **Depended on by**: End users (primary UI entry point)
