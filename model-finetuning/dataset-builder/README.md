# 数据集构建流水线

本目录负责把建筑外立面图片整理成可训练、可验证、可评测的多模态数据集。它是本地模型微调流程的前半部分。

## 核心原则

- **先结构化，再生成文本**：先用项目已有 CV 模型得到材质、楼层、加层、隐患，再让教师模型生成中文报告或问答。
- **教师模型不能是目标模型**：训练和评测参考答案不能由待评测的本地模型自己生成。
- **测试集必须隔离**：`test` 只用于最终评测，不参与训练。
- **像素面积不能换算真实面积**：隐患中的 `area` 是图像像素面积 `px`，只能作为相对大小参考。
- **自动生成后建议抽样复核**：尤其是加层、隐患严重程度、处置建议等内容。

## 目录结构

```text
dataset-builder/
├─ README.md
├─ config/
│  ├─ config.example.json
│  └─ config.json
├─ scripts/
│  ├─ common.py
│  ├─ question_bank.py
│  ├─ split_dataset.py
│  ├─ extract_cv_features.py
│  ├─ build_rule_jsonl.py
│  ├─ export_sft_jsonl.py
│  ├─ build_teacher_jsonl.py
│  └─ export_lora_jsonl.py
└─ output/
   ├─ splits/
   ├─ features/
   ├─ jsonl/
   └─ logs/
```

## 第 0 步：准备配置

复制配置模板：

```powershell
Copy-Item "model-finetuning/dataset-builder/config/config.example.json" "model-finetuning/dataset-builder/config/config.json"
```

修改 `config.json`：

- `images_dir`：原始图片目录。
- `image_extensions`：图片后缀，如 `.jpg`、`.jpeg`、`.png`。
- `split.val_size`：验证集数量，建议 `200`。
- `split.test_size`：测试集数量，建议 `200`。
- `split.seed`：随机种子，固定后可复现划分。
- `models`：四个 CV 检测模型权重路径。

## 第 1 步：划分 train / val / test

```powershell
python "model-finetuning/dataset-builder/scripts/split_dataset.py" `
  --config "config/config.json" `
  --out-dir "output/splits"
```

输出：

- `output/splits/train.csv`
- `output/splits/val.csv`
- `output/splits/test.csv`
- `output/splits/all_splits.csv`

如果总图片为 1776 张，且 `val=200`、`test=200`，则训练集约为 1376 张。

## 第 2 步：提取结构化检测结果

```powershell
python "model-finetuning/dataset-builder/scripts/extract_cv_features.py" `
  --config "config/config.json" `
  --input-csv "output/splits/all_splits.csv" `
  --output-csv "output/features/features.csv" `
  --output-jsonl "output/features/features.jsonl"
```

输出字段包括：

- `material`：外立面材质。
- `floor`：楼层估计。
- `has_extension`：是否存在加层。
- `defects_json`：隐患列表，包含类型和像素面积。
- `split`：样本所属集合。
- `image` / `file_path`：图片路径。

这些结构化结果会成为后续教师答案和模型输入的重要依据。

## 第 3 步：规则模板生成初稿

```powershell
python "model-finetuning/dataset-builder/scripts/build_rule_jsonl.py" `
  --config "config/config.json" `
  --features-csv "output/features/features.csv" `
  --target-split "test" `
  --output-jsonl "output/jsonl/eval_set_generated.jsonl" `
  --review-csv "output/jsonl/manual_review.csv"
```

该脚本主要用于快速生成初稿和人工复核表。它不会调用大模型，适合检查字段是否齐全、问题类型是否正常。

问题模板来自：

```text
model-finetuning/dataset-builder/scripts/question_bank.py
```

当前任务类型覆盖：

- 巡检报告生成
- 住建管理建议
- 普通用户解释
- 加层合规复核
- 隐患维修建议
- 后续巡检关注点
- 材质维护问答

## 第 4 步：教师模型生成高质量参考答案

设置教师模型环境变量：

```powershell
$env:TEACHER_BASE_URL="https://你的教师模型地址/v1"
$env:TEACHER_API_KEY="你的教师模型密钥"
$env:TEACHER_MODEL="deepseek-v4-pro"
```

生成训练集：

```powershell
python "model-finetuning/dataset-builder/scripts/build_teacher_jsonl.py" `
  --config "config/config.json" `
  --features-csv "output/features/features.csv" `
  --target-split "train" `
  --output-jsonl "output/jsonl/train_teacher.jsonl" `
  --review-csv "output/jsonl/manual_review_train_teacher.csv" `
  --text-only `
  --qa-per-image 1
```

