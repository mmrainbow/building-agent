# RAG + Memory 三方合并记录

> 日期: 2026-06-01 | 分支: feature_1.1  
> 最后更新: 2026-06-02 (合并 local-model-update — 本地 VL 微调模型)

## 合并来源

```
feature_1.1 (orchestrator / tools / llm client / 模型 / 测试)
    │
    └── main (c79f1af)
          │
          ├── LBQ ── RAG (agent/rag.py, chroma_db/, Word文档解析)
          │
          └── feature_1.2 ── Memory + ReAct (memory_manager, 增强orchestrator, 测试脚本)
```

## 合并后文件结构

```
building-agent/
├── llm/                     # LLM 客户端 + Tool 封装 + Agent 工厂
│   ├── client.py            # 通义千问 API (OpenAI 兼容)
│   ├── tools.py             # 5 个 Tool (4 CV + search_knowledge)
│   └── agent_factory.py     # 共享 InspectionAgent 单例
├── agent/
│   ├── orchestrator.py      # ReAct Agent 主循环
│   ├── memory_manager.py    # 双层记忆 (近期消息 + 长期记忆提取)
│   ├── rag.py               # ChromaDB 规范检索 (search_regulations)
│   ├── graph.py/nodes.py    # 旧 DAG (保留，/predict API 用)
│   └── state.py             # InspectionState
├── api/
│   ├── chat.py              # Chat API (/chat/send, /chat/conversations)
│   ├── auth.py              # JWT 认证
│   ├── schemas.py           # Pydantic 模型
│   └── main.py              # FastAPI 入口
├── services/
│   ├── chat_service.py      # Gradio 智能问答 Tab (共用 agent_factory)
│   ├── inspection_service.py
│   ├── auth_service.py
│   ├── history_service.py
│   └── statistics_service.py
├── db/                      # 10 表数据模型 + CRUD
├── tests/                   # 42 个测试 (pytest)
├── rag_data/                # RAG 文档 (gitignore)
├── chroma_db/               # ChromaDB 向量库 (gitignore)
└── history_mk/              # 历史文档
```

## 关键修复

### 1. RAG 环境变量解耦
- `agent/rag.py`: `EMBEDDING_API_KEY` 独立配置，默认回退 `DASHSCOPE_API_KEY`
- `EMBEDDING_MODEL` → `text-embedding-v4`
- `agent/nodes.py`: 统一用 `DASHSCOPE_API_KEY`

### 2. RAG 文档目录整理
- 规范文档移入 `rag_data/`，加入 `.gitignore`
- `chroma_db/` 加入 `.gitignore`（38MB 二进制不再入库）
- `agent/rag.py` + `scripts/build_rag.py` 搜索路径从根目录改为 `rag_data/`

### 3. search_knowledge Tool 接入 ChromaDB
- `agent/rag.py`: 新增 `search_regulations(query, k)` 语义检索函数
- `llm/tools.py` KnowledgeSearchTool: 优先 ChromaDB 规范检索 → 回退 SQLite 用户记忆

### 4. 统一 Agent 实例
- 创建 `llm/agent_factory.py` 单例工厂
- `api/chat.py` 和 `services/chat_service.py` 共用同一 InspectionAgent
- 放在 `llm/` 下避免触发 `services/__init__.py` → `agent.graph` → YOLO 模型加载

### 5. Gradio 智能问答 Tab 升级
- 新增图片上传组件
- `chat_with_llm` 支持显式 `image` 参数
- 回复末尾显示 tool 调用摘要 (`🔧 已调用: classify_material, detect_defects`)

### 6. 测试脚本整理
- `scripts/test_agent_step1~4.py` + `test_memory.py` 移至 `tests/`
- 新增 `tests/test_chat.py` (7 个 Chat API 集成测试)
- 历史 .md 文件移入 `history_mk/`

## 架构：双系统并存

| | 旧系统 (graph.py) | 新系统 (orchestrator.py) |
|------|------|------|
| 入口 | `/predict` API, Gradio "图像巡检" Tab, CLI | `/chat/send` API, Gradio "智能问答" Tab |
| 调度 | 静态 DAG (4 predictor 全跑) | ReAct Agent (AI 自主选 Tool) |
| RAG | `retrieve_regulations()` 多维度检索 | `search_regulations()` 语义检索 |
| 记忆 | 无 | MemoryManager → ConversationMemory |
| 持久化 | InspectionRecord | ChatMessage + ConversationMemory |

## 当前 agent 实例架构

```
llm/agent_factory.py  ← 单例
       │
       ├── api/chat.py          (POST /chat/send)
       └── services/chat_service.py  (Gradio 智能问答 Tab)
```

导入链路安全（不含 torch/YOLO）:

```
llm/agent_factory.py
  → agent/orchestrator.py
    → agent/memory_manager.py
      → db/chat_crud.py + db/memory_crud.py
```
