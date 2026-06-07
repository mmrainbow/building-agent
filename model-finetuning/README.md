# 建筑外立面多模态模型微调模块

本目录是项目中独立的模型微调部分，用于保存可公开的脚本、配置模板和复现实验说明。它不会影响 `backend/` 和 `frontend/` 的启动运行。

## 目录内容

```text
model-finetuning/
├─ README.md
├─ .gitignore
├─ dataset-builder/
│  ├─ README.md
│  ├─ config/config.example.json
│  └─ scripts/
│     ├─ split_dataset.py
│     ├─ extract_cv_features.py
│     ├─ build_rule_jsonl.py
│     ├─ build_teacher_jsonl.py
│     ├─ export_sft_jsonl.py
│     ├─ export_lora_jsonl.py
│     ├─ common.py
│     └─ question_bank.py
└─ scripts/
   ├─ evaluate_ollama_baseline.py
   ├─ evaluate_local_report_agent.py
   └─ compare_model_outputs.py
```

## 不上传的内容

为避免仓库过大或泄露敏感信息，本目录不会提交：

- 原始图片、训练集、验证集、测试集成品。
- 评测结果、对比报告、日志输出。
- LoRA checkpoint、合并模型、HuggingFace/Ollama 权重。
- 本机 `config.json`、`.env`、API Key。

## 微调目标

本项目采用“CV 结构化检测 + 多模态大模型报告生成”的路线：

- CV 模型负责识别外立面材质、楼层、加层和隐患。
- 教师模型 API 负责生成中文参考答案。
- Qwen2.5-VL-3B-Instruct 通过 LoRA 学习住建巡检报告风格。
- 合并后的本地模型作为项目中的 `Report Agent`，负责生成专业中文巡检报告。

微调重点是提升专业表达、格式稳定性、事实约束和处置建议质量，而不是替代已有 CV 检测模型。

## 端到端流程

### 1. 准备配置

```powershell
Copy-Item "model-finetuning/dataset-builder/config/config.example.json" `
  "model-finetuning/dataset-builder/config/config.json"
```

修改 `config.json`：

- `images_dir`：建筑外立面图片目录。
- `split.val_size`：建议 200。
- `split.test_size`：建议 200。
- `models`：项目 CV 权重路径。

### 2. 划分数据集

```powershell
python "model-finetuning/dataset-builder/scripts/split_dataset.py" `
  --config "config/config.json" `
  --out-dir "output/splits"
```

约 1776 张图片时，推荐划分为：训练集约 1376 张、验证集 200 张、测试集 200 张。

### 3. 提取结构化特征

```powershell
python "model-finetuning/dataset-builder/scripts/extract_cv_features.py" `
  --config "config/config.json" `
  --input-csv "output/splits/all_splits.csv" `
  --output-csv "output/features/features.csv" `
  --output-jsonl "output/features/features.jsonl"
```

输出字段包括：

- `material`：外立面材质。
- `floor`：楼层。
- `has_extension`：是否加层。
- `defects_json`：隐患类型和像素面积。

注意：隐患 `area` 是像素面积，只能作为相对大小参考，不能换算成平方米。

### 4. 使用教师模型生成参考答案

```powershell
$env:TEACHER_BASE_URL="https://你的教师模型地址/v1"
$env:TEACHER_API_KEY="你的教师模型密钥"
$env:TEACHER_MODEL="deepseek-v4-pro"

python "model-finetuning/dataset-builder/scripts/build_teacher_jsonl.py" `
  --config "config/config.json" `
  --features-csv "output/features/features.csv" `
  --target-split "train" `
  --output-jsonl "output/jsonl/train_teacher.jsonl" `
  --review-csv "output/jsonl/manual_review_train_teacher.csv" `
  --text-only `
  --qa-per-image 1
```

验证集和测试集分别把 `--target-split` 改为 `val`、`test`，并修改输出文件名。

重要原则：教师模型不能使用待评测的本地模型，否则会造成训练和评测污染。

### 5. 转换为 LoRA 数据

