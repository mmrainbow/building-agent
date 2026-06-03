# AGENT.md — Building-Agent 项目上下文

## 项目简介
AI 驱动的建筑外立面巡检系统 — 三 Agent 协同架构。

| Agent | 模型 | 职责 |
|------|------|------|
| **Manager Agent** | 通义千问 qwen3.6-flash | 理解意图、调度 CV 工具、解读结果 |
| **Memory Agent** | 通义千问 qwen-turbo | 自动从对话中提取长期记忆 |
| **Report Agent** | 本地微调 Qwen2.5-VL | 生成专业中文巡检报告 |

技术栈: Python 3.10+, FastAPI, Gradio 6, SQLAlchemy 2, transformers, YOLO (ultralytics), PyTorch, OpenCV, ChromaDB

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
frontend/        Vue 3 前端 (Vite + Element Plus)
backend/         Python 后端
  agent/          Manager Agent (orchestrator, memory_manager, rag, skills/)
  predictors/     CV模型预测器 (材质/楼层/加层/隐患)
  llm/            LLM 客户端 + 6 个 Tool + Agent工厂 + Report Agent
  db/             SQLAlchemy ORM (12表)
  api/            FastAPI 薄路由层 (auth JWT, inspection, chat, main)
  services/       Gradio 适配层
  app.py          Gradio Web UI 主入口
  scripts/
    launch_local_llm.py  Report Agent 服务启动
    build_rag.py         RAG 向量库构建
  model_weights/  CV 模型权重 (5 个文件, gitignore)
  tests/          测试
```

## 职责划分
```
api/       → 薄层: 参数校验 + 认证 + 调用 service → 格式化响应
services/  → Gradio 适配: session 状态管理 + 上下文拼接 + UI 回调
llm/       → 核心逻辑: LLM客户端 + Tool + Agent工厂 + 对话核心 + 本地VL
agent/     → Agent 编排: ReAct循环 + 双层记忆 + RAG 检索
db/        → 数据访问: SQLAlchemy ORM + CRUD
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
- api/ 不写业务逻辑，调 llm/ 或 services/
- services 不依赖 FastAPI / Gradio 组件（auth_service 返回纯数据，UI 包装在 app.py）

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
INIT_ADMIN_USERNAME       初始管理员用户名
INIT_ADMIN_PASSWORD       初始管理员密码
```

## 当前数据模型 (12 张表)
- **User**: id, username, password_hash, role, is_active, created_at, last_login_at
- **UserPreference**: id, user_id(FK,unique), language, report_style, preferred_model
- **InspectionRecord**: id, user_id(FK), status, report, created_at → images(ImageInspection)
- **ImageInspection**: id, record_id(FK), chat_image_id(FK→chat_images), image_name, material, floor, has_extension → defects
- **Defect**: id, image_id(FK→image_inspection), defect_type, area, box_coords(JSON)
- **Conversation**: id, user_id(FK), title, model, message_count, created_at, updated_at → messages(ChatMessage)
- **ChatMessage**: id, conversation_id(FK), role, content, metadata(JSON), created_at → images(ChatImage)
- **ChatImage**: id, message_id(FK), mime_type, data(BLOB)
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
GET  /history              巡检列表 (分页)
GET  /history/{id}         单条详情
GET  /statistics           统计汇总
```

### 对话（需 JWT）
```
POST /chat/send            发送消息 (文本+可选图片) → AI 自主 Tool
GET  /chat/conversations   我的对话列表
GET  /chat/conversations/{id} 对话详情
DELETE /chat/conversations/{id} 删除对话
```

### 管理（需 admin）
```
GET  /admin/users          用户列表
```

### 运维（公开）
```
GET  /health               数据库 + Ollama + 模型文件状态
```

## 两条巡检路径

| | 图像巡检 | 智能问答 |
|------|------|------|
| 入口 | Gradio "图像巡检" Tab | Gradio "智能问答" Tab |
| 调度 | InspectionSkill (多图→批量CV→LLM报告) | ReAct Agent (LLM 自主选 Tool) |
| LLM 后端 | 本地 vLLM (微调模型) | 本地 vLLM (微调模型) |
| Tool 调用 | 固定全跑 4 个 CV | LLM 自主选择 |
| 记忆 | — | MemoryManager |
| 持久化 | InspectionRecord + ImageInspection + Defect | ChatMessage + ChatImage |

## 启动方式

```bash
# 终端 1: 启动 Report Agent (本地微调模型)
conda activate building-agent
python scripts/launch_local_llm.py

# 终端 2: 启动应用 (Manager + Gradio)
conda activate building-agent
python app.py
```

Manager Agent 默认使用通义千问 API（`USE_LOCAL_LLM=false`），Report Agent 在 `localhost:8000` 提供报告生成服务。

## 禁止事项
- 不要删除 `model_weights/` 下的 `.pt`/`.pth` 模型权重文件
- 不要提交 `.env`、`chroma_db/`、`rag_data/`、`*.docx`、`outputs/`、`chat_images/`
- 不要在代码中硬编码密码、密钥或内网地址
- 修改数据模型后必须同步更新测试和 `db/SCHEMA.md`
- 业务逻辑不放 app.py / api/ 层

## 相关文档
- `DEVELOPMENT_PLAN.md`             完整开发路线图
- `db/SCHEMA.md`                    12 表结构全量文档
- `history_mk/merge_rag&memory.md`  RAG+Memory 合并记录
- `history_mk/LLM_FINE_TUNING_GUIDE.md` 微调模型部署指南
- `history_mk/微调模型本地调用说明.md`    本地 VL 调用说明
- `openspec/specs/`                 10 个 capability 规格文件
- `README.md`                       快速启动指南

## 当前开发阶段
阶段 1 完成 — Agent + RAG + 对话 + Memory + 多图巡检 + 本地微调模型 (vLLM 服务化)。
下一步：阶段 2 反馈系统。

## 快速命令
```bash
# 后端
cd backend
python scripts/launch_local_llm.py      # 启动本地 LLM 服务
python app.py                           # Gradio Web UI
uvicorn api.main:app --port 8000        # FastAPI
python scripts/build_rag.py             # 构建 RAG 向量库
python -m pytest tests/ -v              # 测试

# 前端
cd frontend && npm install && npm run dev  # Vue 开发服务器
```
