# Feedback System (反馈系统)

## Purpose
用户反馈收集与导出系统 — 支持巡检结果纠错和对话质量评分，upsert 防重复，数据可导出为模型微调数据集。

## Requirements

### Requirement: Feedback Types
System SHALL support 3 feedback types: `inspection_correction` (correction of CV detection results), `chat_rating` (message quality rating), `report_rating` (overall report evaluation). Each type SHALL have distinct validation rules.

#### Scenario: Inspection correction
- **WHEN** user corrects a CV-detected material from "涂料" to "面砖"
- **THEN** feedback record SHALL have `feedback_type="inspection_correction"`, `target_field="material"`, `original_value="涂料"`, `corrected_value="面砖"`

#### Scenario: Chat rating
- **WHEN** user rates a chat response 4 stars
- **THEN** feedback record SHALL have `feedback_type="chat_rating"`, `rating=4`, optional `comment`

#### Scenario: Report rating
- **WHEN** user rates an inspection report 5 stars
- **THEN** feedback record SHALL have `feedback_type="report_rating"`, `rating=5`

#### Scenario: Dual FK constraint
- **WHEN** creating a feedback record
- **THEN** at least one of `record_id` or `message_id` SHALL be non-NULL

### Requirement: Upsert Strategy
`create_feedback()` SHALL upsert on composite key `(user_id, feedback_type, target_field, record_id/message_id)`. Same-user re-correction of the same field SHALL update the existing record rather than create a duplicate.

#### Scenario: User re-corrects same field
- **WHEN** user who already corrected "material" on record 42 submits another correction
- **THEN** the existing feedback row SHALL be updated with new `corrected_value`, `rating`, `comment`, and fresh `created_at` timestamp — no new row created

#### Scenario: Different user, same field
- **WHEN** a different user corrects "material" on record 42
- **THEN** a new row SHALL be created (upsert is per-user)

### Requirement: Feedback CRUD Operations
CRUD operations SHALL provide list and stats endpoints for administration and UI display.

#### Scenario: Admin listing with filter
- **WHEN** `get_feedback_list(db, feedback_type="inspection_correction", limit=100)` is called
- **THEN** SHALL return up to 100 matching feedback records ordered by newest first

#### Scenario: User's own feedback
- **WHEN** `get_user_feedback(db, user_id=5)` is called
- **THEN** SHALL return only feedback submitted by user 5

#### Scenario: Statistics summary
- **WHEN** `get_feedback_stats(db)` is called
- **THEN** SHALL return `{total, average_rating, by_type: [{type, count}, ...]}`

### Requirement: Fine-Tuning Data Export
`export_feedback_for_finetune()` SHALL export inspection corrections as JSONL-ready dataset entries for model fine-tuning.

#### Scenario: Export corrections
- **WHEN** `export_feedback_for_finetune(db)` is called
- **THEN** SHALL filter `feedback_type="inspection_correction"` with `corrected_value IS NOT NULL`, return up to `limit` records as `[{prompt, input, completion}, ...]`

#### Scenario: Prompt format
- **WHEN** a correction for `target_field="material"` is exported
- **THEN** entry SHALL have `prompt="识别建筑material"`, `input=original_value`, `completion=corrected_value`

#### Scenario: No corrections available
- **WHEN** no inspection corrections exist in the database
- **THEN** SHALL return empty list `[]`

### Requirement: Feedback Table Schema
Feedback table SHALL store: `id` (PK), `user_id` (FK→users), `record_id` (FK→inspection_records, nullable), `message_id` (FK→chat_messages, nullable), `feedback_type` (VARCHAR 30), `target_field` (VARCHAR 100), `original_value` (TEXT), `corrected_value` (TEXT), `rating` (INTEGER 1-5), `comment` (TEXT), `created_at` (DATETIME).

#### Scenario: Full field specification
- **WHEN** a feedback record is inspected
- **THEN** all fields SHALL match `db/SCHEMA.md` Section 10 definitions and `db/models.py` Feedback class

## Dependencies
- **Depends on**: `db/models.py` (Feedback model), `db/feedback_crud.py` (CRUD operations)
- **Depended on by**: `app` (Gradio feedback UI, planned Stage 2)