```powershell
python "model-finetuning/dataset-builder/scripts/export_lora_jsonl.py" `
  --input "model-finetuning/dataset-builder/output/jsonl/train_teacher.jsonl" `
  --output "model-finetuning/data/train_lora.jsonl"

python "model-finetuning/dataset-builder/scripts/export_lora_jsonl.py" `
  --input "model-finetuning/dataset-builder/output/jsonl/val_teacher.jsonl" `
  --output "model-finetuning/data/val_lora.jsonl"
```

输出样例：

```json
{
  "messages": [
    {"role": "user", "content": "<image>\n请生成住建巡检报告..."},
    {"role": "assistant", "content": "根据现场图像与结构化检测结果..."}
  ],
  "images": ["D:/path/to/image.jpg"]
}
```

### 6. LoRA 微调建议

推荐基座模型：

```text
Qwen/Qwen2.5-VL-3B-Instruct
```

本机 8GB 显存建议参数：

```powershell
swift sft `
  --model D:/models/Qwen2.5-VL-3B-Instruct `
  --sft_type lora `
  --dataset D:/pycharm/py_project/agent/model-finetuning/data/train_lora.jsonl `
  --val_dataset D:/pycharm/py_project/agent/model-finetuning/data/val_lora.jsonl `
  --torch_dtype float16 `
  --per_device_train_batch_size 1 `
  --per_device_eval_batch_size 1 `
  --gradient_accumulation_steps 8 `
  --learning_rate 1e-4 `
  --lora_rank 4 `
  --lora_alpha 8 `
  --max_length 512 `
  --save_steps 50 `
  --eval_steps 100 `
  --output_dir D:/pycharm/py_project/agent/outputs/qwen2_5_vl_3b_building_lora
```

建议先用 `--max_steps 5` 跑通流程，再扩大到 100 步或更多。

### 7. 部署本地微调模型

LoRA 合并后得到本地模型目录，例如：

```text
D:\pycharm\py_project\agent\qwen2_5_vl_3b_building_merged
```

启动本地 Report Agent：

```powershell
cd D:\pycharm\py_project\agent\backend
python scripts\launch_local_llm.py `
  --model "D:\pycharm\py_project\agent\qwen2_5_vl_3b_building_merged" `
  --port 8000
```

项目主后端通过 `REPORT_AGENT_URL=http://127.0.0.1:8000` 调用本地模型。

## 评测与对比

评测 Ollama 基线：

```powershell
python "model-finetuning/scripts/evaluate_ollama_baseline.py" `
  --model "qwen3-vl:8b" `
  --eval-set "model-finetuning/data/eval_set.jsonl" `
  --output "model-finetuning/results/baseline_qwen3_vl_8b.jsonl" `
  --system-prompt "你是住建巡检报告助手，请结合图像与输入信息输出正式、客观、简洁的中文内容。" `
  --temperature 0 `
  --top-p 1 `
  --num-ctx 4096 `
  --resume
```

评测本地微调 Report Agent：

```powershell
python "model-finetuning/scripts/evaluate_local_report_agent.py" `
  --eval-set "model-finetuning/data/eval_set.jsonl" `
  --output "model-finetuning/results/ft_qwen2_5_vl_3b_report_agent.jsonl" `
  --base-url "http://127.0.0.1:8000" `
  --resume
```

生成对比报告：

```powershell
python "model-finetuning/scripts/compare_model_outputs.py" `
  --baseline "model-finetuning/results/baseline_qwen3_vl_8b.jsonl" `
  --finetuned "model-finetuning/results/ft_qwen2_5_vl_3b_report_agent.jsonl" `
  --report "model-finetuning/reports/compare_summary.md"
```

## 汇报亮点

- 形成了“图片数据 → CV 结构化检测 → 教师模型标注 → LoRA 微调 → 本地部署 → 固定评测”的完整闭环。
- 微调模型与项目多 Agent 架构结合，专门承担 `Report Agent`。
- 测试集独立保留，支持基线模型与微调模型公平对比。
- 数据和权重不进入 GitHub，仓库只保留可复现代码和说明。
