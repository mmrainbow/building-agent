# Chat System

## Purpose
智能问答对话系统 — Gradio UI + API 双入口，ReAct Agent 驱动，支持多轮对话、历史回顾、图片持久化。

## Requirements

### Requirement: Conversation Management
System SHALL support creating, listing, switching, and deleting conversations per user.

#### Scenario: Create new conversation
- **WHEN** user sends first message in chat
- **THEN** a new `conversations` row SHALL be created with auto-generated title

#### Scenario: Continue existing conversation
- **WHEN** user selects a conversation from the sidebar and sends a message
- **THEN** the message SHALL be appended to that conversation

#### Scenario: Delete conversation
- **WHEN** user deletes a conversation
- **THEN** all messages, images, and memories SHALL be cascade-deleted

### Requirement: Image Persistence
System SHALL store uploaded images as BLOBs in `chat_images` table and render them in conversation history.

#### Scenario: Image in history
- **WHEN** user reopens a conversation that had images
- **THEN** images SHALL render in the chat via BLOB → cache file → Gradio path

#### Scenario: Image survives project move
- **WHEN** project directory is moved to a different location
- **THEN** images SHALL still render because data is in database BLOBs

### Requirement: Gradio Conversation Sidebar
Gradio "智能问答" Tab SHALL show a conversation list sidebar with switch, new, and delete controls.

#### Scenario: Switch conversation
- **WHEN** user clicks a conversation in the radio list
- **THEN** chatbot SHALL load all messages (with images) from that conversation

### Requirement: Tool Call Transparency
System SHALL append tool call names to assistant responses (e.g., "> 🔧 已调用: classify_material, detect_defects").

### Requirement: History Preserves Tool Role
When loading conversation history, tool message roles SHALL be preserved (not disguised as "user") to prevent LLM from re-calling already-executed tools.

## Dependencies
- **Depends on**: `agent/orchestrator.py` (ReAct Agent), `agent/memory_manager.py` (context), `llm/chat_core.py` (run_chat), `db/chat_crud.py` (message persistence), `db/models.py` (ChatMessage/ChatImage/Conversation)
- **Depended on by**: `api/chat.py` (chat API endpoints), `app` (智能问答 Tab)
