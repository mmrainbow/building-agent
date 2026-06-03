# Predictors (CV 模型层)

## Purpose
CV 预测器模块 — 所有建筑外立面检测模型的统一抽象层。4 个具体预测器（材质/楼层/加层/隐患）+ 1 个几何算法辅助模块，全部继承 `BasePredictor`。

## Requirements

### Requirement: BasePredictor Contract
All predictors SHALL inherit from `predictors.base.BasePredictor` and implement `predict(images: List[np.ndarray]) -> List`. The base class SHALL auto-select CUDA/CPU device on construction and provide `transform_image()` for batch preprocessing with `torchvision.transforms.Compose`.

#### Scenario: CUDA available
- **WHEN** `BasePredictor()` is constructed on a CUDA-capable machine
- **THEN** `self.device` SHALL be `torch.device("cuda")`

#### Scenario: CPU only
- **WHEN** `BasePredictor()` is constructed without CUDA
- **THEN** `self.device` SHALL be `torch.device("cpu")`, `self.batch_size` SHALL be 2

#### Scenario: transform_image with invalid argument
- **WHEN** `transform_image()` is called with a non-Compose `trans` argument
- **THEN** SHALL raise `TypeError`

#### Scenario: load_images_from_paths
- **WHEN** `load_images_from_paths()` is called with a list of file paths
- **THEN** SHALL return `List[np.ndarray]` via `cv2.imread()`, raise `ValueError` if any file fails to read

### Requirement: MaterialPredictor (EfficientNetV2 Multi-Label)
MaterialPredictor SHALL classify building facade into 12 material types using EfficientNetV2 with multi-label sigmoid classification.

#### Scenario: High confidence single material
- **WHEN** image clearly shows 面砖 facade
- **THEN** SHALL return `["面砖"]` if prob > 0.3

#### Scenario: Multi-label match
- **WHEN** image contains both 涂料 and 面砖
- **THEN** SHALL return comma-separated labels, e.g., `["涂料,面砖"]`

#### Scenario: All below threshold
- **WHEN** no class exceeds 0.3 probability
- **THEN** SHALL return `["{best_class}(low confidence)"]` for the highest-probability class

#### Scenario: Model weights path
- **WHEN** MaterialPredictor is initialized
- **THEN** SHALL load weights from `model_weights/material.pth`

### Requirement: FloorPredictor (YOLO + RANSAC)
FloorPredictor SHALL detect building floors using dual YOLO models with RANSAC-based window column clustering.

#### Scenario: Urban high-rise
- **WHEN** a multi-story building image is processed
- **THEN** SHALL run main_building YOLO (640px) to detect building, outer_obj YOLO (960px) to exclude external objects within building bounds, cluster windows into columns via RANSAC, and return `"{N}层"`

#### Scenario: Single-story building
- **WHEN** a single-story image is processed
- **THEN** SHALL return `"1层"`

#### Scenario: Model files required
- **WHEN** FloorPredictor is initialized
- **THEN** SHALL load `model_weights/main_building.pt` and `model_weights/outer_obj.pt`

### Requirement: AddedFloorPredictor (EfficientNetV2 Binary)
AddedFloorPredictor SHALL classify whether a building has roof extensions using binary classification.

#### Scenario: Roof extension detected
- **WHEN** image shows added floors on the roof
- **THEN** SHALL return `"有加层"` (prob > 0.5)

#### Scenario: No extension
- **WHEN** image shows a normal roof
- **THEN** SHALL return `"无加层"` (prob <= 0.5)

#### Scenario: Model weights
- **WHEN** AddedFloorPredictor is initialized
- **THEN** SHALL load `model_weights/add_predict.pth` (binary classifier)

### Requirement: HiddenDangerPredictor (YOLO-OBB)
HiddenDangerPredictor SHALL detect oriented bounding box (OBB) defects on building facades.

#### Scenario: Multiple defects in one image
- **WHEN** image contains 3 defects (空鼓, 渗水, 裂缝)
- **THEN** SHALL return `[{id, type, area, box}, ...]` with 3 entries, each having defect_type set to the Chinese name, area computed from OBB polygon coordinates

#### Scenario: No defects
- **WHEN** image has no visible defects
- **THEN** SHALL return `[]` (empty list)

#### Scenario: Defect types
- **WHEN** HiddenDangerPredictor is loaded
- **THEN** SHALL detect 4 defect classes: 0=空鼓, 1=渗水, 2=脱落, 3=裂缝

#### Scenario: Model weights
- **WHEN** HiddenDangerPredictor is initialized
- **THEN** SHALL load `model_weights/best.pt`

### Requirement: floor_recognition.py Geometric Helpers
The `predictors/floor_recognition.py` module SHALL be a stateless geometric algorithm library providing `detect_columns`, `exclude_points`, `get_main_building`, `find_point`, and `cross_rate` functions. These SHALL be used by FloorPredictor only and SHALL NOT be independently callable as a predictor.

### Requirement: Lazy Predictor Loading
Predictors SHALL NOT be loaded at package import time. The `InspectionSkill._ensure_predictors()` method SHALL instantiate all 4 predictors on first call.

#### Scenario: No model files at import time
- **WHEN** `InspectionSkill()` is constructed
- **THEN** SHALL succeed without loading any models

#### Scenario: Model files missing at execution
- **WHEN** `execute()` is called but model files are absent
- **THEN** SHALL raise error during `_ensure_predictors()` call

#### Scenario: Subsequent calls reuse cached predictors
- **WHEN** `_ensure_predictors()` is called a second time
- **THEN** SHALL return immediately without re-loading models

## Dependencies
- **Depends on**: PyTorch, torchvision (EfficientNetV2, transforms), ultralytics (YOLO/OBB), OpenCV, numpy, `model_weights/` directory for `.pt`/`.pth` files
- **Depended on by**: `agent/skills/inspection_skill.py` (InspectionSkill), `agent/nodes.py` (DAG nodes), `llm/tools.py` (Tool wrappers)
