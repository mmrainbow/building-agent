# Building-Agent 项目演进开发路线图

> 基于代码库全面分析生成 | 生成日期: 2026-05-26 | 最后更新: 2026-05-26 (阶段0完成)

---

## 零、执行进度

| 阶段 | 状态 | 完成日期 |
|------|------|---------|
| 阶段0: 基础夯实 | **已完成** | 2026-05-26 |
| 阶段0.5: 数据模型架构补强 | **已完成** | 2026-05-26 |
| 阶段1: Agent 框架 + RAG + 对话系统 | **已完成** | 2026-06-01 |
| 阶段1.5: 本地 LLM 服务化 + 架构精简 | **已完成** | 2026-06-02 |
| 阶段2: 多 Agent 协同 | **已完成** | 2026-06-03 |
| 阶段2.5: 前后端分离 (Vue 3 + FastAPI) | **已完成** | 2026-06-03 |
| 阶段2.6: Memory 系统重构 (三层模型) | **已完成** | 2026-06-06 |
| 阶段3: 反馈系统 | 待开始 | — |
| 阶段4: 服务化部署 (Docker/CICD) | 待开始 | — |

---

## 一、代码库全面分析

### 1.1 项目概述

**核心业务**: AI 驱动的建筑外立面巡检系统。用户上传建筑图片，系统通过 CV 模型（YOLO、EfficientNet）自动检测建筑材质、楼层数、违建加层、外墙隐患（空鼓/渗水/脱落/裂缝），并调用 Ollama 本地 LLM 生成中文巡检报告。

**服务对象**: 住建管理部门为主，普通用户随拍随用为辅。

### 1.2 现有架构

当前为 **多 Agent 协同** 架构：

```
┌─────────────────────────────────────────────────────────┐
│  用户入口                                               │
│  ├── app.py           Gradio Web UI (4 Tab)              │
│  └── api/main.py      FastAPI REST API                   │
├─────────────────────────────────────────────────────────┤
│  Manager Agent (通义千问 API)                            │
│  ├── agent/orchestrator.py   ReAct 推理 + 工具调度        │
│  ├── agent/memory_manager.py 三层记忆管理 (LLM提取+向量检索)│
│  └── llm/client.py           OpenAI 兼容客户端            │
├─────────────────────────────────────────────────────────┤
│  工具层 (6 个 Tool)                                     │
│  ├── classify_material / estimate_floors                 │
│  ├── detect_extension / detect_defects                   │
│  ├── search_knowledge (ChromaDB RAG)                     │
│  └── generate_report → Report Agent                     │
├─────────────────────────────────────────────────────────┤
│  Report Agent (本地微调 Qwen2.5-VL)                      │
│  ├── scripts/launch_local_llm.py   FastAPI 服务 (:8000)  │
│  └── llm/local_vl_model.py        模型加载 + 推理        │
├─────────────────────────────────────────────────────────┤
│  CV 模型层                                              │
│  └── predictors/   YOLO + EfficientNetV2 (本地 GPU)      │
├─────────────────────────────────────────────────────────┤
│  数据层                                                 │
│  └── db/            SQLAlchemy ORM (12 表)              │
└─────────────────────────────────────────────────────────┘
```

**两条巡检路径 (Path C 已删除):**
- **图像巡检 Tab**: InspectionSkill — 多图收集≥3张 → 全量CV → LLM报告
- **智能问答 Tab**: Manager Agent — 推理 → 自主选Tool → 需要时委托 Report Agent

**关键技术组件**:
| 类别 | 技术 | 用途 |
|------|------|------|
| AI 编排 | LangGraph | 定义检测 DAG，并行执行材质/楼层/加层/隐患四个节点 |
| CV 模型 | YOLO (ultralytics) | 建筑主体检测、外部物体检测、隐患 OBB 检测 |
| CV 模型 | EfficientNetV2 (torchvision) | 材质多标签分类、加层二分类 |
| 几何算法 | RANSAC + 自定义聚类 | 楼层数统计算法 (基于窗户排列) |
| LLM | Ollama (qwen2:1.5b) | 巡检报告生成 + 智能问答 |
| 数据库 | SQLAlchemy 2.0 + SQLite/MySQL | 用户、巡检记录、隐患数据持久化 |
| API | FastAPI + HTTP Basic Auth | RESTful 接口 |
| UI | Gradio 4.0 | Web 交互界面 |
| 密码 | bcrypt | 密码哈希 |
| 导出 | openpyxl | Excel 报告导出 |
| 可视化 | Plotly | 统计图表 |

### 1.3 可复用部分 (当前状态)

| 模块 | 状态 |
|------|------|
| `predictors/` | ✅ 全部 5 个预测器可复用，无需改造 |
| `db/models.py` | ✅ 12 表，User/Feedback/Knowledge 表已扩展 |
| `db/*_crud.py` | ✅ 5 个 CRUD 模块，含 feedback/memory/chat |
| `agent/orchestrator.py` | ✅ Manager Agent — ReAct 编排 |
| `llm/client.py` | ✅ OpenAI 兼容，native+prompt 双模式 |
| `llm/tools.py` | ✅ 6 个 Tool，含 generate_report |
| `api/` | ✅ JWT 认证 + 角色权限 |

