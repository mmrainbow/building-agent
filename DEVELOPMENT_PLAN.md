# Building-Agent 项目演进开发路线图

> 基于代码库全面分析生成 | 生成日期: 2026-05-26 | 最后更新: 2026-05-26 (阶段0完成)

---

## 零、执行进度

| 阶段 | 状态 | 完成日期 |
|------|------|---------|
| 阶段0: 基础夯实 | **已完成** | 2026-05-26 |
| 阶段0.5: 数据模型架构补强 | **已完成** | 2026-05-26 |
| 阶段1: Agent 框架 + RAG + 对话系统 | **已完成** | 2026-06-01 |
| 阶段2: 反馈系统 | 待开始 | — |
| 阶段3: 多 Agent 协同 | 待开始 | — |
| 阶段4: 服务化部署 | 待开始 | — |
| 阶段5: 前后端分离 (可选) | 待开始 | — |

---

## 一、代码库全面分析

### 1.1 项目概述

**核心业务**: AI 驱动的建筑外立面巡检系统。用户上传建筑图片，系统通过 CV 模型（YOLO、EfficientNet）自动检测建筑材质、楼层数、违建加层、外墙隐患（空鼓/渗水/脱落/裂缝），并调用 Ollama 本地 LLM 生成中文巡检报告。

**服务对象**: 住建管理部门为主，普通用户随拍随用为辅。

### 1.2 现有架构

当前为 **模块化单体** 架构，技术栈和分层如下：

```
┌─────────────────────────────────────────────────┐
│  用户入口                                        │
│  ├── app.py      Gradio Web UI (146行，薄路由层) │
│  ├── main.py     CLI 命令行入口 (25行)            │
│  └── api/main.py FastAPI REST API (290行)        │
├─────────────────────────────────────────────────┤
│  业务逻辑层 (2026-05-26 新增)                    │
│  └── services/   app.py 拆分产物                  │
│      ├── auth_service.py        认证逻辑          │
│      ├── inspection_service.py 巡检核心流程       │
│      ├── history_service.py    历史记录管理       │
│      ├── statistics_service.py 统计分析           │
│      └── chat_service.py       LLM 智能问答       │
├─────────────────────────────────────────────────┤
│  认证层 (2026-05-26 新增)                        │
│  └── api/        FastAPI 扩展                    │
│      ├── auth.py     JWT 签发/验证/角色依赖注入    │
│      └── schemas.py  统一 Pydantic 请求/响应模型   │
├─────────────────────────────────────────────────┤
│  业务编排层                                      │
│  └── agent/      LangGraph 工作流引擎             │
│      ├── graph.py    DAG 图定义 (load→并行4节点→汇总)│
│      ├── nodes.py    各检测节点 + LLM报告生成      │
│      └── state.py    TypedDict 状态定义            │
├─────────────────────────────────────────────────┤
│  AI 模型层                                       │
│  └── predictors/ CV 推理模块                      │
│      ├── base.py        BasePredictor 基类        │
│      ├── material.py    EfficientNetV2 材质识别    │
│      ├── floor.py       YOLO + RANSAC 楼层检测     │
│      ├── added_floor.py EfficientNetV2 加层判断    │
│      ├── hidden_danger.py YOLO-OBB 隐患检测       │
│      └── floor_recognition.py 几何算法辅助         │
├─────────────────────────────────────────────────┤
│  数据层                                         │
│  └── db/         SQLAlchemy ORM                 │
│      ├── models.py     User/InspectionRecord/Defect │
│      ├── database.py   SQLite/MySQL 引擎管理       │
│      └── crud.py       用户认证 + 记录CRUD + 统计   │
└─────────────────────────────────────────────────┘
```

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

### 1.3 可复用部分

| 模块 | 可直接复用 | 需要改造 |
|------|-----------|---------|
| `predictors/` | 全部6个预测器及其 `BasePredictor` 基类可直接复用 | 增加统一配置管理和模型热加载 |
| `db/models.py` | User/InspectionRecord/Defect 三个模型可复用 | 需扩展 User 表增加反馈相关字段 |
| `db/crud.py` | 用户认证 (`authenticate_user`, `create_user`) 可复用 | 需增加反馈 CRUD 和知识库检索 |
| `db/database.py` | `init_db()`, `SessionLocal`, `get_db()` 可复用 | 连接池配置可优化 |
| `agent/graph.py` | LangGraph 编排模式可复用 | 需扩展为多 Agent 编排 |
| `agent/nodes.py` | 各检测节点可复用 | 报告节点需接入知识库上下文 |
| `agent/state.py` | TypedDict 模式可复用 | 需扩展状态字段 |
| `api/main.py` | FastAPI 路由结构可参考 | 权限需升级为 JWT |

### 1.4 需要重构或重写的部分

