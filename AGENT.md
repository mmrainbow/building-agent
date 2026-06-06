# AGENT.md — Building-Agent 项目上下文

## 项目简介
AI 驱动的建筑外立面巡检系统 — 三 Agent 协同架构。

| Agent | 模型 | 职责 |
|------|------|------|
| **Manager Agent** | 通义千问 qwen3.6-flash | 理解意图、调度 CV 工具、解读结果 |
| **Memory Agent** | 通义千问 qwen-turbo | 自动从对话中提取长期记忆 |
| **Report Agent** | 本地微调 Qwen2.5-VL | 生成专业中文巡检报告 |

技术栈: Python 3.10+, FastAPI, Vue 3, SQLAlchemy 2, transformers, YOLO (ultralytics), PyTorch, OpenCV, ChromaDB

## 多 Agent 架构

```
用户 ──→ Manager Agent (qwen3.6-flash) ──→ CV 工具 (本地)
                │                              ├─ classify_material
                │                              ├─ estimate_floors
                │                              ├─ detect_extension
                │                              ├─ detect_defects
                │                              └─ search_knowledge
                │
                ├──→ generate_report ──→ Report Agent (本地 Qwen2.5-VL :8000)
                │
                └──(每轮对话后自动)──→ Memory Agent (qwen-turbo) ──→ ConversationMemory
```

## 项目结构
```
frontend/               Vue 3 前端 (Vite + Element Plus + Pinia)
backend/                Python 后端
  agent/                 Manager Agent + Memory 系统
    orchestrator.py       ReAct 循环 + 持久化 + 摘要压缩
    context.py            System Prompt + 消息构建
    memory_manager.py     长期记忆管理 (LLM判断提取 + 向量检索 + 混合排序)
    memory_reflection.py  反思模块 (≥20条记忆自动生成洞察)
    rag.py                ChromaDB RAG (建筑规范 + Memory 向量存储)
    skills/               InspectionSkill (多图巡检工作流)
  predictors/            CV模型预测器 (材质/楼层/加层/隐患)
  llm/                   LLM 核心
    client.py             LLMClient (OpenAI 兼容, native+prompt 双模式)
    tools/                6 个 Tool (已拆分为包: schemas/base/knowledge/report)
    agent_factory.py      Manager Agent 单例
    chat_core.py          对话核心逻辑
    local_vl_model.py     Report Agent 模型加载与推理
    memory_agent.py       Memory Agent 独立客户端
    react_parser.py       ReAct 文本解析器 (prompt 回退模式)
  db/                    SQLAlchemy ORM
    models.py             12 表定义
    crud_user.py          用户 CRUD (注册/认证/查询)
    crud_inspection.py    巡检记录 CRUD
    chat_crud.py          对话与消息 CRUD
    memory_crud.py        长期记忆 CRUD
    feedback_crud.py      反馈 CRUD
  api/                   FastAPI 路由
    main.py               App 入口 (lifespan + CORS + 路由注册)
    auth.py               JWT 工具 (签发/验证/角色守卫)
    chat.py               Chat API (REST + SSE 流式)
    inspection.py         Inspection API (多图巡检)
    schemas.py            Pydantic 请求/响应模型
    routes/               按业务域拆分的路由模块
      auth_routes.py       /register, /token, /login, /token/refresh
      history_routes.py    /history, /history/{id}, /history/{id}/export
      admin_routes.py      /admin/users
      health_routes.py     /health, /agent/status
  scripts/
    launch_local_llm.py  Report Agent 服务启动
    build_rag.py         RAG 向量库构建
  model_weights/         CV 模型权重 (5 个文件, gitignore)
  tests/                 测试 (12 个文件)
```

## 职责划分
```
api/       → 薄层: 参数校验 + 认证 + 调用 service → 格式化响应
llm/       → 核心逻辑: LLM客户端 + Tool + Agent工厂 + 对话核心 + 本地VL
agent/     → Agent 编排: ReAct循环 + 上下文构建 + 双层记忆 + RAG 检索
db/        → 数据访问: SQLAlchemy ORM + 按域拆分的 CRUD 模块
```

