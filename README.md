# Building Agent

AI 驱动的建筑外立面巡检系统 — 三 Agent 协同架构。

| Agent | 模型 | 职责 |
|---|---|---|
| **Manager Agent** | 通义千问 qwen3.6-flash | 理解意图、调度 CV 工具、解读结果 |
| **Memory Agent** | 通义千问 qwen-turbo | 自动从对话中提取长期记忆 |
| **Report Agent** | 本地微调 Qwen2.5-VL-3B | 生成专业中文巡检报告 |

技术栈: Python 3.10+ / FastAPI / Vue 3 / SQLAlchemy 2 / ChromaDB / YOLO / PyTorch

---

## 前置条件

- **Conda 环境** `building-agent`，Python 3.10+
- **Node.js** 18+（前端）
- **阿里云百炼 API Key**（Manager + Memory Agent 调用通义千问）
- **CUDA**（可选，加速 CV 模型推理）
- 模型权重文件放入 `backend/model_weights/`（5 个 .pt/.pth 文件）
- 微调模型目录 `backend/qwen2_5_vl_3b_building_merged/`（Report Agent 需要）

---

## 启动方式

### 1. 安装依赖

```bash
# 后端
cd backend
pip install -r requirements.txt

# 前端
cd frontend
npm install
```

### 2. 配置 API Key

编辑 `backend/.env`，填入你的百炼 API Key：

```ini
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. 启动 Report Agent（可选但推荐）

打开终端 1：

```bash
cd backend
conda activate building-agent
python scripts/launch_local_llm.py
```

启动后监听 `http://127.0.0.1:8000`，提供 `/v1/report` 和 `/v1/chat/completions` 端点。

如果不启动 Report Agent，Manager 仍可调用 CV 工具分析图片，但无法生成最终巡检报告。

### 4. 启动后端 API

打开终端 2：

```bash
cd backend
conda activate building-agent
uvicorn api.main:app --host 0.0.0.0 --port 8001
```

后端运行在 `http://localhost:8001`。

如果 Report Agent 已占用了 8000 端口，记得换一个端口（如 8001）。

### 5. 启动前端

打开终端 3：

```bash
cd frontend
npm run dev
```

前端运行在 `http://localhost:5173`，请求自动代理到后端。

---

## 启动总结（三条命令）

```bash
# 终端 1 — Report Agent
cd backend && conda activate building-agent && python scripts/launch_local_llm.py

# 终端 2 — 后端 API
cd backend && conda activate building-agent && uvicorn api.main:app --host 0.0.0.0 --port 8001

# 终端 3 — 前端
cd frontend && npm run dev
```

---

## API 端点

### 认证（公开）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/register` | 用户注册 |
| POST | `/login` | JSON 登录 |
| POST | `/token` | OAuth2 表单登录 |
| POST | `/token/refresh` | 刷新 JWT |

### 巡检（需 JWT）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/inspection/multi` | 多图巡检 (SSE 流式进度) |
| GET | `/history` | 巡检列表（分页） |
| GET | `/history/{id}` | 单条详情 |
| GET | `/history/{id}/export?format=xlsx\|docx\|md` | 导出报告（含标注图） |
| GET | `/history/images/{id}/{kind}` | 原图/标注图 |

### 对话（需 JWT）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/chat/send` | 发送消息（支持多图） |
| POST | `/chat/send/stream` | SSE 流式问答（CoT 实时推送） |
| GET | `/chat/conversations` | 对话列表 |
| GET | `/chat/conversations/{id}` | 对话详情（含反馈） |
| DELETE | `/chat/conversations/{id}` | 删除对话 |
| GET | `/chat/memories` | 对话记忆列表 |
| DELETE | `/chat/memories/{id}` | 删除单条记忆 |
| POST | `/chat/messages/{id}/feedback` | AI 回复评分/反馈 |

### 管理（需 admin）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/users` | 用户列表 |
| GET | `/admin/dashboard` | 统计看板 |
| GET | `/admin/feedbacks` | 反馈列表 |

### 运维
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/agent/status` | Agent 监控 |

---

## 关键环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `LLM_API_KEY` | 百炼 API Key | 必填 |
| `LLM_MODEL` | Manager 模型 | `qwen3.6-flash` |
| `MEMORY_LLM_MODEL` | Memory Agent 模型 | `qwen-turbo` |
| `REPORT_AGENT_URL` | Report Agent 地址 | `http://localhost:8000` |
| `INSPECTION_DB_URL` | 数据库连接 | `sqlite:///./inspection.db` |
| `JWT_SECRET_KEY` | JWT 签名密钥 | 必填 |
| `MEMORY_EXTRACT_THRESHOLD` | 记忆提取阈值 | `6000` |
| `INIT_USERNAME` | 初始用户名 | `user123` |
| `INIT_PASSWORD` | 初始用户密码 | `user123` |
| `INIT_ADMIN_USERNAME` | 初始管理员 | `admin` |
| `INIT_ADMIN_PASSWORD` | 初始管理员密码 | `admin123456` |