生成验证集：

```powershell
python "model-finetuning/dataset-builder/scripts/build_teacher_jsonl.py" `
  --config "config/config.json" `
  --features-csv "output/features/features.csv" `
  --target-split "val" `
  --output-jsonl "output/jsonl/val_teacher.jsonl" `
  --review-csv "output/jsonl/manual_review_val_teacher.csv" `
  --text-only `
  --qa-per-image 1
```

生成测试集：

```powershell
python "model-finetuning/dataset-builder/scripts/build_teacher_jsonl.py" `
  --config "config/config.json" `
  --features-csv "output/features/features.csv" `
  --target-split "test" `
  --output-jsonl "output/jsonl/test_teacher.jsonl" `
  --review-csv "output/jsonl/manual_review_test_teacher.csv" `
  --text-only `
  --qa-per-image 1
```

参数说明：

- `--target-split`：指定生成 `train`、`val`、`test` 或 `all`。
- `--text-only`：教师模型不支持图片时使用，只基于结构化检测结果生成答案。
- `--qa-per-image`：每张图片生成几条问答。
- `--max-samples`：调试时限制样本数量，正式生成设为 `0` 或不传。
- `--sleep`：控制请求间隔，避免触发 API 限流。

## 第 5 步：导出通用训练 JSONL

```powershell
python "model-finetuning/dataset-builder/scripts/export_sft_jsonl.py" `
  --input "output/jsonl/train_teacher.jsonl" `
  --output "output/jsonl/train_sft.jsonl"
```

该步骤用于生成普通 SFT 格式数据，便于后续根据不同训练框架调整。

## 第 6 步：导出 LoRA 多模态数据

训练集：

```powershell
python "model-finetuning/dataset-builder/scripts/export_lora_jsonl.py" `
  --input "model-finetuning/dataset-builder/output/jsonl/train_teacher.jsonl" `
  --output "model-finetuning/data/train_lora.jsonl"
```

验证集：

```powershell
python "model-finetuning/dataset-builder/scripts/export_lora_jsonl.py" `
  --input "model-finetuning/dataset-builder/output/jsonl/val_teacher.jsonl" `
  --output "model-finetuning/data/val_lora.jsonl"
```

输出格式：

```json
{
  "id": "Q_train_1104_maintenance",
  "task": "qa",
  "messages": [
    {"role": "user", "content": "<image>\n请为住建巡检问答任务生成..."},
    {"role": "assistant", "content": "在日常巡检中，应重点检查..."}
  ],
  "images": ["D:/path/to/image.jpg"],
  "question_type": "maintenance",
  "reference_source": "teacher_api:deepseek-v4-pro"
}
```

## 第 7 步：人工复核建议

建议优先抽查以下样本：

- 有加层的建筑。
- 有裂缝、渗水、空鼓、脱落等隐患的建筑。
- 教师模型输出过短或过长的样本。
- 出现真实面积单位的样本。
- 材质、楼层、隐患与结构化结果不一致的样本。

复核后可以直接修改 teacher JSONL 中的 `reference` 字段，再重新执行 LoRA 转换脚本。

## 第 8 步：常见问题

### 为什么教师模型可以不看图片？

如果教师模型不支持图片，它仍然可以基于结构化检测结果生成规范中文文本。图片信息已经由本项目 CV 模型转化成材质、楼层、加层和隐患字段。这样做的重点是训练本地大模型学习专业表达、报告结构和处置建议。

### 为什么不能直接用本地待微调模型生成参考答案？

因为这样会导致训练和评测闭环污染：本地模型既生成标准答案，又参与考试，评测结果会失真。

### 为什么问题看起来有重复？

部分任务会共享同一类问题模板，但 `question_bank.py` 中已经按材质、隐患、加层、管理场景、普通用户场景进行了细分。若要增加工作量体现，可以继续扩展问题库，而不是改动训练框架。

### 如果生成中断怎么办？

教师 API 生成可能耗时较长。建议分 split 生成，并保留已生成的 JSONL。若担心覆盖，输出文件名中加入日期或 split，例如 `train_teacher_20260607.jsonl`。