### 1.4 已修复的问题

| 问题 | 严重程度 | 状态 |
|------|---------|------|
| `app.py` 单体巨石 | 高 | **已修复**: 拆为 `services/` 下 5 个模块 |
| 认证机制不统一 | 高 | **已修复**: JWT Bearer + 角色权限 |
| 无测试 | 中 | **已修复**: 11 个测试文件 |
| 无知识库 | 中 | **已修复**: ChromaDB + RAG |
| Agent 编排简单 | 低 | **已修复**: ReAct Agent + 多Agent协同 |
| 无反馈机制 | 中 | 待实现 (阶段3) |
| 无日志系统 | 中 | 待实现 |
| 无 Docker/CICD | 中 | 待实现 (阶段4) |

---

## 二、目标功能定义与实现建议

### 2.1 用户管理：JWT 认证与角色权限

**现状**: 已有 `User` 模型 (id/username/password_hash/role)、bcrypt 密码哈希、UserRole 枚举 (inspector/admin)，注册和登录逻辑在 `db/crud.py` 中。但认证是 session-based (Gradio) 和 HTTP Basic (FastAPI)，无 JWT。

**实现方案**:
- 新增 `PyJWT` 依赖，在 `api/` 下新增 `auth.py` 模块
- 实现 JWT 签发 (`create_access_token`) 和验证 (`get_current_user` 依赖注入)
- 角色权限通过 FastAPI Dependency 实现: `RequireRole(UserRole.admin)`
- Gradio 端改为在请求头携带 JWT，或保留 session state 但后端统一走 JWT 验证
- Token 刷新机制: access token 30分钟，refresh token 7天

**新增文件**:
- `api/auth.py` — JWT 工具函数和 FastAPI 依赖
- `api/schemas.py` — Pydantic 请求/响应模型

**技术选型**: `python-jose[cryptography]` 或 `PyJWT`，推荐前者（更完整的 JWT 生态支持）。

### 2.2 数据库搭建

**现状**: 已有完整的 SQLAlchemy 2.0 配置，支持 SQLite (默认) 和 MySQL。`database.py` 实现了自动建库 (`CREATE DATABASE IF NOT EXISTS`)，`models.py` 有 3 个表。

**建议**: 保持现有 SQLAlchemy + SQLite/MySQL 双模式不变。对于新功能，需要扩展以下表:

**新增/修改表结构**:
```sql
-- 反馈表 (新增)
feedback (
    id INTEGER PK,
    user_id INTEGER FK→users,
    record_id INTEGER FK→inspection_records,
    feedback_type VARCHAR(20),     -- 'correction' | 'rating' | 'comment'
    target_field VARCHAR(50),       -- 被纠错的字段, 如 'material', 'defects[0].type'
    original_value TEXT,            -- 模型原始输出
    corrected_value TEXT,           -- 用户修正后的值
    rating INTEGER CHECK(1-5),      -- 1-5星评分
    comment TEXT,                    -- 文字评价
    created_at DATETIME
)

-- 知识库文档表 (新增)
knowledge_documents (
    id INTEGER PK,
    title VARCHAR(255),
    content TEXT,
    source_type VARCHAR(50),       -- 'regulation' | 'manual' | 'report_template'
    chunk_count INTEGER,
    embedding_model VARCHAR(100),
    created_at DATETIME
)

-- 知识库向量块表 (新增)
knowledge_chunks (
    id INTEGER PK,
    document_id INTEGER FK→knowledge_documents,
    chunk_index INTEGER,
    content TEXT,
    embedding BLOB,                 -- 向量序列化存储
    metadata JSON
)

-- User 表扩展字段
ALTER TABLE users ADD COLUMN last_login DATETIME;
ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT TRUE;
```

### 2.3 人工反馈闭环

**设计目标**: 用户在查看巡检结果时可以对 AI 的判断进行纠错或评分，反馈数据被收集并结构化存储，支持后续导出为模型微调数据集。

**数据流**:
```
用户查看报告 → 发现错误（如材质识别错误） → 提交修正
→ feedback 表存储 → 管理员可导出为 JSONL/CSV 微调数据集
```

**接口设计**:
```
POST   /api/feedback              # 提交反馈
GET    /api/feedback              # 管理员查看所有反馈 (分页)
GET    /api/feedback/export       # 导出为微调数据集 (JSONL/CSV)
GET    /api/feedback/stats        # 反馈统计 (准确率变化趋势)
```

**实现要点**:
- 前端 (Gradio): 在报告展示区增加 "纠错" 按钮和 "评分" 组件
- 导出格式: JSONL (每行一个 `{"prompt": "...", "completion": "..."}` 格式，适配微调)
- 去重策略: 同一用户对同一记录的同一字段，以最新提交为准
- 可选: 当反馈积累到一定量 (>100条)，触发人工审核流程

**新增文件**:
- `api/feedback.py` — 反馈 API 路由
- `db/feedback_crud.py` — 反馈 CRUD 操作
- `export/feedback_exporter.py` — 数据集导出工具

### 2.4 微服务拆分

**评估结论**: 当前项目规模 (约2000行 Python) 尚不需要完整的微服务拆分。但为支撑后续扩展，建议采用 **模块化服务 + 进程内通信** 的过渡方案，为未来真正的微服务化做好准备。