| 问题 | 严重程度 | 状态 |
|------|---------|------|
| `app.py` 单体巨石 | 高 | **已修复**: 拆为 `services/` 下 5 个模块 + 146行薄路由层 |
| 认证机制不统一 | 高 | **已修复**: FastAPI 统一使用 JWT Bearer，含角色权限中间件 |
| 无 JWT 无角色权限中间件 | 高 | **已修复**: `api/auth.py` 实现 `get_current_user` + `require_admin` |
| 无测试 | 中 | **已修复**: `tests/` 目录 27 个用例覆盖认证/巡检/历史/健康检查 |
| 无日志系统 | 中 | 待实现 |
| 无反馈机制 | 中 | 完全缺失，但这是关键的新功能 |
| 无知识库 | 中 | LLM 问答仅基于最近一次报告，无历史知识检索 |
| Agent 编排简单 | 低 | 目前只是 LangGraph 的 DAG，非真正多 Agent 协作 |
| 模型权重未版本化 | 中 | 依赖手动放置 .pt/.pth 文件 |

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

### 2.5 多 Agent 协同

**现状**: 使用 LangGraph 定义了单个 DAG 工作流（load_image → material/floor/extension/defect 并行 → report 汇总），这不是真正的多 Agent 系统。

**设计方案: 主控 Agent + 专项 Agent**

```
                  ┌─────────────┐
                  │ Orchestrator │  (主控 Agent)
                  │  Agent       │  负责: 任务分解、Agent 调度、结果汇总
                  └──┬───┬───┬──┘
          ┌──────────┘   │   └──────────┐
          ▼              ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │Material  │  │Floor     │  │Defect    │
    │Agent     │  │Agent     │  │Agent     │
    └──────────┘  └──────────┘  └──────────┘
          │              │              │
          └──────────────┼──────────────┘
                         ▼
                  ┌──────────┐
                  │ Report   │
                  │ Agent    │
                  └──────────┘
```

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

#### 核心架构决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| LLM 服务 | 通义千问 API (qwen-plus) | 免费额度，OpenAI 兼容，原生 function calling |
| Tool 调度 | LLM 自主决策 (ReAct 循环) | 替代静态 DAG，AI 根据图像内容选择调用哪些工具 |
| Embedding | 通义千问 text-embedding-v4 | 与 LLM 同平台，免费额度充足 |
| Agent 框架 | 自建 ReAct + LangGraph State | 轻量可控，无需引入 LangChain Agent |

#### Agent 执行流程

```
用户发送图片 + 问题
        │
        ▼
┌─────────────────────────────────────────────┐
│            MemoryManager                     │
│  1. 组装上下文                               │
│     ├── 短期: 最近 20 条对话消息              │
│     ├── 长期: ConversationMemory 关键词检索   │
│     └── RAG:  ChromaDB 知识库检索            │
└──────────────┬──────────────────────────────┘
               │ messages + tools
               ▼
┌─────────────────────────────────────────────┐
│           AgentOrchestrator (ReAct)          │
│                                              │
│  ┌─── LLM 决定 ──▶ 调用 Tool ──▶ 返回结果 ──┐│
│  │                                          ││
│  └──── 循环直到 LLM 生成最终回答 ◀───────────┘│
│                                              │
│  可用 Tools:                                  │
│  - classify_material  (材质识别)              │
│  - estimate_floors     (楼层估算)              │
│  - detect_extension    (加层检测)              │
│  - detect_defects      (隐患检测)              │
│  - search_knowledge    (知识库检索)            │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────┐
│            后处理                             │
│  ├── 保存消息到 ChatMessage                    │
│  ├── 自动提取记忆 → ConversationMemory        │
│  └── 返回 AI 回复 + tool_call_log             │
└─────────────────────────────────────────────┘
```

#### 新增目录

```
llm/                    # 新增: LLM 客户端 + Tool 封装
├── __init__.py
├── client.py           # 通义千问 API (OpenAI 兼容)
└── tools.py            # 4个 Predictor → Tool 封装 + search_knowledge

agent/
├── orchestrator.py     # 新增: ReAct Agent 主循环
├── memory_manager.py   # 新增: 三层上下文检索 + 记忆提取
├── graph.py            # 保留: 原有 DAG (CLI 兼容)
├── nodes.py / state.py # 保留

api/
├── chat.py             # 新增: Chat API 路由
```

#### 任务清单

**1.1 LLM 客户端 (0.5天)** ✅
- [x] **通义千问 API 客户端** — `llm/client.py`: `chat(messages, tools)` + `chat_with_tools()` ReAct 自动循环 — **复杂度: 低, 可 CC**
- [x] **环境变量** — `DASHSCOPE_API_KEY`, `LLM_MODEL` (默认 qwen-plus), `LLM_BASE_URL` — **复杂度: 低, 可 CC**

