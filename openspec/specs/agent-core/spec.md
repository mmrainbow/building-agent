# Agent Core

## Purpose
ReAct Agent 编排引擎，LLM 自主选择 Tool 执行建筑巡检任务，支持双层记忆和上下文管理。

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