**拆分方案 (三阶段演进)**:

```
阶段1 (当前→模块化):
  保持单体部署，但 app.py 按业务模块拆分为:
  ├── services/
  │   ├── auth_service.py      # 认证逻辑
  │   ├── inspection_service.py # 巡检核心流程
  │   ├── feedback_service.py  # 反馈收集
  │   └── statistics_service.py # 统计分析
  └── app.py 变为薄路由层

阶段2 (模块化→服务化):
  按业务边界拆分为独立进程:
  ├── auth-service        (端口8001)  FastAPI, JWT签发/验证
  ├── inspection-service  (端口8002)  CV推理+LLM报告
  ├── feedback-service    (端口8003)  反馈收集/导出
  └── gateway             (端口8000)  API网关(nginx/FastAPI), 路由+限流

阶段3 (服务化→微服务):
  引入服务发现和异步消息:
  - 同步通信: gRPC (推理请求低延迟需要)
  - 异步通信: Redis Pub/Sub 或 RabbitMQ (反馈收集、统计更新)
  - 服务注册: Consul 或 Kubernetes Service
```

**阶段1 推荐立即执行**，文件改动小、收益明显（app.py 从530行缩到~100行）。

**服务间通信建议**:
| 场景 | 方式 | 理由 |
|------|------|------|
| 推理请求 (inspection) | gRPC | 低延迟、强类型、支持流式 |
| 反馈提交 | REST | 简单、无状态 |
| 统计更新事件 | Redis Pub/Sub | 解耦、异步、轻量 |
| 知识库索引更新 | 消息队列 (RabbitMQ) | 持久化、重试机制 |

### 2.5 多 Agent 协同 ✅ 已完成 2026-06-02

**架构: Manager Agent (通义千问) + Report Agent (本地微调 Qwen2.5-VL)**

```
用户 ──→ Manager Agent (通义千问) ──→ CV 工具 (本地)
               │                        ├─ classify_material
               │                        ├─ estimate_floors
               │                        ├─ detect_extension
               │                        ├─ detect_defects
               │                        └─ search_knowledge
               │
               └──→ generate_report ──→ Report Agent (本地 Qwen2.5-VL)
                                             └─ localhost:8000
```

**设计原则**: 让每个模型做自己擅长的事。
- Manager Agent (通义千问 API): 推理、意图理解、工具调度 — 原生支持 function calling
- Report Agent (本地 Qwen2.5-VL): 看图 + 结构化数据 → 专业中文巡检报告 — 微调训练的目标

**实现要点**:
- `llm/tools.py`: 新增第 6 个 Tool `generate_report`，通过 HTTP 调用 `localhost:8000/v1/report`
- `scripts/launch_local_llm.py`: Report Agent 独立进程，FastAPI + transformers 加载模型
- `agent/orchestrator.py`: System Prompt 重写为 Manager 角色，明确报告委托规则
- CV 工具在本地 GPU 运行，Manager 通过 function calling 调度
- Manager 默认使用远程 API (`USE_LOCAL_LLM=false`)
- 简单问答直接回复，不需要调用 Report Agent（如"你好"、"什么材质"）

**已删除的旧代码**:
- `main.py` (CLI入口)
- `agent/graph.py`, `agent/nodes.py`, `agent/state.py` (LangGraph DAG)
- `services/inspection_service.py` (旧巡检服务)
- `scripts/launch_vllm.py/.bat` (Windows 不支持 vLLM)

**新增文件**:
- `scripts/launch_local_llm.py` — Report Agent 服务
- `llm/react_parser.py` — ReAct 文本解析 (prompt 回退模式)
- `qwen2_5_vl_3b_building_merged/README.md` — 模型文档

**Agent 通信协议 (JSON 消息格式)**:

```json
{
  "message_id": "uuid-v4",
  "session_id": "session-xxx",
  "timestamp": "2026-05-26T10:00:00Z",
  "from_agent": "orchestrator",
  "to_agent": "material_agent",
  "type": "task_request",
  "payload": {
    "task": "classify_material",
    "image_ref": "s3://bucket/image_001.jpg",
    "parameters": { "confidence_threshold": 0.3 }
  },
  "reply_to": "orchestrator.result_queue"
}
```

```json
{
  "message_id": "uuid-v4",
  "session_id": "session-xxx",
  "timestamp": "2026-05-26T10:00:02Z",
  "from_agent": "material_agent",
  "to_agent": "orchestrator",
  "type": "task_result",
  "status": "success",
  "payload": {
    "result": "Coating,Face Brick",
    "confidence": 0.87,
    "processing_time_ms": 450
  }
}
```

**Agent 注册与发现 (本地模式)**:
```python
# agent/registry.py
from typing import Dict, Callable

class AgentRegistry:
    """本地 Agent 注册中心 (进程内)"""
    _agents: Dict[str, Callable] = {}

    @classmethod
    def register(cls, name: str, handler: Callable):
        cls._agents[name] = handler

    @classmethod
    def dispatch(cls, name: str, payload: dict) -> dict:
        agent = cls._agents.get(name)
        if not agent:
            return {"status": "error", "error": f"Agent '{name}' not found"}
        return agent(payload)
```

