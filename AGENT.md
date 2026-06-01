# AGENT.md — Building-Agent 项目上下文

## 项目简介
AI 驱动的建筑外立面巡检系统。上传建筑图片 → CV 模型检测材质/楼层/加层/隐患 → 通义千问 LLM 生成中文巡检报告。

技术栈: Python 3.10+, LangGraph, FastAPI, Gradio 4, SQLAlchemy 2, 通义千问 API (qwen3.6-flash), YOLO (ultralytics), PyTorch, OpenCV, ChromaDB

## 项目结构
```
agent/          LangGraph DAG + ReAct Agent (orchestrator, memory_manager, rag, graph/nodes/state)
predictors/     CV模型预测器 (材质/楼层/加层/隐患) — 全部继承 BasePredictor
llm/            LLM 客户端 + Tool + Agent工厂 + 对话核心
  client.py        通义千问 API (OpenAI 兼容)
  tools.py         5 个 Tool (4 CV + search_knowledge)
  agent_factory.py 共享 InspectionAgent 单例
  chat_core.py     run_chat() 核心对话逻辑
db/             SQLAlchemy ORM (10表, database, crud, chat_crud, memory_crud, feedback_crud)
api/            FastAPI 薄路由层 (auth JWT, schemas, main, chat)
services/       Gradio 适配层 (session管理 + UI回调 + 业务逻辑)
app.py          Gradio Web UI 主入口
main.py         CLI 命令行入口
rag_data/       RAG 规范文档 (gitignore)
chroma_db/      ChromaDB 向量库 (gitignore)
tests/          测试 (pytest + httpx, 42 个用例)
scripts/        RAG 索引构建 + PDF 提取工具
history_mk/    历史过程文档
```

## 职责划分
```
api/       → 薄层: 参数校验 + 认证 + 调用 service → 格式化响应
services/  → Gradio 适配: session 状态管理 + 上下文拼接 + UI 回调
llm/       → 核心逻辑: LLM客户端 + Tool + Agent工厂 + 对话核心
agent/     → Agent 编排: ReAct循环 + 双层记忆 + RAG 检索
db/        → 数据访问: SQLAlchemy ORM + CRUD
```

## 开发约定
- 文案、注释、报告、UI 统一中文
- 类型注解使用新语法: `list[dict]`, `str | None`
- API 认证用 JWT (python-jose)，密码用 bcrypt
- 数据库默认 SQLite，可通过 `INSPECTION_DB_URL` 切 MySQL
- LLM 调用走通义千问 DashScope API (OpenAI 兼容格式)
- Embedding 调用默认复用 LLM key，也可单独配置 `EMBEDDING_API_KEY`
- 环境变量命名: `UPPER_SNAKE_CASE`
- api/ 不写业务逻辑，调 llm/ 或 services/
- services 不依赖 FastAPI / Gradio 组件（auth_service 返回纯数据，UI 包装在 app.py）
- 新文件避免经过 `services/__init__.py` import 链（会触发 agent.graph → YOLO）

## 关键环境变量
```
DASHSCOPE_API_KEY    通义千问 API 密钥
LLM_MODEL            大模型名称 (默认 qwen-plus)
LLM_BASE_URL         API 地址 (默认 dashscope.aliyuncs.com/compatible-mode/v1)
EMBEDDING_API_KEY    Embedding API 密钥 (默认复用 DASHSCOPE_API_KEY)
EMBEDDING_MODEL      Embedding 模型 (默认 text-embedding-v4)
INSPECTION_DB_URL    数据库连接 (默认 sqlite:///./inspection.db)
JWT_SECRET_KEY       JWT 签名密钥
INIT_ADMIN_USERNAME  初始管理员用户名
INIT_ADMIN_PASSWORD  初始管理员密码
OLLAMA_BASE_URL      Ollama 地址 (旧路径兼容)
```

## 当前数据模型 (12 张表)
- **User**: id, username, password_hash, role, is_active, created_at, last_login_at
- **UserPreference**: id, user_id(FK,unique), language, report_style, preferred_model
- **InspectionRecord**: id, user_id(FK), report, created_at → images(ImageInspection)
- **ImageInspection**: id, record_id(FK), chat_image_id(FK→chat_images), image_name, material, floor, has_extension → defects
- **Defect**: id, image_id(FK→image_inspection), defect_type, area, box_coords(JSON)
- **Conversation**: id, user_id(FK), title, model, message_count, created_at, updated_at → messages
- **ChatMessage**: id, conversation_id(FK), role, content, metadata(JSON), created_at → images(ChatImage)
- **ChatImage**: id, message_id(FK), mime_type, data(BLOB) → inspection_images(ImageInspection)
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
POST /predict              上传图片 → 巡检结果 (旧 DAG)
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

## 双系统并存
| | 旧系统 (graph.py) | 新系统 (orchestrator.py) |
|------|------|------|
| 入口 | /predict, Gradio "图像巡检", CLI | /chat/send, Gradio "智能问答" |
| 调度 | 静态 DAG (4 predictor 全跑) | ReAct Agent (AI 自主选 Tool) |
| RAG | retrieve_regulations() 多维度 | search_regulations() 语义检索 |
| 记忆 | 无 | MemoryManager → ConversationMemory |
| 持久化 | InspectionRecord | ChatMessage |

## 禁止事项
- 不要删除 `models/` 下的 `.pt`/`.pth` 模型权重文件
- 不要提交 `.env`、`chroma_db/`、`rag_data/`、`*.docx`
- 不要在代码中硬编码密码、密钥或内网地址
- 修改数据模型后必须同步更新测试
- 新模块不要经过 `services/__init__.py` import 链
- 业务逻辑不放 app.py / api/ 层

## 相关文档
- `DEVELOPMENT_PLAN.md`        完整开发路线图
- `history_mk/merge_rag&memory.md` RAG+Memory 合并记录
- `history_mk/PROJECT_CO_BUILD.md` 项目共建文档
- `README.md`                  快速启动指南

## 当前开发阶段
阶段 1 主体完成 — Agent 框架 + RAG + Chat API + 对话系统 + Memory。下一步：阶段 2 反馈系统。

## 快速命令
```bash
python app.py                           # Gradio Web UI
uvicorn api.main:app --port 8000        # FastAPI
python -m pytest tests/ -v              # 测试 (42 passed)
```
