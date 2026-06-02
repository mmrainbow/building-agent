# Database

## Purpose
SQLAlchemy ORM 数据持久化 — 12 张表覆盖用户、巡检、对话、记忆、反馈、知识库。

## Requirements

### Requirement: User and Auth
System SHALL store users with bcrypt-hashed passwords and role-based access (user/admin).

#### Scenario: User registration
- **WHEN** a new user registers
- **THEN** a `users` row is created with role="user" and bcrypt-hashed password

### Requirement: Inspection Records
System SHALL separate inspection sessions (`inspection_records`) from per-image results (`image_inspection`).

#### Scenario: One record, many images
- **WHEN** user inspects 3 images of one building
- **THEN** 1 `inspection_records` row + 3 `image_inspection` rows are created

### Requirement: Conversation and Chat
System SHALL persist conversation sessions and individual messages with optional image BLOBs.

#### Scenario: Message with image
- **WHEN** user sends a message with an uploaded image
- **THEN** system SHALL create 1 `chat_messages` row + 1 `chat_images` row (BLOB)

### Requirement: Image Deduplication
System SHALL NOT store duplicate image data. `image_inspection.chat_image_id` SHALL FK-reference `chat_images`. The image BLOB lives only in `chat_images`.

#### Scenario: Inspection from chat
- **WHEN** inspection uses images already uploaded in chat
- **THEN** `image_inspection.chat_image_id` SHALL point to the existing `chat_images` row

### Requirement: Memory Persistence
System SHALL store long-term memories per-conversation with upsert on (user_id, memory_type, key, conversation_id).

#### Scenario: Memory upsert
- **WHEN** LLM extracts "用户偏好简短报告" with key="report_style"
- **THEN** existing memory with same key SHALL be updated, not duplicated

### Requirement: Full Table Documentation
All 12 tables SHALL be documented in `db/SCHEMA.md` with column types, constraints, and ER diagram.