**实现路径**: 在 LangGraph 基础上增加 Agent 封装层，每个节点变为独立 Agent，通过 Registry 注册和调度。保留现有的 DAG 执行模式，但增加 Agent 间的协商能力（如 Material Agent 发现置信度低时可主动请求 Defect Agent 交叉验证）。

**新增文件**:
- `agent/registry.py` — Agent 注册与调度
- `agent/protocol.py` — 消息格式定义 (Pydantic models)
- `agent/orchestrator.py` — 主控 Agent 逻辑

### 2.6 知识库增强

**技术选型: ChromaDB** (轻量级嵌入式向量数据库)

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| **ChromaDB** | 零运维、Python原生、嵌入式 | 大规模性能不如ES | 本项目首选 |
| FAISS | 速度极快 | 无持久化、需手动管理 | 纯内存检索 |
| Elasticsearch | 全文+向量混合检索 | 运维成本高 | 企业级大规模 |
| LanceDB | 列式存储、高性能 | 生态较新 | 大规模向量检索 |

**推荐理由**: ChromaDB 可嵌入 Python 进程，无需额外部署，支持持久化，自带 embedding 生成（可用本地 Ollama 模型），与现有技术栈契合。

**文档摄入流程**:
```
上传文档(PDF/Word/Markdown)
  → 文档解析 (unstructured / pypdf)
  → 文本分块 (LangChain TextSplitter, chunk_size=500, overlap=50)
  → 向量化 (Ollama embedding: nomic-embed-text)
  → 存入 ChromaDB Collection
```

**检索增强生成 (RAG) 流程**:
```
用户提问 → 问题向量化 → ChromaDB 相似度检索 (top_k=5)
  → 拼接上下文 → LLM 生成回答 (限制基于检索内容)
```

**接口设计**:
```
POST   /api/knowledge/upload       # 上传文档 (支持 PDF/DOCX/MD/TXT)
GET    /api/knowledge/documents    # 列出已入库文档
DELETE /api/knowledge/documents/{id} # 删除文档
POST   /api/knowledge/search       # 检索 (query: str, top_k: int)
POST   /api/chat/rag               # 基于知识库的问答 (已有 /api/chat，增强)
```

**新增依赖**: `chromadb`, `langchain-text-splitters`, `unstructured` 或 `pypdf`

**新增文件**:
- `knowledge/` 目录
  - `embedding.py` — 向量化引擎
  - `loader.py` — 文档解析和分块
  - `retriever.py` — 检索接口
  - `vector_store.py` — ChromaDB 管理
- `api/knowledge.py` — 知识库 API 路由

---

## 三、分阶段开发路线图

### 阶段0: 基础夯实 (1-2周, 1-2人) ✅ 已完成 2026-05-26

**目标**: 建立工程化基础，为后续功能铺路。

- [x] **模块拆分 app.py** — 将 530 行巨石拆分为 `services/` 目录下的独立模块 (auth_service.py, inspection_service.py, history_service.py, statistics_service.py, chat_service.py)。结果: app.py 534→146行 (-73%) — **复杂度: 中, 可 CC**
- [x] **统一认证为 JWT** — `api/auth.py` 实现 JWT 签发/验证/角色依赖注入; `api/schemas.py` 定义 Pydantic 模型; `api/main.py` 使用 JWT 替代 HTTP Basic。新增 `/register`, `/login`, `/token`, `/token/refresh` 端点 — **复杂度: 中, 可 CC**
- [ ] **添加结构化日志** — 引入 `loguru` 或标准库 `logging`，在关键路径 (推理、数据库、文件处理) 添加日志 — **复杂度: 低, 可 CC**
- [x] **添加健康检查接口** — `/health` 返回数据库连接状态、Ollama 可达性、模型文件完整性 — **复杂度: 低, 可 CC**
- [ ] **添加上传文件校验** — 类型 (仅图片)、大小限制 (10MB)、空文件检查 — **复杂度: 低, 可 CC**
- [x] **API 基础测试** — `tests/` 目录 (27 个用例)，覆盖 `/predict`, `/history`, `/statistics`, `/health`, `/register`, `/token`, `/token/refresh`，使用 `pytest` + `httpx` TestClient。含权限隔离测试 — **复杂度: 中, 可 CC**

> **架构决策点**: JWT 密钥管理 — 选项A: 环境变量 (简单); 选项B: 配置文件 + 轮转策略 (安全)。已选A，通过 `JWT_SECRET_KEY` 环境变量配置。

### 阶段0.5: 数据模型架构补强 (半天) ✅ 已完成 2026-05-26

**目标**: 建立承载对话记忆、反馈、知识库的完整数据骨架，避免后续推倒重来。

