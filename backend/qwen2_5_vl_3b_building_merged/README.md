# Qwen2.5-VL-3B 建筑外立面巡检微调模型

## 模型概述

| 项目 | 说明 |
|------|------|
| **基座模型** | Qwen2.5-VL-3B-Instruct |
| **微调方式** | LoRA (Low-Rank Adaptation) |
| **用途** | 建筑外立面巡检报告生成 |
| **架构** | Qwen2_5_VLForConditionalGeneration |
| **精度** | float16 |
| **显存需求** | 约 8 GB (float16)，可调整 `max_pixels` 降低 |
| **合并日期** | 2026-05-31 |

## 文件清单

```
qwen2_5_vl_3b_building_merged/
├── model-00001-of-00002.safetensors   # 权重分片 1 (~4.6 GB)
├── model-00002-of-00002.safetensors   # 权重分片 2 (~2.4 GB)
├── model.safetensors.index.json       # 权重索引
├── config.json                        # 模型结构配置
├── generation_config.json             # 生成参数默认值
├── tokenizer.json                     # 分词器 (~11 MB)
├── tokenizer_config.json              # 分词器配置
├── preprocessor_config.json           # 图像预处理配置
├── processor_config.json              # 处理器综合配置
├── chat_template.jinja               # 对话模板
└── args.json                          # 训练超参数记录
```

## 模型结构

从 `config.json` 提取的关键参数：

| 参数 | 值 |
|------|-----|
| 隐藏层维度 | 2048 |
| Transformer 层数 | 36 |
| 注意力头数 | 16 |
| KV 头数 | 2 (GQA) |
| 词表大小 | 151,936 |
| 最大位置编码 | 128,000 |
| 视觉编码器深度 | 32 |
| 视觉隐藏层维度 | 1280 |
| Patch 大小 | 14×14 |
| 空间合并大小 | 2×2 |

## 训练参数

从 `args.json` 提取：

| 参数 | 值 |
|------|-----|
| 每设备 batch size | 1 |
| 梯度累积步数 | 8 |
| 训练轮数 | 1 |
| 最大步数 | 1000 |
| 学习率 | 3e-05 |
| 学习率调度 | cosine |
| 优化器 | adamw_torch |
| 权重衰减 | 0.1 |
| 精度 | fp16 |
| 梯度检查点 | 开启 |

## 在本项目中的使用

### 方式一：FastAPI 本地服务（主 Agent，默认，Windows 原生）

将模型部署为 OpenAI 兼容 API，供 ReAct Agent 调用：

```bash
python scripts/launch_local_llm.py
```
（模型路径已在 .env 中配置为 `./qwen2_5_vl_3b_building_merged`）

启动后访问 `http://localhost:8000/v1/chat/completions`。

`.env` 中已默认配置：
```ini
USE_LOCAL_LLM=true
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=qwen2.5-vl-building
LLM_TOOL_CALL_MODE=prompt
```

### 方式二：transformers 直接加载（本地 VL 报告生成）

在 `agent/nodes.py` 已删除的 DAG 路径中原有此功能。如需在别处直接调用：

```python
from llm.local_vl_model import generate_local_inspection_report

report = generate_local_inspection_report(
    image_path="building.jpg",
    material="Coating",
    floor="18层",
    has_extension="无加层",
    defects=[{"id": 1, "type": "渗水", "area": 54029.5}],
)
print(report)
```

环境变量配置：

| 变量 | 推荐值 | 说明 |
|------|--------|------|
| `LOCAL_VL_MODEL_ENABLED` | `true` | 启用本地 VL |
| `LOCAL_VL_MODEL_PATH` | `./qwen2_5_vl_3b_building_merged` | 模型路径 |
| `LOCAL_VL_DEVICE_MAP` | `auto` | 设备分配 |
| `LOCAL_VL_TORCH_DTYPE` | `float16` | 推理精度 |
| `LOCAL_VL_MAX_NEW_TOKENS` | `512` | 最大生成长度 |
| `LOCAL_VL_MAX_PIXELS` | `131072` | 图像最大像素 |

### 显存不足时

```bash
set LOCAL_VL_MAX_PIXELS=65536
set LOCAL_VL_MAX_NEW_TOKENS=256
```

## 代码集成点

项目中使用此模型的代码：

| 文件 | 用途 |
|------|------|
| `llm/local_vl_model.py` | 模型加载、推理、报告生成 |
| `scripts/launch_local_llm.py` | FastAPI 本地 OpenAI 兼容服务启动 |
| `llm/agent_factory.py` | Agent 单例 (默认 localhost:8000) |
| `llm/client.py` | LLM 客户端 (tool_call prompt 回退) |

## 获取方式

此模型通过以下途径获取（不在 GitHub 仓库中）：

- 网盘 / 移动硬盘 / NAS 传输
- HuggingFace 私有仓库
- ModelScope 私有仓库

> `.gitignore` 已配置忽略 `outputs/` 目录，防止意外提交大文件。

## 训练来源

- 基座: `Qwen2.5-VL-3B-Instruct`
- LoRA 微调产物: `outputs/qwen2_5_vl_3b_building_lora_run2/v0-20260531-032509`
- 合并命令 (ms-swift): 将 LoRA adapter 合并到基座模型得到本目录

## 相关文档

- `history_mk/微调模型本地调用说明.md` — 详细的本地调用说明
- `history_mk/LLM_FINE_TUNING_GUIDE.md` — 微调执行手册
- `AGENT.md` — 项目整体架构文档
