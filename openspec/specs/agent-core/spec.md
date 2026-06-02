# Agent Core

## Purpose
ReAct Agent 编排引擎，LLM 自主选择 Tool 执行建筑巡检任务，支持双层记忆和上下文管理。支持两种 LLM 后端：远程通义千问 DashScope API（默认）和本地 vLLM 服务化的微调 Qwen2.5-VL 模型（`USE_LOCAL_LLM=true`）。

## Requirements

### Requirement: ReAct Agent Loop
Agent SHALL execute a ReAct (Reasoning + Acting) loop: LLM decides which tools to call, executes them, feeds results back, and repeats until generating a final response.

#### Scenario: Single tool call
- **WHEN** user asks "这栋楼是什么材质"
- **THEN** LLM calls `classify_material` tool only, and returns the result

#### Scenario: Multi-tool comprehensive inspection
- **WHEN** user asks "全面检测这栋楼"
- **THEN** LLM may call `classify_material`, `detect_defects`, `search_knowledge` in sequence

#### Scenario: No tool needed
- **WHEN** user asks "你好，介绍一下你自己"
- **THEN** LLM responds directly without calling any tool

#### Scenario: Max rounds protection
- **WHEN** LLM keeps calling tools without generating a final response
- **THEN** agent SHALL stop after 10 rounds and force a summary

### Requirement: Tool System
Agent SHALL have 5 independently callable tools, each wrapping a CV predictor or knowledge source.

- `classify_material` — MaterialPredictor (EfficientNetV2)
- `estimate_floors` — FloorPredictor (YOLO + RANSAC)
- `detect_extension` — AddedFloorPredictor (EfficientNetV2)
- `detect_defects` — HiddenDangerPredictor (YOLO-OBB)
- `search_knowledge` — ChromaDB vector search + SQLite fallback

#### Scenario: Tool lazy loading
- **WHEN** agent is initialized without model files
- **THEN** tools SHALL defer predictor loading until first `execute()` call

### Requirement: Dual Memory System
Agent SHALL maintain short-term and long-term memory for each conversation.

#### Scenario: Short-term memory
- **WHEN** agent processes a new message
- **THEN** it SHALL inject the last 20 messages from the current conversation into LLM context

#### Scenario: Long-term memory extraction
- **WHEN** a conversation turn completes
- **THEN** LLM SHALL extract key facts (user_fact, building_info, preference) and upsert into ConversationMemory table

#### Scenario: Memory isolation
- **WHEN** user switches conversations
- **THEN** long-term memories SHALL be filtered by `conversation_id`, not cross-visible

### Requirement: Single Agent Instance
Both Gradio and FastAPI paths SHALL share one `InspectionAgent` singleton via `llm/agent_factory.py`.

### Requirement: LLM Backend Switching
The agent SHALL support switching between remote API and local vLLM backend via environment variables without code changes.

#### Scenario: Remote API (default)
- **WHEN** `USE_LOCAL_LLM` is unset or false
- **THEN** `agent_factory` SHALL create `LLMClient` with `tool_call_mode="native"` pointing to DashScope API

#### Scenario: Local vLLM
- **WHEN** `USE_LOCAL_LLM=true` and vLLM server is running on `localhost:8000`
- **THEN** `agent_factory` SHALL create `LLMClient` with `base_url="http://localhost:8000/v1"`, model from `LLM_MODEL`, and `tool_call_mode` from `LLM_TOOL_CALL_MODE` (default "prompt")

#### Scenario: Prompt-based tool calling fallback
- **WHEN** `LLM_TOOL_CALL_MODE=prompt` and `tools` are provided
- **THEN** `LLMClient.chat()` SHALL inject tool schemas as text into the system prompt, remove `tools` from the API request body, and parse `<tool_call>` blocks from the response text

## Dependencies
- **Depends on**: `llm/client.py` (LLM API calls + prompt fallback), `llm/react_parser.py` (text-based tool call parsing), `llm/tools.py` (5 Tool definitions → predictors), `agent/memory_manager.py` (context assembly), `agent/rag.py` (regulation search), `db/` (persistence)
- **Depended on by**: `api/chat.py` (chat endpoint), `services/chat_service.py` (Gradio chat callbacks), `app` (智能问答 Tab)
