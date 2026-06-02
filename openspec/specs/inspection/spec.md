# Inspection

## Purpose
建筑外立面巡检 — 多图收集、CV 批处理检测、LLM 报告生成、数据持久化。

## Requirements

### Requirement: Multi-Image Collection
Inspection SHALL require at least 3 images of the same building before running detection.

#### Scenario: Collecting phase
- **WHEN** user uploads 1st image and clicks "添加"
- **THEN** system stores image in `image_inspection` with status="collecting" and prompts "还需 2 张"

#### Scenario: Trigger inspection
- **WHEN** image count reaches 3
- **THEN** system SHALL run CV detection on all collected images and generate a report

#### Scenario: Continue adding after minimum
- **WHEN** user adds a 4th or 5th image to an existing inspection
- **THEN** system SHALL re-run inspection on all images and update the report

### Requirement: CV Detection Pipeline
Inspection SHALL detect material, floor count, extension, and defects for each image independently.

#### Scenario: Per-image detection
- **WHEN** inspecting multiple images
- **THEN** each image gets independent material/floor/extension/defect results stored in `image_inspection`

#### Scenario: Defect-level granularity
- **WHEN** an image has 3 defects
- **THEN** 3 rows SHALL be created in `defects` table, each with `image_id` FK

### Requirement: Report Generation
Inspection SHALL generate a Chinese report referencing specific image numbers for each finding.

#### Scenario: Report with image references
- **WHEN** generating report for 3 images
- **THEN** report SHALL reference "图1", "图2", "图3" for each defect finding

### Requirement: Data Persistence
Inspection SHALL save results to `inspection_records` (status='done'), `image_inspection` (per-image results), and `defects` (per-image defects).

### Requirement: Standalone Workflow
Inspection SHALL NOT be a ReAct Tool. It SHALL be a standalone Gradio "图像巡检" Tab with direct button triggers, independent of LLM decision-making.