**1.2 Tool 封装 (0.5天)** ✅
- [x] **Predictor → Tool 适配器** — `llm/tools.py`: 4 个 Predictor 包装为 Function Call schema + executor (延迟加载) + DefectToolWrapper 中文格式化 — **复杂度: 中, 可 CC**
- [x] **知识库检索 Tool** — `search_knowledge(query)` → SQLite LIKE 过渡 — **复杂度: 中, 可 CC**

**1.3 Agent 编排 (1天)** ✅
- [x] **ReAct 循环** — `agent/orchestrator.py`: InspectionAgent 类，上下文组装 → LLM 调用 → tool_calls 执行 → 持久化消息 — **复杂度: 高, 可 CC**
- [x] **System Prompt** — 建筑巡检专家角色 + 5 个工具说明 + 使用原则 + 输出格式 — **复杂度: 中, 可 CC**
- [x] **Tool 调用日志** — 记录 name/input/output/elapsed_ms 到 ChatMessage.metadata — **复杂度: 低, 可 CC**

**1.4 Memory + RAG (1天)** ✅
- [x] **MemoryManager** — `agent/memory_manager.py`: 双层记忆（近期消息 + LLM 提取长期记忆）→ ConversationMemory
- [x] **ChromaDB 接入** — KnowledgeSearchTool 优先查 ChromaDB 规范 (`agent/rag.py` search_regulations)，回退用户记忆

**1.5 Chat API (0.5天)** ✅
- [x] **对话端点** — `api/chat.py`: POST `/chat/send` (支持图片), GET `/chat/conversations`, GET/DELETE `/chat/conversations/{id}`

**1.6 集成验证 + 代码清理 (0.5天)** ✅
- [x] **统一 Agent 实例** — `llm/agent_factory.py` 单例，api/ 和 services/ 共用
- [x] **职责边界清理** — api/ 薄路由、services/ Gradio 适配、llm/ 核心逻辑
- [x] **Gradio 对话 Tab 升级** — 图片上传 + tool 调用摘要显示
- [x] **35 测试通过**（核心套件）

**1.7 对话体验增强 (1天)** ✅
- [x] **记忆隔离** — 长期记忆从全局共享改为按对话隔离（`conversation_id` 过滤检索和 upsert）
- [x] **防重复 Tool 调用** — `_history_to_messages` 保留 tool role，不伪装成 user
- [x] **Gradio 对话列表侧栏** — 左侧列表显示历史对话，点击切换，支持新建/删除
- [x] **对话图片持久化** — `chat_images` 表 (BLOB 入库) + 缓存文件渲染，项目移动不丢数据
- [x] **巡检表重构** — `InspectionRecord` 拆出 `ImageInspection` (图片级检测结果)，`Defect.record_id` → `Defect.image_id`
- [x] **图片不存两份** — `image_inspection.chat_image_id` FK→`chat_images`，巡检对话复用同一张图片
- [x] **InspectionSkill 多图巡检** — 收集 ≥3 张 → 批量 CV 检测 → LLM 汇总报告 → 入库。独立于 LLM Tool 体系
- [x] **智能问答 vs 图像巡检分离** — 智能问答 Tab (5 Tool ReAct) / 图像巡检 Tab (多图工作流)，互不干扰
- [x] **默认角色重命名** — `UserRole.inspector` → `UserRole.user`（普通用户）
- [x] **数据模型总览** — 12 张表，`db/SCHEMA.md` 全量文档
- [x] **本地 VL 微调模型** — `llm/local_vl_model.py` Qwen2.5-VL 本地调用，优先 VL 报告 → 回退 LLM+RAG
- [x] **embedding API 修复** — 原生 DashScope 端点，batch_size=10，模型名 v4→v3
- [x] **LLM_API_KEY / EMBEDDING_API_KEY 分离** — 各自独立配置，embedding 默认复用 LLM key
- [x] **OpenSpec 规格化** — `openspec/specs/` 6 个 capability spec + `config.yaml`

> **架构决策**: ReAct 最大循环 10 次防死循环；Tool 超时 30s；短期记忆窗口 20 条消息；长期记忆 top_k=5；RAG top_k=3。

### 阶段2: 反馈系统 (1周, 1人)

**目标**: 收集用户纠错和评分数据，建立数据飞轮。

- [ ] **Feedback API** — `api/feedback.py`: POST/GET 反馈，GET 统计 (表 + CRUD 已在 0.5) — **复杂度: 中, 可 CC**
- [ ] **Gradio 反馈 UI** — 报告详情 + 对话消息旁增加纠错/评分 — **复杂度: 中, 可 CC**

### 阶段3: 多 Agent 协同 (2-3周, 1-2人)

**目标**: 从单 ReAct Agent 演进到主控+专项 Agent 协作。

