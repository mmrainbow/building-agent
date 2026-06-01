# 数据库表结构

> 引擎: SQLAlchemy 2 + SQLite（可切换 MySQL）  
> 文件: `db/models.py`  
> 总计: 12 张表，3 个枚举

---

## ER 图

```
users ─── 1:N ─── inspection_records ─── 1:N ─── inspection_images ─── 1:N ─── defects
  │
  ├── 1:N ─── conversations ─── 1:N ─── chat_messages ─── 1:N ─── chat_images
  │
  ├── 1:N ─── conversation_memories
  ├── 1:N ─── feedbacks ─── → inspection_records / chat_messages
  ├── 1:1 ─── user_preferences
  │
knowledge_documents ─── 1:N ─── knowledge_chunks
```

---

## 枚举定义

### UserRole
| 值 | 含义 |
|------|------|
| `user` | 默认角色，普通用户 |
| `admin` | 管理员，可查看所有记录和用户列表 |

### MemoryType
| 值 | 含义 | 提取场景 |
|------|------|---------|
| `user_fact` | 用户身份/偏好/需求 | 用户说“我是XX区住建局的人” |
| `building_info` | 讨论过的建筑特征 | 用户问“上次那个面砖楼…” |
| `preference` | 用户明确表达的偏好变更 | 用户说“以后报告改简短版” |
| `summary` | 对话阶段摘要 | 超过 10 轮对话自动压缩 |

### FeedbackType
| 值 | 含义 |
|------|------|
| `inspection_correction` | 巡检结果纠错（材质、隐患类型等） |
| `chat_rating` | 对话消息质量评分 |
| `report_rating` | 巡检报告整体评价 |

---

## 1. users — 用户表

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, AUTO | |
| `username` | VARCHAR(50) | UNIQUE, NOT NULL | |
| `password_hash` | VARCHAR(255) | NOT NULL | bcrypt 哈希 |
| `role` | ENUM | NOT NULL, DEFAULT inspector | inspector / admin |
| `is_active` | BOOLEAN | DEFAULT TRUE | 软删除标记 |
| `created_at` | DATETIME | DEFAULT NOW | |
| `last_login_at` | DATETIME | NULLABLE | |

**关联子表**（级联删除）:
- `inspection_records` (1:N)
- `conversations` (1:N)
- `conversation_memories` (1:N)
- `feedbacks` (1:N)
- `user_preferences` (1:1)

---

## 2. inspection_records — 巡检会话

一次巡检 = 对同一建筑的多张图片进行检测，汇总生成一份报告。

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, AUTO | |
| `user_id` | INTEGER | FK→users.id, NOT NULL | |
| `report` | TEXT | | 综合所有图片汇总生成的巡检报告 |
| `created_at` | DATETIME | DEFAULT NOW | |

**关联**:
- → `inspection_images` (1:N, 级联删除)

---

## 3. inspection_images — 巡检图片

每张图片有独立的检测结果。

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, AUTO | |
| `record_id` | INTEGER | FK→inspection_records.id, CASCADE | |
| `image_name` | VARCHAR(255) | | 上传文件名 |
| `material` | VARCHAR(100) | | 材质检测结果 |
| `floor` | VARCHAR(20) | | 楼层估算 |
| `has_extension` | VARCHAR(20) | | 加层检测 |
| `created_at` | DATETIME | DEFAULT NOW | |

**关联**:
- → `defects` (1:N, 级联删除)

---

## 4. defects — 图片级隐患

每条隐患属于一张巡检图片。

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, AUTO | |
| `image_id` | INTEGER | FK→inspection_images.id, CASCADE | |
| `defect_type` | VARCHAR(50) | | 空鼓 / 渗水 / 脱落 / 裂缝 |
| `area` | FLOAT | | 面积（像素²） |
| `box_coords` | JSON | | 坐标框 |

---

## 5. conversations — 对话会话

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, AUTO | |
| `user_id` | INTEGER | FK→users.id, NOT NULL | |
| `title` | VARCHAR(255) | | 由首次提问自动生成，可手动修改 |
| `model` | VARCHAR(100) | | 使用的 LLM 模型名 |
| `message_count` | INTEGER | DEFAULT 0 | 冗余字段，避免 COUNT 查询 |
| `created_at` | DATETIME | DEFAULT NOW | |
| `updated_at` | DATETIME | DEFAULT NOW, ON UPDATE | 新消息时自动更新 |

**关联**:
- → `chat_messages` (1:N, 级联删除, 按 created_at 正序)

---

## 6. chat_messages

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, AUTO | |
| `conversation_id` | INTEGER | FK→conversations.id, CASCADE | |
| `role` | VARCHAR(20) | NOT NULL | user / assistant / system |
| `content` | TEXT | NOT NULL | 消息正文 |
| `metadata` | JSON | | `{tool_calls, tokens, latency_ms, sources}` |
| `created_at` | DATETIME | DEFAULT NOW | |

