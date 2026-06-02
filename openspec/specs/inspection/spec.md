# Inspection

## Purpose
建筑外立面巡检 — 多图收集、CV 批处理检测、LLM 报告生成、数据持久化。通过 `InspectionSkill` 实现独立于 ReAct Agent 的完整工作流。

## Requirements

### Requirement: InspectionSkill State Machine
InspectionSkill SHALL manage a state machine with two states: `collecting` (accumulating images) and `done` (inspection complete). MIN_IMAGES SHALL be 3.

#### Scenario: collecting → done transition
- **WHEN** 3 images are collected for the same record
- **THEN** `_run_inspection_on_all()` SHALL execute all 4 CV predictors on all images → generate LLM report → set `record.status="done"` → commit all defects

#### Scenario: Reuse existing collecting session
- **WHEN** user uploads an image for inspection
- **THEN** `_get_or_create_record()` SHALL find the most recent `status="collecting"` record for that user; if none exists, create a new one

#### Scenario: Post-done addition (4th+ image)
- **WHEN** user adds a 4th image to an already-done inspection
- **THEN** the image SHALL be added to the record, and `_run_inspection_on_all()` SHALL re-run all CV detectors on ALL images (1-4), update the report, and re-commit updated defects

#### Scenario: InspectionSkill not a ReAct Tool
- **WHEN** inspection is triggered via Gradio "图像巡检" Tab
- **THEN** InspectionSkill SHALL be called directly via button callback, NOT via LLM `tool_calls`

### Requirement: Multi-Image Collection
Inspection SHALL require at least 3 images of the same building before running detection.

#### Scenario: Collecting phase
- **WHEN** user uploads 1st image
- **THEN** system SHALL create `InspectionRecord(status="collecting")`, encode image as JPEG BLOB via `ChatImage`, create `ImageInspection(chat_image_id=...)`, and prompt "还需 2 张"

#### Scenario: Trigger inspection
- **WHEN** image count reaches 3
- **THEN** system SHALL run CV detection on all collected images and generate a Chinese report

#### Scenario: Continue adding after minimum
- **WHEN** user adds a 4th or 5th image to an existing inspection
- **THEN** system SHALL re-run inspection on all images and update the report

### Requirement: Per-Image CV Detection Pipeline
Inspection SHALL detect material, floor count, extension, and defects for each image independently.

#### Scenario: Per-image detection
- **WHEN** inspecting multiple images
- **THEN** each image SHALL get independent material/floor/extension/defect results stored in its `image_inspection` row

#### Scenario: Defect-level granularity
- **WHEN** an image has 3 defects
- **THEN** 3 rows SHALL be created in `defects` table, each with `image_id` FK

### Requirement: Report Generation
Inspection SHALL generate a 300-400 character Chinese report referencing specific image numbers for each finding.

#### Scenario: Report with image references
- **WHEN** generating report for 3 images
- **THEN** report SHALL reference "图1", "图2", "图3" for each defect finding

#### Scenario: Report structure
- **WHEN** report is generated
- **THEN** SHALL follow format: [检测概况(图片数+建筑概况)] → [逐图分析(引用图片编号)] → [综合评定] → [处理建议]

#### Scenario: Defect formatting in report
- **WHEN** defects are detected on multiple images
- **THEN** report SHALL list each defect with source image index (e.g., "图1: 裂缝 (面积: 1234px²)")

### Requirement: Data Persistence
Inspection SHALL save results to `inspection_records` (status='done', report TEXT), `image_inspection` (per-image material/floor/has_extension), and `defects` (per-image defect_type/area/box_coords).

#### Scenario: Complete inspection save
- **WHEN** inspection completes for 3 images with 5 total defects
- **THEN** 1 `inspection_records` row (status=done) + 3 `image_inspection` rows + 5 `defects` rows SHALL be persisted

### Requirement: Standalone Workflow
Inspection SHALL NOT be part of the ReAct Agent's tool system. It SHALL be a standalone workflow triggered via Gradio "图像巡检" Tab or `POST /predict` API.

#### Scenario: Inspection tab vs Q&A tab
- **WHEN** user wants full inspection of multiple images
- **THEN** SHALL use "图像巡检" Tab (InspectionSkill workflow), not "智能问答" Tab (ReAct Agent with 5 tools)

#### Scenario: API path
- **WHEN** `POST /predict` is called with an image
- **THEN** SHALL run LangGraph DAG (all 4 predictors → report), optionally using local VL model for report generation before falling back to remote LLM+RAG

## Dependencies
- **Depends on**: `predictors/` (4 CV models), `agent/skills/inspection_skill.py` (InspectionSkill), `llm/local_vl_model.py` (optional local VL), `db/models.py` (InspectionRecord/ImageInspection/Defect), `db/crud.py` (persistence)
- **Depended on by**: `app` (Gradio 图像巡检 Tab), `api/main.py` (POST /predict), `main.py` (CLI)