- [ ] **Agent 注册中心** — `agent/registry.py`: Agent 注册/发现/调度 — **复杂度: 中, 可 CC**
- [ ] **Agent 通信协议** — `agent/protocol.py`: 标准化消息格式 — **复杂度: 低, 可 CC**
- [ ] **ReviewAgent** — 审核其他 Agent 输出，基于知识库检查报告一致性 — **复杂度: 高, 可 CC**

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
[由 Tech Lead 更新，如: "阶段0 - 模块拆分中"]

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

### A. 推荐新增目录结构

```
building-agent/
├── AGENT.md                     # ✅ AI Agent 共享上下文入口
├── DEVELOPMENT_PLAN.md          # ✅ 本文档
├── pyproject.toml               # [待新增] 项目配置 (ruff, black, pytest)
├── .github/
│   └── pull_request_template.md # [待新增] PR 模板
├── services/                    # ✅ 业务逻辑层 (阶段0)
│   ├── __init__.py
│   ├── constants.py             # ✅ TEXT 文案字典
│   ├── auth_service.py          # ✅ 认证逻辑
│   ├── inspection_service.py    # ✅ 巡检核心流程
│   ├── history_service.py       # ✅ 历史记录管理
│   ├── statistics_service.py    # ✅ 统计分析
│   └── chat_service.py          # ✅ LLM 智能问答
├── knowledge/                   # [待新增] 知识库模块 (阶段1)
│   ├── __init__.py
│   ├── vector_store.py
│   ├── loader.py
│   ├── embedding.py
│   └── retriever.py
├── export/                      # [待新增] 导出工具 (阶段1)
│   ├── __init__.py
│   └── feedback_exporter.py
├── scripts/                     # [待新增] 运维脚本 (阶段3)
│   ├── healthcheck.py
│   └── download_models.sh
├── tests/                       # ✅ 测试目录 (阶段0)
│   ├── __init__.py
│   ├── conftest.py              # ✅ fixtures + mock agent
│   ├── test_auth.py             # ✅ 16 个认证用例
│   ├── test_predict.py          # ✅ 3 个巡检用例
│   ├── test_history.py          # ✅ 5 个历史/权限用例
│   └── test_health.py           # ✅ 3 个健康检查用例
├── api/                         # ✅ JWT 认证 + 新端点 (阶段0)
│   ├── auth.py                  # ✅ JWT 签发/验证/角色依赖
│   ├── schemas.py               # ✅ Pydantic 请求/响应模型
│   ├── feedback.py              # [待新增] 反馈 API (阶段1)
│   ├── knowledge.py             # [待新增] 知识库 API (阶段1)
│   └── main.py                  # ✅ 重写: HTTP Basic→JWT, +7 端点
├── agent/                       # [待扩展] (阶段2)
│   ├── registry.py              # [待新增]
│   ├── protocol.py              # [待新增]
│   ├── orchestrator.py          # [待新增]
│   └── ...
├── db/                          # [待扩展] (阶段1)
│   ├── feedback_crud.py         # [待新增]
│   └── ...
└── app.py                       # ✅ 146行 薄UI层 (-73%)
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
当前                                      目标 (阶段3完成后)

┌─────────┐ ┌──────┐                    ┌──────────┐  ┌──────────┐
│ Gradio  │ │ CLI  │                    │  Gradio  │  │  React   │
│   UI    │ │      │                    │    UI    │  │  (PWA)   │
└────┬────┘ └──┬───┘                    └────┬─────┘  └────┬─────┘
     │         │                            │             │
     └────┬────┘                            └──────┬──────┘
          │                                       │
┌─────────┴─────────┐                   ┌─────────┴─────────┐
│    app.py (530行)  │                   │  Nginx Gateway    │
│    单体巨石        │                   │  :8000            │
└─────────┬─────────┘                   └─────────┬─────────┘
          │                                       │
    ┌─────┴─────┐                    ┌────────────┼────────────┐
    │           │                    │            │            │
┌───┴───┐ ┌────┴────┐         ┌─────┴────┐ ┌─────┴────┐ ┌─────┴────┐
│Agent  │ │FastAPI  │         │  Auth    │ │Inspect   │ │Feedback  │
│Graph  │ │:8000    │         │  :8001   │ │:8002     │ │:8003     │
└───┬───┘ └────┬────┘         └─────┬────┘ └─────┬────┘ └─────┬────┘
    │          │                    │            │            │
    └────┬─────┘                    └──────┬─────┴─────┬──────┘
         │                                │           │
    ┌────┴────┐                      ┌────┴────┐ ┌────┴────┐
    │ SQLite  │                      │  MySQL  │ │ChromaDB │
    └─────────┘                      └─────────┘ └─────────┘
```

---

> **文档维护**: 本文件由项目 Tech Lead 维护，每阶段完成后更新进度。开发者可通过 `AGENT.md` 获取简化版上下文，通过本文档查看完整路线图。