- [x] **扩展 User 模型** — 新增 `last_login_at`, `is_active` 字段，新增 `conversations`, `memories`, `feedbacks`, `preferences` 关系 — **复杂度: 低, 可 CC**
- [x] **对话 + 消息表** — `Conversation` (会话) 和 `ChatMessage` (消息) 模型，含 `conversation_id` 外键和级联删除 — **复杂度: 中, 可 CC**
- [x] **长期记忆表** — `ConversationMemory` 模型，支持 `memory_type` 分类 (user_fact/building_info/preference/summary)，`importance` 权重，`chroma_id` 预留向量检索 — **复杂度: 中, 可 CC**
- [x] **用户偏好表** — `UserPreference` 模型，1:1 绑定 User，存储 `report_style`, `preferred_model` — **复杂度: 低, 可 CC**
- [x] **反馈表** — `Feedback` 模型，支持巡检纠错和对话评分两种类型，upsert 策略防止重复 — **复杂度: 中, 可 CC**
- [x] **知识库表** — `KnowledgeDocument` + `KnowledgeChunk` 模型，预留 `chroma_id` 向量检索接口 — **复杂度: 中, 可 CC**
- [x] **新增 CRUD 模块** — `db/chat_crud.py` (对话/消息), `db/memory_crud.py` (记忆/检索), `db/feedback_crud.py` (反馈/导出) — **复杂度: 中, 可 CC**
- [x] **测试覆盖** — `tests/test_models.py` (8 个用例) 覆盖新表创建、对话CRUD、记忆检索、反馈 upsert — **复杂度: 中, 可 CC**

> **架构决策**: 记忆向量存储选 ChromaDB（阶段1B集成），当前用 SQLite LIKE 做关键词过渡检索；记忆提取方式选 LLM 自动提取（每轮对话后用小 prompt 提取关键事实）；对话存储选无限存储（全量持久化，30天/200条后可选摘要压缩）。

### 阶段1: Agent 框架 + RAG + 对话系统 (2-3周, 1-2人) ✅ 已完成 2026-06-01

**目标**: 通义千问 API 替代本地 Ollama，Predictor 封装为 Tool 让 AI 自主选择调用，打通 思维链 + Memory + RAG。

**已完成的关键任务**:
- LLM 客户端 (`llm/client.py`): 通义千问 API，OpenAI 兼容，支持 native + prompt 双模式
- 5 个 Tool (`llm/tools.py`): 4 CV + search_knowledge
- ReAct Agent (`agent/orchestrator.py`): LLM 自主选择 Tool，最大 10 轮循环
- MemoryManager: 短期 20 条 + 长期记忆提取
- ChromaDB RAG: 建筑规范语义检索
- Chat API + Gradio 智能问答 Tab
- InspectionSkill: 多图巡检独立工作流
- 本地 VL 模型 (`llm/local_vl_model.py`): transformers 加载 Qwen2.5-VL

### 阶段1.5: 本地 LLM 服务化 + 架构精简 (0.5天) ✅ 已完成 2026-06-02

**目标**: 将本地模型部署为 OpenAI 兼容服务，删除不再使用的 CLI/DAG 路径。

- [x] **本地模型服务化** — `scripts/launch_local_llm.py`: FastAPI + transformers 加载 Qwen2.5-VL，暴露 `/v1/chat/completions` 和 `/v1/report` 端点
- [x] **LLMClient 双模式** — `tool_call_mode=native` (原生 function calling) / `prompt` (ReAct 文本解析)
- [x] **ReAct 文本解析器** — `llm/react_parser.py`: 从模型输出提取 `<tool_call>` 标记
- [x] **删除废弃路径** — 移除 `main.py`, `agent/graph.py`, `agent/nodes.py`, `agent/state.py`, `services/inspection_service.py`, `tests/test_predict.py`
- [x] **Windows 兼容** — vLLM 不支持 Windows，改用 FastAPI + transformers 自建服务

### 阶段2: 多 Agent 协同 ✅ 已完成 2026-06-03

**目标**: Manager Agent (通义千问) + Report Agent (本地微调模型) 各司其职。

**已完成**:

```
用户 ──→ Manager Agent (通义千问) ──→ CV 工具 (本地: 4 CV + RAG)
               │                        
               └──→ generate_report ──→ Report Agent (本地 Qwen2.5-VL, :8000)
```

- [x] **Manager + Report 分离** — Manager 用远程 API 推理+工具调度，Report 用本地模型生成报告
- [x] **generate_report 工具** — `llm/tools.py` 新增第 6 个 Tool，通过 HTTP 调用 `localhost:8000/v1/report`
- [x] **Report Agent 服务** — `scripts/launch_local_llm.py` 独立进程，`/v1/report` 端点接收图片+数据→返回报告
- [x] **System Prompt 重写** — Manager 角色明确，含报告委托规则（简单问答不调用 Report Agent）
- [x] **配置切换** — `USE_LOCAL_LLM=false`，Manager 默认远程 API，`REPORT_AGENT_URL` 指向本地
- [x] **架构精简** — 删除 Path C: `main.py`, `agent/graph.py/nodes.py/state.py`, `services/inspection_service.py`

**待完成**:

- [ ] **Agent 注册中心** — `agent/registry.py`: Agent 注册/发现/调度 — **复杂度: 中, 可 CC**
- [ ] **Agent 通信协议** — `agent/protocol.py`: 标准化 JSON 消息格式 — **复杂度: 低, 可 CC**
- [ ] **ReviewAgent** — 审核其他 Agent 输出，基于知识库检查报告一致性 — **复杂度: 高, 可 CC**
- [ ] **Report Agent 多路召回** — 同时生成多份报告供对比选择

> **架构决策**: Manager 使用通义千问 API 因原生支持 function calling；Report Agent 使用本地模型因微调训练的目标就是报告生成。两者通过 HTTP 通信，可独立扩展。

