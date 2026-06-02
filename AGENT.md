# AGENT.md — Building-Agent 项目上下文

## 项目简介
AI 驱动的建筑外立面巡检系统。上传建筑图片 → CV 模型检测材质/楼层/加层/隐患 → 本地微调 Qwen2.5-VL 模型生成中文巡检报告。

技术栈: Python 3.10+, FastAPI, Gradio 6, SQLAlchemy 2, vLLM, YOLO (ultralytics), PyTorch, OpenCV, ChromaDB, Qwen2.5-VL (本地微调)

## 项目结构
```
agent/          ReAct Agent + Skills (orchestrator, memory_manager, rag, skills/)
predictors/     CV模型预测器 (材质/楼层/加层/隐患) — 全部继承 BasePredictor
llm/            LLM 客户端 + Tool + Agent工厂 + 对话核心 + 本地VL模型
  client.py          OpenAI 兼容客户端 (native + prompt 双模式)
  tools.py           5 个 Tool (4 CV + search_knowledge)
  agent_factory.py   共享 InspectionAgent 单例 (默认本地 vLLM)
  chat_core.py       run_chat() 核心对话逻辑
  local_vl_model.py  Qwen2.5-VL 微调模型本地加载 (transformers)
  react_parser.py    ReAct 文本 tool_call 解析器
db/             SQLAlchemy ORM (12表, database, crud, chat_crud, memory_crud, feedback_crud)
api/            FastAPI 薄路由层 (auth JWT, schemas, main, chat)
services/       Gradio 适配层 (session管理 + UI回调 + 业务逻辑)
  constants.py      用户可见文案字典 TEXT
  auth_service.py   登录/注册/引导逻辑
  chat_service.py   智能问答回调
  history_service.py 历史记录查询
  statistics_service.py 统计图表
app.py          Gradio Web UI 主入口
scripts/        工具脚本 (vLLM 启动, RAG 构建)
model_weights/  CV 模型权重文件 (5 个 .pt/.pth, gitignore)
chroma_db/      ChromaDB 向量库 (gitignore)
rag_data/       RAG 规范文档 (gitignore)
chat_images/    图片缓存目录 (gitignore, 可从DB重建)
history_mk/     历史过程文档
openspec/       OpenSpec 规格文件 (10 个 capability spec)
tests/          测试 (pytest + httpx)
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
USE_LOCAL_LLM            使用本地 vLLM (默认 true)
LLM_BASE_URL             LLM API 地址 (默认 http://localhost:8000/v1)
LLM_MODEL                大模型名称 (默认 qwen2.5-vl-building)
LLM_TOOL_CALL_MODE       工具调用模式: prompt (默认) 或 native
LLM_API_KEY              远程 API 密钥 (USE_LOCAL_LLM=false 时必填)
EMBEDDING_API_KEY        Embedding API 密钥 (默认复用 LLM_API_KEY)
EMBEDDING_MODEL          Embedding 模型 (默认 text-embedding-v3)
LOCAL_VL_MODEL_PATH      本地 merged 模型目录 (vLLM 启动时使用)
LOCAL_VL_DEVICE_MAP      模型加载设备分配 (默认 auto)
LOCAL_VL_TORCH_DTYPE     模型推理精度 (默认 float16)
INSPECTION_DB_URL        数据库连接 (默认 sqlite:///./inspection.db)
JWT_SECRET_KEY           JWT 签名密钥
INIT_ADMIN_USERNAME      初始管理员用户名
INIT_ADMIN_PASSWORD      初始管理员密码
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

## LLM 后端

### 本地 vLLM (默认)
```bash
# 终端 1: 启动 vLLM 服务
python scripts/launch_vllm.py

# 终端 2: 启动应用 (.env 已默认配置)
python app.py
```

### 远程 API (备用)
```bash
set USE_LOCAL_LLM=false
set LLM_API_KEY=sk-xxx
set LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
set LLM_MODEL=qwen3.6-flash-2026-04-16
python app.py
```

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
python scripts/launch_vllm.py           # 启动 vLLM 本地 LLM 服务
python app.py                           # Gradio Web UI
uvicorn api.main:app --port 8000        # FastAPI
python scripts/build_rag.py             # 构建 RAG 向量库
python -m pytest tests/ -v              # 测试
```
