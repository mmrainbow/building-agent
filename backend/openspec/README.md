# OpenSpec — Building-Agent 规格文档

OpenSpec 规格定义了 Building-Agent 系统中每个能力的**需求（Requirements）**和**场景（Scenarios）**。规格反映代码的**当前行为**（非目标状态），随代码演进同步更新。

## 规格与代码路径对照

| Spec | 描述 | 对应代码路径 |
|------|------|------------|
| [agent-core](specs/agent-core/spec.md) | ReAct Agent 编排引擎 | `agent/orchestrator.py`, `agent/memory_manager.py` |
| [api](specs/api/spec.md) | FastAPI REST 接口 | `api/main.py`, `api/auth.py`, `api/schemas.py`, `api/chat.py` |
| [chat](specs/chat/spec.md) | 智能问答对话系统 | `llm/chat_core.py`, `db/chat_crud.py`, `services/chat_service.py` |
| [database](specs/database/spec.md) | 数据模型 (12 表) | `db/models.py`, `db/crud.py`, `db/SCHEMA.md` |
| [inspection](specs/inspection/spec.md) | 建筑外立面巡检 | `agent/skills/inspection_skill.py`, `agent/nodes.py`, `agent/graph.py` |
| [rag](specs/rag/spec.md) | 知识库检索增强 | `agent/rag.py`, `scripts/build_rag.py`, `chroma_db/` |
| [predictors](specs/predictors/spec.md) | CV 预测器模块 | `predictors/base.py`, `predictors/material.py`, `predictors/floor.py`, `predictors/added_floor.py`, `predictors/hidden_danger.py`, `predictors/floor_recognition.py` |
| [local-vl-model](specs/local-vl-model/spec.md) | 本地微调 VL 模型 | `llm/local_vl_model.py` |
| [feedback](specs/feedback/spec.md) | 反馈收集与导出 | `db/feedback_crud.py`, `db/models.py` (Feedback) |
| [app](specs/app/spec.md) | Gradio Web UI | `app.py`, `services/` (6 modules) |

## 阅读指南

每个 spec 文件遵循统一结构：

1. **Purpose** — 一句话描述该模块的职责
2. **Requirements** — 功能需求列表
   - `### Requirement: 需求名` — 一个独立的功能需求
   - `#### Scenario: 场景描述` — WHEN/THEN 形式的可验证场景
3. **Dependencies** — 依赖和被依赖关系

## 规格编写原则

- **反映当前行为，不描述目标**：规格应与代码一致。如需加新功能，先完成实现再更新规格。
- **可验证**：每个 Scenario 应有明确的 WHEN 条件和可观察的 THEN 结果。
- **不重复实现细节**：字段类型和代码级细节参考 `db/SCHEMA.md` 或源码。
- **中文描述**：所有 Purpose、Requirement、Scenario 使用中文（与项目约定一致）。

## 与 DEVELOPMENT_PLAN.md 的关系

| | OpenSpec Specs | DEVELOPMENT_PLAN.md |
|------|------|------|
| 视角 | 能力需求（Capability Requirements） | 演进路线图（Evolution Roadmap） |
| 时间 | 描述当前行为 | 规划未来阶段 |
| 粒度 | 需求 + 可验证场景 | 任务清单 + 架构决策 |
| 更新时机 | 代码变更后同步 | 每阶段完成后 |

## 变更流程

1. 在 `changes/` 下创建 delta spec，描述变更
2. 实现代码变更
3. 将 delta spec 合并到 `specs/` 中的对应 capability spec
4. 归档 change 记录到 `changes/archive/`