### 阶段2.5: 前后端分离 (Vue 3 + FastAPI) ✅ 已完成 2026-06-03

**目标**: Gradio UI 替换为 Vue 3 单页应用，FastAPI 作为纯后端 API。

- [x] **补充 API 端点** — `POST /inspection/multi`、`GET /history/{id}/export`、`GET /agent/status`、`POST /chat/send/stream` (SSE 流式 CoT)
- [x] **Vue 3 脚手架** — Vite + Element Plus + Axios + Pinia + Vue Router
- [x] **智能问答页面** — SSE 流式 CoT 可视化、对话列表管理、图片上传
- [x] **图像巡检页面** — 多图上传 Gallery、标注图展示、报告渲染
- [x] **历史记录页面** — 表格 + 详情 + Excel 导出
- [x] **Agent 监控页面** — 三 Agent 状态卡片 + Token 圆环
- [x] **项目重构** — 后端文件移入 `backend/`，前端独立 `frontend/`
- [x] **Defect 表重构** — 移除 `image_id`，直连 `chat_images`
- [x] **图文并茂报告** — 标注缺陷框 + Gallery 展示 + `<img>` 嵌入

**技术栈**: Vue 3 + Vite + Element Plus + Pinia, FastAPI + SSE + CORS

### 阶段2.6: Memory 系统重构 (1天) ✅ 已完成 2026-06-06

**目标**: 将双层记忆升级为三层认知记忆模型。

- [x] **Memory Consolidation** — LLM 轻量判断是否值得提取 + Memory Agent 一次性提取 ≤3 条记忆 + 冲突检测 (同 key upsert) — **复杂度: 中**
- [x] **Summary Buffer** — 旧消息先用 Memory Agent 生成 100-200 字摘要再删除，替代直接删除 — **复杂度: 中**
- [x] **Vector Retrieval** — ChromaDB 语义检索 + 混合排序公式 `0.3R+0.5R+0.2I`，不可用回退 SQLite LIKE — **复杂度: 高**
- [x] **Reflection** — ≥20 条记忆时异步触发 LLM 生成高阶洞察 (insight)，importance≥8 — **复杂度: 中**
- [x] **Memory 面板** — 前端 Chat 页面 🧠 抽屉，查看/删除记忆 — **复杂度: 低**

### 阶段3: 反馈系统 (1周, 1人)

**目标**: 收集用户纠错和评分数据，建立数据飞轮。

- [ ] **Feedback API** — `api/feedback.py`: POST/GET 反馈，GET 统计 (表 + CRUD 已在 0.5) — **复杂度: 中, 可 CC**
- [ ] **Gradio 反馈 UI** — 报告详情 + 对话消息旁增加纠错/评分 — **复杂度: 中, 可 CC**

### 阶段4: 服务化部署 (1-2周, 1人)

**目标**: 支撑团队协作和实际部署。

- [ ] **Docker Compose 编排** — `docker-compose.yml`: app + Ollama + ChromaDB + MySQL(可选) — **复杂度: 中, 可 CC**
- [ ] **Nginx 反向代理** — 统一入口 + 静态文件服务 + 速率限制 — **复杂度: 低, 可 CC**
- [ ] **FastAPI 中间件** — CORS、请求日志、速率限制、全局异常处理 — **复杂度: 低, 可 CC**
- [ ] **CI/CD 配置** — GitHub Actions: lint (ruff) + test (pytest) + docker build — **复杂度: 中, 可 CC**
- [ ] **模型管理脚本** — `scripts/download_models.sh`: 自动从远程拉取模型权重 — **复杂度: 低, 可 CC**
- [ ] **启动自检脚本** — `scripts/healthcheck.py`: 数据库/模型文件/Ollama 完整性检查 — **复杂度: 低, 可 CC**

### 阶段5: 前后端分离 + 高级特性 (按需)

**目标**: 增强系统能力和用户体验。

- [ ] **模型提示模板版本化** — 报告生成 prompt 模板管理 + A/B 对比 — **复杂度: 中, 可 CC**
- [ ] **轻量观测指标** — Prometheus metrics: 请求耗时、失败率、模型调用成功率 — **复杂度: 中, 可 CC**
- [ ] **异步推理队列** — Celery/Redis 队列处理耗时推理，避免 HTTP 超时 — **复杂度: 高, 可 CC**
- [ ] **移动端适配** — PWA 或 React Native 轻量客户端 — **复杂度: 高, 不可 CC** (需要前端专业开发)
- [ ] **模型微调管线** — 基于收集的反馈数据，自动触发模型微调 (LoRA) — **复杂度: 高, 部分可 CC**

---

## 四、AGENT 团队协作指南

### 4.1 上下文共享方案: AGENT.md

在项目根目录维护 `AGENT.md` 文件作为共享上下文入口。AGENT 会自动读取 `CLAUDE.md`，其他 Agent 工具可配置读取 `AGENT.md`。团队统一使用 `AGENT.md` 作为文件名，兼容多种 AI 编码助手。

**仓库中已创建 `AGENT.md`**，内容如下:

