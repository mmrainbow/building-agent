# Database

## Purpose
SQLAlchemy ORM 数据持久化 — 12 张表覆盖用户、巡检、对话、记忆、反馈、知识库。完整字段级文档见 `db/SCHEMA.md`。

## Requirements

### Requirement: User and Auth
System SHALL store users with bcrypt-hashed passwords and role-based access (user/admin). `username` SHALL be VARCHAR(50) UNIQUE NOT NULL. `password_hash` SHALL be VARCHAR(255) NOT NULL. `role` SHALL be ENUM(UserRole) default "user". `is_active` SHALL be BOOLEAN default True (soft-delete marker). `last_login_at` SHALL be DATETIME nullable.

#### Scenario: User registration
- **WHEN** a new user registers
- **THEN** a `users` row is created with role="user" and bcrypt-hashed password

#### Scenario: Admin bootstrap
- **WHEN** no users exist and `INIT_ADMIN_USERNAME` / `INIT_ADMIN_PASSWORD` env vars are set
- **THEN** system SHALL create an admin user on startup

### Requirement: Inspection Records
System SHALL separate inspection sessions (`inspection_records`) from per-image results (`image_inspection`). `InspectionRecord.status` SHALL be VARCHAR(20) with values "collecting"|"done". `image_inspection` SHALL contain `material` (VARCHAR 100), `floor` (VARCHAR 20), `has_extension` (VARCHAR 20). `Defect` SHALL store `defect_type` (VARCHAR 50), `area` (FLOAT), `box_coords` (JSON — OBB 多边形坐标).

#### Scenario: One record, many images
- **WHEN** user inspects 3 images of one building
- **THEN** 1 `inspection_records` row + 3 `image_inspection` rows are created, each with independent material/floor/extension/defects

#### Scenario: Defect-level granularity
- **WHEN** an image has 3 defects
- **THEN** 3 rows SHALL be created in `defects` table, each with `image_id` FK referencing `image_inspection`

### Requirement: Conversation and Chat
System SHALL persist conversation sessions and individual messages with optional image BLOBs. `Conversation` SHALL have `title` (VARCHAR 255), `model` (VARCHAR 100), `message_count` (INTEGER default 0), `created_at`, `updated_at` (auto-update on change). `ChatMessage.role` SHALL be VARCHAR(20) with values "user"|"assistant"|"system"|"tool". `ChatMessage.metadata` SHALL be JSON storing tokens, latency_ms, sources, tool_call_log. `ChatImage.data` SHALL be LARGEBINARY NOT NULL, `mime_type` SHALL be VARCHAR(50) default "image/jpeg".

#### Scenario: Message with image
- **WHEN** user sends a message with an uploaded image
- **THEN** system SHALL create 1 `chat_messages` row + 1 `chat_images` row (JPEG BLOB), linked by `message_id` FK with CASCADE delete

#### Scenario: Conversation lifecycle
- **WHEN** first message of a conversation is sent
- **THEN** `Conversation` SHALL be created with auto-generated title from first message content

### Requirement: Image Deduplication
System SHALL NOT store duplicate image data. `image_inspection.chat_image_id` SHALL FK-reference `chat_images` (ondelete="SET NULL"). The image BLOB lives only in `chat_images`.

#### Scenario: Inspection from chat
- **WHEN** inspection uses images already uploaded in chat
- **THEN** `image_inspection.chat_image_id` SHALL point to the existing `chat_images` row — no duplicate BLOB

### Requirement: Memory Persistence
System SHALL store long-term memories in `conversation_memories` with upsert on (user_id, memory_type, key, conversation_id). Key fields: `memory_type` (VARCHAR 30, enum: user_fact/building_info/preference/summary), `importance` (FLOAT default 0.5, 0-1 range), `access_count` (INTEGER default 0, heat metric for eviction), `chroma_id` (VARCHAR 255, reserved for future vector integration), `last_accessed_at` (DATETIME). `conversation_id` FK SHALL be nullable with ondelete="SET NULL" (memories survive conversation deletion).

#### Scenario: Memory upsert
- **WHEN** LLM extracts "用户偏好简短报告" with key="report_style"
- **THEN** existing memory with same (user_id, memory_type, key, conversation_id) SHALL be updated, not duplicated

#### Scenario: Memory isolation by conversation
- **WHEN** user switches conversations
- **THEN** memory retrieval SHALL filter by current `conversation_id`

### Requirement: User Preferences
`UserPreference` SHALL be 1:1 with User (unique `user_id` FK). Fields: `language` (VARCHAR 10, default "zh"), `report_style` (VARCHAR 20, default "standard"), `preferred_model` (VARCHAR 100, nullable), `extra` (JSON), `updated_at` (auto-update).

#### Scenario: First preference access
- **WHEN** user has no preference row yet
- **THEN** system SHALL create one with default values

### Requirement: Feedback Table
`Feedback` SHALL support dual FK: `record_id` (FK→inspection_records, ondelete="SET NULL") and `message_id` (FK→chat_messages, ondelete="SET NULL"). At least one SHALL be non-NULL. Fields: `feedback_type` (VARCHAR 30), `target_field` (VARCHAR 100), `original_value` (TEXT), `corrected_value` (TEXT), `rating` (INTEGER 1-5), `comment` (TEXT). Upsert strategy: per (user_id, feedback_type, target_field, record_id/message_id).

#### Scenario: Correction feedback
- **WHEN** user corrects a material detection result
- **THEN** record_id references the inspection, target_field="material", original_value and corrected_value both populated

#### Scenario: Chat rating feedback
- **WHEN** user rates a chat message
- **THEN** message_id references the chat message, rating 1-5, corrected_value is NULL

### Requirement: Knowledge Base Tables
`KnowledgeDocument` SHALL store document metadata: `title` (VARCHAR 255 NOT NULL), `file_name` (VARCHAR 255), `file_type` (VARCHAR 20: pdf/md/txt), `source_type` (VARCHAR 50: regulation/manual/report_template/general), `chunk_count` (INTEGER default 0), `status` (VARCHAR 20 default "active"). `KnowledgeChunk` SHALL store: `document_id` FK (CASCADE), `chunk_index` (INTEGER NOT NULL), `content` (TEXT NOT NULL), `chroma_id` (VARCHAR 255), `metadata` (JSON). Vector data SHALL live in ChromaDB (`chroma_db/`), metadata in SQLite (`inspection.db`).

#### Scenario: Document ingestion
- **WHEN** a PDF document is ingested
- **THEN** 1 `knowledge_documents` row + N `knowledge_chunks` rows are created; chunks are also embedded and stored in ChromaDB

#### Scenario: Vector-data separation
- **WHEN** ChromaDB is unavailable
- **THEN** SQL metadata (documents + chunks) SHALL still be queryable; search falls back to SQLite LIKE

### Requirement: Full Table Documentation
All 12 tables SHALL be documented in `db/SCHEMA.md` with column types, constraints, and ER diagram. `db/models.py` SHALL be the authoritative source for column definitions.

## Dependencies
- **Depends on**: SQLAlchemy 2, SQLite/MySQL driver, bcrypt (password hashing)
- **Depended on by**: ALL other modules — `api/` (endpoints), `agent/` (state persistence), `services/` (Gradio data), `scripts/build_rag.py` (knowledge ingestion)
