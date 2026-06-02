# Local VL Model (本地微调视觉语言模型)

## Purpose
本地微调 Qwen2.5-VL 3B 模型调用模块 — 作为通义千问 API 的可选替代，用于生成巡检报告。通过 `LOCAL_VL_MODEL_ENABLED=true` 环境变量启用，启用后优先本地推理，失败时自动回退远程 LLM。

## Requirements

### Requirement: Lazy Singleton Initialization
The module SHALL expose `get_local_vl_client()` returning a `LocalVLModelClient` singleton. Model and processor SHALL NOT load until the first `generate()` call.

#### Scenario: First call
- **WHEN** `get_local_vl_client()` is called for the first time
- **THEN** SHALL create and cache a `LocalVLModelClient` instance (model and processor remain None)

#### Scenario: Subsequent calls
- **WHEN** `get_local_vl_client()` is called again
- **THEN** SHALL return the same cached instance

#### Scenario: Model directory missing at load time
- **WHEN** `load()` is called but `LOCAL_VL_MODEL_PATH` does not exist
- **THEN** SHALL raise `FileNotFoundError`

### Requirement: Environment Toggle
All local VL usage SHALL be gated behind `LOCAL_VL_MODEL_ENABLED` env var. The module SHALL expose `is_local_vl_enabled()` for runtime checks.

#### Scenario: Toggle enabled
- **WHEN** `LOCAL_VL_MODEL_ENABLED` is set to "true", "1", "yes", or "on"
- **THEN** `is_local_vl_enabled()` SHALL return `True`

#### Scenario: Toggle disabled
- **WHEN** `LOCAL_VL_MODEL_ENABLED` is unset or set to "false"
- **THEN** `is_local_vl_enabled()` SHALL return `False`, and local VL path SHALL never execute; system falls back to remote LLM

### Requirement: Model Loading
`LocalVLModelClient.load()` SHALL load Qwen2.5-VL from the configured path using `transformers.AutoProcessor` and `Qwen2_5_VLForConditionalGeneration`.

#### Scenario: Standard config
- **WHEN** `load()` is called with `device_map="auto"` and `torch_dtype="float16"`
- **THEN** SHALL load model on CUDA with float16 precision and set to `.eval()` mode

#### Scenario: Custom config via env
- **WHEN** `LOCAL_VL_DEVICE_MAP="cpu"` and `LOCAL_VL_TORCH_DTYPE="float32"`
- **THEN** SHALL load model on CPU with float32 precision

#### Scenario: max_pixels control
- **WHEN** `max_pixels` is set (default 131072)
- **THEN** SHALL pass to `AutoProcessor.from_pretrained()` to control image resolution

#### Scenario: Already loaded
- **WHEN** `load()` is called but model and processor are already non-None
- **THEN** SHALL return immediately without reloading

### Requirement: Image+Text Generation
`generate()` SHALL accept an image path, text prompt, max_new_tokens, and temperature; and return a decoded string.

#### Scenario: Greedy decoding
- **WHEN** `generate()` is called with `temperature=0`
- **THEN** SHALL run greedy decoding (`do_sample=False`)

#### Scenario: Sampling mode
- **WHEN** `generate()` is called with `temperature>0`
- **THEN** SHALL run sampling with `do_sample=True`

#### Scenario: Prompt token trimming
- **WHEN** `model.generate()` returns token IDs
- **THEN** SHALL trim the input prompt tokens from output, returning only the generated portion

#### Scenario: Image format handling
- **WHEN** any image path is provided
- **THEN** SHALL open via PIL `Image.open().convert("RGB")` and apply chat template with `{"type": "image"}` + `{"type": "text"}`

### Requirement: Inspection Report Generation
`generate_report()` SHALL be a convenience method combining `build_inspection_prompt()` with `generate()`, producing a constrained Chinese inspection report.

#### Scenario: Defects present
- **WHEN** `generate_report()` is called with structured CV results containing defects
- **THEN** report SHALL include findings with defect IDs from the CV pipeline

#### Scenario: No defects
- **WHEN** `generate_report()` is called with empty defects list
- **THEN** report SHALL include "无明显隐患"

#### Scenario: Output constraints
- **WHEN** report is generated
- **THEN** output SHALL be 120-220 Chinese characters, SHALL NOT contain markdown, section headers, or area unit conversions (area is pixel-based)

#### Scenario: No fabrication
- **WHEN** CV results are limited
- **THEN** report SHALL NOT invent facts beyond the provided detection data

### Requirement: Prompt Template
`build_inspection_prompt()` SHALL construct a structured prompt from CV detection results including material, floor, has_extension, and defects.

#### Scenario: Defect formatting
- **WHEN** defects list is provided
- **THEN** SHALL format each as `- 序号{id}：{type}，像素面积约 {area:.1f}px`

#### Scenario: Role definition
- **WHEN** prompt is generated
- **THEN** SHALL include "你是住建外立面巡检报告助手" role definition and 5 explicit constraints (pixel-only areas, no fabrication, 120-220 chars, conclusion+risks+recommendations, no markdown/headers)

### Requirement: Top-Level Convenience Function
`generate_local_inspection_report(image_path, material, floor, has_extension, defects)` SHALL be a module-level shortcut that internally calls `get_local_vl_client().generate_report()`.

#### Scenario: Direct module call
- **WHEN** `generate_local_inspection_report()` is called from `agent/nodes.py`
- **THEN** SHALL return the same result as `get_local_vl_client().generate_report()`

## Dependencies
- **Depends on**: `transformers` (AutoProcessor, Qwen2_5_VLForConditionalGeneration), `torch`, `PIL` (Pillow), `accelerate`, `safetensors`, local merged model directory at `LOCAL_VL_MODEL_PATH`
- **Depended on by**: `agent/nodes.py` (DAG report node fallback), `agent/skills/inspection_skill.py` (optional report generation)