```markdown
# AGENT.md — Building-Agent 项目上下文

## 项目简介
AI 驱动的建筑外立面巡检系统。技术栈: Python 3.10+, LangGraph, FastAPI,
Gradio, SQLAlchemy, Ollama (qwen2:1.5b), YOLO, PyTorch。

## 项目结构
- agent/     LangGraph 工作流编排
- predictors/ CV模型预测器 (材质/楼层/加层/隐患)
- db/        SQLAlchemy ORM + CRUD
- api/       FastAPI 路由
- app.py     Gradio Web UI (正在拆分中)
- knowledge/ 知识库 (ChromaDB RAG)
- services/  业务逻辑层
- tests/     测试

## 开发约定
- 所有文案和注释使用中文
- Python 类型注解使用新语法 (list[dict] 而非 List[Dict])
- 使用 bcrypt 进行密码处理，JWT 进行 API 认证
- 数据库默认 SQLite，生产环境 MySQL
- LLM 调用通过 Ollama 本地 API，模型: qwen2:1.5b
- 环境变量命名: UPPER_SNAKE_CASE

## 当前阶段
阶段2 完成 — 多Agent协同 (Manager+Memory+Report)+ 前后端分离 (Vue 3 + FastAPI)。下一步: 阶段3 反馈系统。

## 禁止事项
- 不要删除或修改 model_weights/ 下的模型权重文件
- 不要提交 .env 文件
- 不要在代码中硬编码密码或密钥
- 修改数据库模型后必须同时更新迁移脚本

## 相关文件
- DEVELOPMENT_PLAN.md  完整开发路线图
- history_mk/PROJECT_CO_BUILD.md   项目共建文档
- .env.example          环境变量模板
```

### 4.2 任务提示词模板

以下模板可直接复制给 Claude Code，开发者只需填入 `[方括号]` 中的参数。

#### 模板1: 实现 API 端点

```
在 `api/` 目录下新建 `[endpoint_name].py` 文件。

## 任务
实现 [功能描述，如: "用户反馈提交和查询 API"]

## 参考实现
参考 `api/main.py` 中的路由定义风格和 `db/crud.py` 中的数据库操作模式。

## 要求
- 使用 FastAPI 的 APIRouter
- Pydantic 模型定义在 api/schemas.py
- 数据库操作放在 db/[name]_crud.py
- 添加 JWT 权限校验 (从 api/auth.py 导入 get_current_user)
- 添加请求/响应示例的 docstring
- 不需要写测试 (测试任务分离)

## 涉及文件
- api/schemas.py: 新增 [SchemaName]Request, [SchemaName]Response
- db/models.py: [如果需要新表] 新增 [ModelName] 模型
- db/[name]_crud.py: 新建，包含 [列出CRUD函数]
```

#### 模板2: 模块拆分

```
将 `[源文件路径]` 中的 `[功能名]` 相关代码提取到 `[目标文件路径]`。

## 任务
从 [源文件] 中提取 [具体功能] (约 [行数范围] 行)，移动到新模块 [目标文件]。

## 要求
- 保持原有函数签名和返回值不变
- 更新所有 import 路径
- 在 [源文件] 中保留对提取模块的 import 和调用
- 不要修改业务逻辑，仅做代码搬迁
- 完成后运行 `python -m pytest tests/ -x` 确保不引入回归

## 涉及文件
- 源文件: [path]
- 目标文件: [path]
- 需要更新 import 的文件: [列出]
```

#### 模板3: 添加新 Predictor

```
参考 `predictors/material.py` 的实现模式，新建一个预测器。

## 任务
实现 [预测器名称] 用于 [功能描述]

## 基类
继承 `predictors/base.py` 中的 `BasePredictor`

## 模型信息
- 模型架构: [YOLO / EfficientNet / 其他]
- 模型权重路径: model_weights/[weights_file]
- 输入: [描述]
- 输出格式: [描述，如: List[str], List[dict]]

## 要求
- 实现 predict(self, images: list) -> list 方法
- 使用 self.device 和 self.batch_size (继承自 BasePredictor)
- 在 agent/nodes.py 中注册新的调用节点
- 在 agent/graph.py 中添加工作流边
- 在 agent/state.py 的 InspectionState 中添加新字段
```

#### 模板4: 编写测试

```
为 `[模块路径]` 编写 pytest 测试。

## 任务
覆盖 [模块名] 的所有公开函数。

## 测试文件
tests/test_[module_name].py

## 要求
- 使用 pytest + httpx (API 测试) 或直接调用 (单测)
- Mock 外部依赖 (Ollama, YOLO 模型)
- 每个函数至少 2 个测试: 正常路径 + 异常路径
- 使用 fixtures 管理测试数据
- 测试类名: Test[FeatureName]
```

### 4.3 代码审查与集成建议

**减少冲突的策略**:
1. **按模块分人**: 每个开发者负责独立的目录树 (如: 张三做 `api/`, 李四做 `services/`, 王五做 `knowledge/`)
2. **先定义接口再开发**: 在 `api/schemas.py` 中先定义 Pydantic 模型 (接口契约)，各自实现
3. **短分支策略**: 每个任务在独立分支开发，最长不超过 3 天即合并