---

## 7. chat_images — 对话图片

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, AUTO | |
| `message_id` | INTEGER | FK→chat_messages.id, CASCADE | 属于哪条消息 |
| `mime_type` | VARCHAR(50) | DEFAULT 'image/jpeg' | |
| `data` | BLOB | NOT NULL | JPEG 图片字节 |
| `created_at` | DATETIME | DEFAULT NOW | |

> 图片以 BLOB 存入数据库，项目移动不丢数据。  
> 渲染时 BLOB → 缓存文件 `chat_images/{message_id}.jpg` → Gradio 展示。  
> 缓存文件可随时从数据库重建。

---

## 8. conversation_memories — 长期记忆

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, AUTO | |
| `user_id` | INTEGER | FK→users.id, NOT NULL | |
| `conversation_id` | INTEGER | FK→conversations.id, SET NULL | NULL=跨对话记忆 |
| `memory_type` | VARCHAR(30) | NOT NULL | user_fact / building_info / preference / summary |
| `key` | VARCHAR(255) | | upsert 去重键 (user_id+type+key) |
| `content` | TEXT | NOT NULL | 记忆正文 |
| `chroma_id` | VARCHAR(255) | NULLABLE | 阶段1B 填充，ChromaDB 向量 ID |
| `importance` | FLOAT | DEFAULT 0.5 | 0-1，影响检索优先级和淘汰 |
| `access_count` | INTEGER | DEFAULT 0 | 热度指标 |
| `last_accessed_at` | DATETIME | NULLABLE | |
| `created_at` | DATETIME | DEFAULT NOW | |

**当前检索方式**: SQL LIKE（`search_memories_by_keyword`）  
**计划升级**: ChromaDB 向量检索（`chroma_id` 预留字段）

---

## 9. user_preferences — 用户偏好

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, AUTO | |
| `user_id` | INTEGER | FK→users.id, UNIQUE, NOT NULL | 1:1 绑定 |
| `language` | VARCHAR(10) | DEFAULT 'zh' | |
| `report_style` | VARCHAR(20) | DEFAULT 'standard' | brief / standard / detailed |
| `preferred_model` | VARCHAR(100) | | 用户偏好的 LLM 模型 |
| `extra` | JSON | | 扩展字段 |
| `updated_at` | DATETIME | DEFAULT NOW, ON UPDATE | |

---

## 10. feedbacks — 用户反馈

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, AUTO | |
| `user_id` | INTEGER | FK→users.id, NOT NULL | |
| `record_id` | INTEGER | FK→inspection_records.id, SET NULL | 巡检纠错时非空 |
| `message_id` | INTEGER | FK→chat_messages.id, SET NULL | 对话评分时非空 |
| `feedback_type` | VARCHAR(30) | NOT NULL | inspection_correction / chat_rating / report_rating |
| `target_field` | VARCHAR(100) | | 被纠错字段，如 "material" |
| `original_value` | TEXT | | 模型原始输出 |
| `corrected_value` | TEXT | | 用户修正值 |
| `rating` | INTEGER | | 1-5 星 |
| `comment` | TEXT | | 文字评价 |
| `created_at` | DATETIME | DEFAULT NOW | |

**Upsert 策略**: 同用户对同目标同字段的反馈以最新为准（`feedback_crud.create_feedback`）

---

## 11. knowledge_documents — 知识库文档

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, AUTO | |
| `title` | VARCHAR(255) | NOT NULL | |
| `file_name` | VARCHAR(255) | | 原始文件名 |
| `file_type` | VARCHAR(20) | | pdf / md / txt |
| `source_type` | VARCHAR(50) | | regulation / manual / report_template / general |
| `chunk_count` | INTEGER | DEFAULT 0 | 冗余字段 |
| `status` | VARCHAR(20) | DEFAULT 'active' | active / archived |
| `created_at` | DATETIME | DEFAULT NOW | |

**关联**:
- → `knowledge_chunks` (1:N, 级联删除)

---

## 12. knowledge_chunks — 知识库分块

| 列名 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PK, AUTO | |
| `document_id` | INTEGER | FK→knowledge_documents.id, CASCADE | |
| `chunk_index` | INTEGER | NOT NULL | 分块序号（按原文顺序） |
| `content` | TEXT | NOT NULL | 分块文本 |
| `chroma_id` | VARCHAR(255) | | ChromaDB 向量 ID |
| `metadata` | JSON | | `{page, section_title}` |
| `created_at` | DATETIME | DEFAULT NOW | |

> 注意: `knowledge_documents` 和 `knowledge_chunks` 存储的是**元数据**。  
> 实际的向量检索走 ChromaDB (`chroma_db/`)，通过 `agent/rag.py` 调用。  
> 这两个表主要用于：文档管理（增删查）、chunk 溯源（"这段规范来自哪个文档第几页"）。