## 开发约定
- 文案、注释、报告、UI 统一中文
- 类型注解使用新语法: `list[dict]`, `str | None`
- API 认证用 JWT (python-jose)，密码用 bcrypt
- 数据库默认 SQLite，可通过 `INSPECTION_DB_URL` 切 MySQL
- **默认 LLM 后端: 本地 vLLM** (微调 Qwen2.5-VL, `USE_LOCAL_LLM=true`)
- 可切回远程通义千问 API: `USE_LOCAL_LLM=false`
- Embedding 调用默认复用 LLM_API_KEY，也可单独配置 EMBEDDING_API_KEY
- 环境变量命名: `UPPER_SNAKE_CASE`
- api/ 不写业务逻辑，调 llm/ 或 agent/
- routes/ 模块各自独立 APIRouter，main.py 仅负责注册

## 关键环境变量
```
USE_LOCAL_LLM            使用本地 LLM 作为 Manager (默认 false，使用远程 API)
LLM_BASE_URL             Manager LLM API 地址
LLM_MODEL                 Manager 模型 (默认 qwen3.6-flash)
LLM_TOOL_CALL_MODE        Manager 工具调用: native (默认)
MEMORY_LLM_MODEL          Memory Agent 模型 (默认 qwen-turbo，独立于 Manager)
LLM_API_KEY               DashScope API 密钥
REPORT_AGENT_URL          Report Agent 地址 (默认 http://localhost:8000)
EMBEDDING_API_KEY         Embedding API 密钥 (默认复用 LLM_API_KEY)
EMBEDDING_MODEL           Embedding 模型 (默认 text-embedding-v3)
LOCAL_VL_MODEL_PATH       本地模型路径 (Report Agent 使用)
LOCAL_VL_DEVICE_MAP       模型加载设备 (默认 auto)
LOCAL_VL_TORCH_DTYPE      推理精度 (默认 float16)
INSPECTION_DB_URL         数据库连接 (默认 sqlite:///./inspection.db)
JWT_SECRET_KEY            JWT 签名密钥
MEMORY_EXTRACT_THRESHOLD  记忆提取触发字符数阈值 (默认 6000)
INIT_USERNAME             初始用户名 (默认 user123)
INIT_PASSWORD             初始密码 (默认 user123)
```

## 当前数据模型 (12 张表)
- **User**: id, username, password_hash, role, is_active, created_at, last_login_at
- **UserPreference**: id, user_id(FK,unique), language, report_style, preferred_model
- **InspectionRecord**: id, user_id(FK), status, report, created_at → images(ImageInspection)
- **ImageInspection**: id, record_id(FK), chat_image_id(FK→chat_images), image_name, material, floor, has_extension → defects(通过 chat_image)
- **Defect**: id, chat_image_id(FK→chat_images), defect_type, area, box_coords(JSON)
- **Conversation**: id, user_id(FK), title, model, message_count, created_at, updated_at → messages(ChatMessage)
- **ChatMessage**: id, conversation_id(FK), role, content, metadata(JSON), created_at → images(ChatImage)
- **ChatImage**: id, message_id(FK), mime_type, data(BLOB) → defects
- **ConversationMemory**: id, user_id(FK), conversation_id(FK), memory_type, key, content, chroma_id, importance, access_count
- **Feedback**: id, user_id(FK), record_id(FK), message_id(FK), feedback_type, target_field, original_value, corrected_value, rating, comment
- **KnowledgeDocument**: id, title, file_name, file_type, source_type, chunk_count, status → chunks
- **KnowledgeChunk**: id, document_id(FK), chunk_index, content, chroma_id, metadata(JSON)

## API 端点

### 认证（公开）
```
POST /register             用户注册
POST /token                登录 (OAuth2 form, Swagger UI)
POST /login                登录 (JSON, API 客户端)
POST /token/refresh        刷新 token
```

### 巡检（需 JWT）
```
POST /inspection/multi     多图巡检 (≥3张, 返回报告+标注图)
GET  /history              巡检列表 (分页)
GET  /history/{id}         单条详情
GET  /history/{id}/export  导出 Excel
```