**保证风格一致**:
1. **共享 `pyproject.toml` 配置**: 配置 `ruff` (lint) 和 `black` (format) 规则
   ```toml
   [tool.ruff]
   line-length = 100
   target-version = "py310"

   [tool.ruff.lint]
   select = ["E", "F", "I", "N", "W"]

   [tool.black]
   line-length = 100
   target-version = ['py310']
   ```
2. **Pre-commit Hook**: 在 `.github/hooks/pre-commit` 中配置自动 lint
3. **PR 模板**: 在 `.github/pull_request_template.md` 中要求填写变更说明和测试证明
4. **Claude Code 生成代码规范检查**: 每个开发者在提交前手动运行 `ruff check .` 和 `python -m pytest`

**集成流程**:
```
feature分支 → ruff/pytest 通过 → PR → 人工Review → squash merge → main
```

---

## 五、附录

### A. 当前目录结构 (2026-06-02)

```
building-agent/
├── AGENT.md                     # ✅ 项目上下文
├── DEVELOPMENT_PLAN.md          # ✅ 本文档
├── .env                         # ✅ 多Agent环境配置
├── agent/                       # ✅ Manager Agent
│   ├── orchestrator.py          # ✅ ReAct Agent 编排
│   ├── memory_manager.py        # ✅ 三层记忆 (LLM提取+向量检索+混合排序)
│   ├── memory_reflection.py     # ✅ 反思模块 (≥20条记忆生成洞察)
│   ├── rag.py                   # ✅ ChromaDB 检索
│   └── skills/
│       └── inspection_skill.py  # ✅ 多图巡检工作流
├── llm/                         # ✅ LLM 核心
│   ├── client.py                # ✅ OpenAI 兼容 (native+prompt双模式)
│   ├── tools.py                 # ✅ 6 个 Tool
│   ├── agent_factory.py         # ✅ Manager Agent 单例
│   ├── chat_core.py             # ✅ 对话核心
│   ├── local_vl_model.py        # ✅ Report Agent 模型加载
│   └── react_parser.py          # ✅ ReAct 文本解析
├── predictors/                  # ✅ CV 模型 (5个)
├── db/                          # ✅ ORM (12表 + 5 CRUD)
├── api/                         # ✅ FastAPI (auth, chat, history, statistics, health)
├── services/                    # ✅ Gradio 适配 (5模块)
├── scripts/
│   ├── launch_local_llm.py      # ✅ Report Agent 服务
│   ├── build_rag.py             # ✅ RAG 构建
│   └── inspect_pdf.py           # ✅ PDF 提取
├── qwen2_5_vl_3b_building_merged/  # 🆕 微调模型 (gitignored, README.md 除外)
├── model_weights/               # ✅ CV 权重 (gitignored)
├── chroma_db/                   # ✅ 向量库 (gitignored)
├── openspec/                    # ✅ 10 cap specs + config.yaml
├── tests/                       # ✅ 11 测试文件
└── app.py                       # ✅ Gradio Web UI
```

### B. 推荐新增依赖

```
# requirements.txt 已包含
# 新增:
#   - (无) — 本地 LLM 服务使用已有的 fastapi + uvicorn + transformers
#   - 已移除: vllm (Windows 不支持)
```

### B. 推荐新增依赖

```
# requirements.txt 追加

# JWT 认证
python-jose[cryptography]>=3.3.0

# 知识库
chromadb>=0.4.0
langchain-text-splitters>=0.2.0
pypdf>=4.0.0

# 日志
loguru>=0.7.0

# 测试
pytest>=8.0.0
httpx>=0.27.0
pytest-asyncio>=0.23.0

# 代码质量
ruff>=0.4.0
black>=24.0.0

# 消息队列 (阶段3)
# celery>=5.3.0
# redis>=5.0.0

# gRPC (阶段3)
# grpcio>=1.60.0
# grpcio-tools>=1.60.0
```

### C. 系统架构演进图

```
当前 (阶段2.5 完成)                       目标 (阶段4完成后)

┌──────────────────┐                   ┌──────────┐  ┌──────────┐
│    Gradio UI     │                   │  Gradio  │  │  React   │
│   (app.py)       │                   │    UI    │  │  (PWA)   │
└────────┬─────────┘                   └────┬─────┘  └────┬─────┘
         │                                  │             │
┌────────┴─────────┐                   ┌────┴─────────────┴────┐
│ Manager Agent    │                   │   Nginx Gateway :8000 │
│ (通义千问 API)    │                   └──────────┬────────────┘
│ + 6 Tools        │                              │
│ + MemoryManager  │                   ┌──────────┼────────────┐
└────────┬─────────┘                   │          │            │
         │                        ┌────┴────┐ ┌───┴────┐ ┌────┴────┐
┌────────┴─────────┐             │  Auth   │ │Inspect │ │Feedback │
│ Report Agent     │             │ :8001   │ │:8002   │ │:8003    │
│ (本地 Qwen2.5-VL) │             └─────────┘ └────────┘ └─────────┘
│ localhost:8000   │
└────────┬─────────┘
         │
    ┌────┴────────────────┐
    │  SQLite + ChromaDB  │
    └─────────────────────┘
```

---

> **文档维护**: 本文件由项目 Tech Lead 维护，每阶段完成后更新进度。开发者可通过 `AGENT.md` 获取简化版上下文，通过本文档查看完整路线图。
