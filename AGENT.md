# AGENT.md — Building-Agent 项目上下文

## 项目简介
AI 驱动的建筑外立面巡检系统。上传建筑图片 → CV 模型检测材质/楼层/加层/隐患 → 通义千问 LLM 生成中文巡检报告。

技术栈: Python 3.10+, LangGraph, FastAPI, Gradio 4, SQLAlchemy 2, 通义千问 API (qwen-plus), YOLO (ultralytics), PyTorch, OpenCV, ChromaDB

## 项目结构
```
agent/          LangGraph 工作流 + ReAct Agent (orchestrator, memory_manager, graph/nodes/state)
predictors/     CV模型预测器 (材质/楼层/加层/隐患) — 全部继承 BasePredictor
llm/            LLM 客户端 + Tool 封装 (通义千问 API, tools.py)
db/             SQLAlchemy ORM (10表, database, crud, chat_crud, memory_crud, feedback_crud)
api/            FastAPI REST 路由 (auth JWT, schemas, main, chat)
services/       业务逻辑层 (auth, inspection, history, statistics, chat)
app.py          Gradio Web UI 主入口 (146行，薄路由层)
main.py         CLI 命令行入口
models/         模型权重文件 (不纳入 Git)
tests/          测试 (pytest + httpx, 35 个用例)
knowledge/      知识库 RAG 模块 (ChromaDB 向量检索)
```

## 开发约定
- 文案、注释、报告、UI 统一中文
- 类型注解使用新语法: `list[dict]` 而非 `List[Dict]`，`str | None` 而非 `Optional[str]`
- 密码处理用 bcrypt，API 认证用 JWT (python-jose)
- 数据库默认 SQLite (`sqlite:///./inspection.db`)，可通过 `INSPECTION_DB_URL` 环境变量切 MySQL
- LLM 调用通过 Ollama 本地 HTTP API: `{OLLAMA_BASE_URL}/api/generate` 或 `/api/chat`
- 环境变量命名: `UPPER_SNAKE_CASE`
- 所有依赖列在 `requirements.txt`
- API 新增端点需在 `api/schemas.py` 中定义 Pydantic 模型
- 业务逻辑不放 `app.py`，放在 `services/` 对应模块中

## 关键环境变量
```
INSPECTION_DB_URL    数据库连接 (默认 sqlite:///./inspection.db)
OLLAMA_BASE_URL      Ollama 地址 (默认 http://localhost:11434)
OLLAMA_MODEL         模型名 (默认 qwen2:1.5b)
INIT_ADMIN_USERNAME  初始管理员用户名
INIT_ADMIN_PASSWORD  初始管理员密码 (仅首次启动时用于创建账号)
JWT_SECRET_KEY       JWT 签名密钥 (生产环境必须修改)
DASHSCOPE_API_KEY    通义千问 API 密钥
LLM_MODEL            大模型名称 (默认 qwen-plus)
LLM_BASE_URL         API 地址 (默认 https://dashscope.aliyuncs.com/compatible-mode/v1)
```

## 当前数据模型

### 用户与权限
- **User**: id, username, password_hash, role (inspector/admin), is_active, created_at, last_login_at
- **UserPreference**: id, user_id(FK,unique), language, report_style, preferred_model, extra(JSON)

### 巡检
- **InspectionRecord**: id, user_id(FK), image_name, material, floor, has_extension, report, created_at → defects
- **Defect**: id, record_id(FK), defect_type, area, box_coords(JSON)

### 对话与记忆
- **Conversation**: id, user_id(FK), title, model, message_count, created_at, updated_at → messages
- **ChatMessage**: id, conversation_id(FK), role, content, metadata(JSON), created_at
- **ConversationMemory**: id, user_id(FK), conversation_id(FK), memory_type, key, content, chroma_id, importance, access_count

### 反馈
- **Feedback**: id, user_id(FK), record_id(FK), message_id(FK), feedback_type, target_field, original_value, corrected_value, rating, comment

### 知识库 (阶段1B)
- **KnowledgeDocument**: id, title, file_name, file_type, source_type, chunk_count, status
- **KnowledgeChunk**: id, document_id(FK), chunk_index, content, chroma_id, metadata(JSON)

## API 端点

### 认证（公开）
```
POST /register          用户注册
POST /token             登录获取 JWT（OAuth2 form，Swagger UI 用）
POST /login             登录获取 JWT（JSON，API 客户端用）
POST /token/refresh     刷新 access token
```

### 核心业务（需 JWT）
```
POST /predict           上传图片 → 巡检结果
GET  /history           巡检记录列表 (分页)
GET  /history/{id}      单条记录详情
GET  /statistics        统计数据
```

### 管理（需 admin 角色）
```
GET  /admin/users       用户列表
```

### 运维（公开）
```
GET  /health            数据库 + Ollama + 模型文件状态
```

## 禁止事项
- 不要删除或修改 `models/` 下的 `.pt`/`.pth` 模型权重文件
- 不要提交 `.env` 文件或任何含密码/密钥的文件
- 不要在代码中硬编码密码、密钥或内网地址
- 修改数据库模型后必须同步更新测试
- 不要引入不必要的新依赖，优先用现有依赖栈解决问题
- 不要将业务逻辑写入 app.py，应放在 services/ 对应模块

## 相关文档
- `DEVELOPMENT_PLAN.md`  — 完整四阶段开发路线图 + 任务清单 + CC 提示词模板
- `history_mk/PROJECT_CO_BUILD.md`    — 项目共建文档 (定位/决策/变更日志)
- `README.md`              — 快速启动指南
- `.env.example`           — 环境变量模板

## 当前开发阶段
阶段 1.1-1.3 已完成 — llm/client.py (通义千问 API)、llm/tools.py (5 个 Tool)、agent/orchestrator.py (ReAct Agent)。下一步：1.5 Chat API (api/chat.py)，1.4 Memory+RAG 延后。

## 快速命令
```bash
python app.py                           # 启动 Gradio Web UI
python main.py                          # CLI 单张图片巡检
uvicorn api.main:app --port 8000        # 启动 FastAPI
python -m pytest tests/ -v              # 运行测试 (35 passed)
ruff check .                            # Lint 检查
```
