"""本地 VL 模型客户端 — Qwen2.5-VL 加载与推理。

用法:
    from llm.local_vl_model import get_local_vl_client, build_inspection_prompt
    client = get_local_vl_client()
    report = client.generate_multi(image_paths=["/tmp/img.jpg"], prompt="...")
    text  = client.chat(messages=[{"role":"user","content":"你好"}])
"""

import os
from pathlib import Path
from typing import Any

import torch
from PIL import Image

LOCAL_VL_MODEL_PATH = os.getenv(
    "LOCAL_VL_MODEL_PATH",
    str(Path(__file__).resolve().parent.parent / "qwen2_5_vl_3b_building_merged"),
)
LOCAL_VL_DEVICE_MAP = os.getenv("LOCAL_VL_DEVICE_MAP", "auto")
LOCAL_VL_TORCH_DTYPE = os.getenv("LOCAL_VL_TORCH_DTYPE", "float16")
LOCAL_VL_MAX_NEW_TOKENS = int(os.getenv("LOCAL_VL_MAX_NEW_TOKENS", "512"))
LOCAL_VL_MAX_PIXELS = int(os.getenv("LOCAL_VL_MAX_PIXELS", "131072"))

_CLIENT: "LocalVLModelClient | None" = None


def get_local_vl_client() -> "LocalVLModelClient":
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = LocalVLModelClient()
    return _CLIENT


def _resolve_dtype(dtype_name: str):
    if dtype_name == "auto":
        return "auto"
    dtype = getattr(torch, dtype_name, None)
    if dtype is None:
        raise ValueError(f"不支持的 torch dtype: {dtype_name}")
    return dtype


def _format_defects(defects: list[dict[str, Any]]) -> str:
    if not defects:
        return "无明显隐患"
    lines = []
    for d in defects:
        img_idx = d.get("image_index", "?")
        defect_type = d.get("type", "未知隐患")
        area = d.get("area", 0)
        lines.append(f"- 图{img_idx}: {defect_type}，像素面积约 {float(area):.1f}px")
    return "\n".join(lines)


def build_inspection_prompt(
    material: str,
    floor: str,
    has_extension: str,
    defects: list[dict[str, Any]],
    image_count: int = 1,
) -> str:
    """构建巡检报告生成 prompt — 将结构化检测数据 + 约束规则拼接为模型输入。"""
    mat = material or "Unknown"
    flr = floor or "Unknown"
    ext = has_extension or "Unknown"

    return (
        f"你是住建外立面巡检报告助手。现有一栋建筑共 {image_count} 张不同角度照片。\n"
        f"请结合图像和以下所有图片的结构化检测结果生成中文巡检报告。\n"
        f"报告中引用图片时请使用标记 [图N]（N 为图片编号），如'[图1] 显示建筑正面...'。\n\n"
        f"结构化检测结果（共 {image_count} 张图片汇总）：\n"
        f"- 材质：{mat}\n"
        f"- 楼层：{flr}\n"
        f"- 加层：{ext}\n"
        f"- 隐患明细（按图片编号）：\n{_format_defects(defects)}\n\n"
        f"重要约束：\n"
        f"1. 隐患 area 是图像像素面积 px²，只能用于相对大小参考，禁止换算为平方米或平方厘米。\n"
        f"2. 不要编造检测结果之外的事实。\n"
        f"3. 输出 200 到 350 字中文。\n"
        f"4. 内容包含：检测概况 → 逐图分析 → 综合评定 → 处理建议。\n"
        f"5. 每个隐患描述必须标注来源图片编号。\n"
        f"6. 不要输出标题、Markdown 标记、base64 编码或 HTML 标签。"
    )


class LocalVLModelClient:
    """本地 Qwen2.5-VL 模型客户端 — 加载 / 多图生成 / 纯文本对话。"""

    def __init__(
        self,
        model_path: str | None = None,
        device_map: str | None = None,
        torch_dtype: str | None = None,
        max_pixels: int | None = None,
    ):
        self.model_path = str(Path(model_path or LOCAL_VL_MODEL_PATH))
        self.device_map = device_map or LOCAL_VL_DEVICE_MAP
        self.torch_dtype = _resolve_dtype(torch_dtype or LOCAL_VL_TORCH_DTYPE)
        self.max_pixels = max_pixels or LOCAL_VL_MAX_PIXELS
        self.model = None
        self.processor = None

    def load(self) -> None:
        if self.model is not None and self.processor is not None:
            return
        if not Path(self.model_path).exists():
            raise FileNotFoundError(f"本地多模态模型目录不存在: {self.model_path}")

        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        self.processor = AutoProcessor.from_pretrained(
            self.model_path,
            max_pixels=self.max_pixels,
            trust_remote_code=True,
        )
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.model_path,
            torch_dtype=self.torch_dtype if self.torch_dtype != "auto" else torch.float16,
            device_map=self.device_map,
            trust_remote_code=True,
        )
        self.model.eval()

    def generate_multi(
        self,
        image_paths: list[str],
        prompt: str,
        max_new_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> str:
        """多图生成 — 图片 + prompt → VL 模型 → 文本。"""
        self.load()
        images = [Image.open(p).convert("RGB") for p in image_paths]
        for img in images:
            img.load()  # Windows: 强制读完以释放文件句柄

        content = [{"type": "image", "image": img} for img in images]
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]

        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )
        inputs = self.processor(
            text=[text], images=images, padding=True, return_tensors="pt",
        ).to(self.model.device)

        generate_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens or LOCAL_VL_MAX_NEW_TOKENS,
            "do_sample": temperature > 0,
        }
        if temperature > 0:
            generate_kwargs["temperature"] = temperature

        generated_ids = self.model.generate(**inputs, **generate_kwargs)
        generated_ids = [
            output_ids[len(input_ids):]
            for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
        ]
        return self.processor.batch_decode(
            generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False,
        )[0].strip()

    def chat(
        self,
        messages: list[dict],
        max_new_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> str:
        """纯文本对话 — 不走图像，直接 tokenize 消息列表。"""
        self.load()
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )
        inputs = self.processor(
            text=[text], padding=True, return_tensors="pt",
        ).to(self.model.device)

        generate_kwargs: dict[str, Any] = {
            "max_new_tokens": max_new_tokens or LOCAL_VL_MAX_NEW_TOKENS,
            "do_sample": temperature > 0,
        }
        if temperature > 0:
            generate_kwargs["temperature"] = temperature

        generated_ids = self.model.generate(**inputs, **generate_kwargs)
        generated_ids = [
            output_ids[len(input_ids):]
            for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
        ]
        return self.processor.batch_decode(
            generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False,
        )[0].strip()