### 对话（需 JWT）
```
POST /chat/send            发送消息 (文本+图片) → AI 自主 Tool
POST /chat/send/stream     SSE 流式问答 (CoT 实时推送)
GET  /chat/conversations   我的对话列表
GET  /chat/conversations/{id} 对话详情 (含图片 URL)
DELETE /chat/conversations/{id} 删除对话
GET  /chat/images/{message_id} 获取图片 (公开端点)
GET  /chat/memories           对话记忆列表
DELETE /chat/memories/{id}    删除单条记忆
```

### 管理（需 admin）
```
GET  /admin/users          用户列表
```

### 运维
```
GET  /health               数据库 + Ollama + 模型文件状态 (公开)
GET  /agent/status         Manager/Memory/Report 三 Agent 状态 (需 JWT)
```

## Memory 系统 (三层模型)

借鉴认知心理学，记忆分为三层：

| 层级 | 实现 | 机制 |
|------|------|------|
| **短期记忆** | `chat_messages` (最近 20 条) | 滑动窗口 + Summary Buffer (LLM 摘要压缩旧消息) |
| **长期记忆** | `conversation_memories` + ChromaDB | LLM 判断触发 → 提取 ≤3 条 → 向量索引 → 混合排序召回 |
| **反思** | `memory_reflection.py` | ≥20 条记忆时异步触发，生成高阶洞察 (insight) |

**检索公式**: `Score = 0.3×recency + 0.5×relevance + 0.2×importance`
**降级策略**: ChromaDB 不可用 → SQLite keyword LIKE; LLM 不可用 → 字符数阈值

## 两条巡检路径

| | 图像巡检 | 智能问答 |
|------|------|------|
| 入口 | Vue Inspection 页面 | Vue Chat 页面 |
| 调度 | InspectionSkill (多图→批量CV→LLM报告) | ReAct Agent (LLM 自主选 Tool) |
| LLM 后端 | Report Agent (本地 Qwen2.5-VL) | Manager (通义千问 API) + Report Agent |
| Tool 调用 | 固定全跑 4 个 CV | LLM 自主选择 |
| 记忆 | — | MemoryManager |
| 持久化 | InspectionRecord + ImageInspection + Defect | ChatMessage + ChatImage |

## 启动方式

### 后端
```bash
cd backend
# 终端 1: 启动 Report Agent (本地微调模型)
conda activate building-agent
python scripts/launch_local_llm.py

# 终端 2: 启动 FastAPI
conda activate building-agent
uvicorn api.main:app --port 8001
```

### 前端 (Vue 3)
```bash
cd frontend
npm install
npm run dev     # http://localhost:5173 (代理 /api → :8000)
```

## 禁止事项
- 不要删除 `model_weights/` 下的 `.pt`/`.pth` 模型权重文件
- 不要提交 `.env`、`chroma_db/`、`rag_data/`、`*.docx`、`outputs/`、`chat_images/`
- 不要在代码中硬编码密码、密钥或内网地址
- 修改数据模型后必须同步更新测试和 `db/SCHEMA.md`
- 业务逻辑不放 api/ 层

## 相关文档
- `DEVELOPMENT_PLAN.md`             完整开发路线图
- `db/SCHEMA.md`                    12 表结构全量文档
- `history_mk/merge_rag&memory.md`  RAG+Memory 合并记录
- `history_mk/LLM_FINE_TUNING_GUIDE.md` 微调模型部署指南
- `history_mk/微调模型本地调用说明.md`    本地 VL 调用说明
- `README.md`                       快速启动指南

## 当前开发阶段
阶段 2/2.5 完成 — 多 Agent 协同 (Manager + Memory + Report) + 前后端分离 (Vue 3 + FastAPI)。
代码已重构: Gradio 适配层移除，按职责解耦为独立模块。
下一步：阶段 3 反馈系统。

## 快速命令
```bash
# 后端
cd backend
python scripts/launch_local_llm.py      # 启动本地 LLM 服务
uvicorn api.main:app --port 8001        # FastAPI
python scripts/build_rag.py             # 构建 RAG 向量库
python -m pytest tests/ -v              # 测试

# 前端
cd frontend && npm install && npm run dev  # Vue 开发服务器
```
