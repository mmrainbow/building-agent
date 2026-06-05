import os
from pathlib import Path
from typing import Any

import torch
from PIL import Image


LOCAL_VL_MODEL_ENABLED = os.getenv("LOCAL_VL_MODEL_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
LOCAL_VL_MODEL_PATH = os.getenv(
    "LOCAL_VL_MODEL_PATH",
    str(Path(__file__).parent.parent.parent / "outputs" / "qwen2_5_vl_3b_building_merged"),
)
LOCAL_VL_DEVICE_MAP = os.getenv("LOCAL_VL_DEVICE_MAP", "auto")
LOCAL_VL_TORCH_DTYPE = os.getenv("LOCAL_VL_TORCH_DTYPE", "float16")
LOCAL_VL_MAX_NEW_TOKENS = int(os.getenv("LOCAL_VL_MAX_NEW_TOKENS", "512"))
LOCAL_VL_MAX_PIXELS = int(os.getenv("LOCAL_VL_MAX_PIXELS", "131072"))

_CLIENT: "LocalVLModelClient | None" = None


def is_local_vl_enabled() -> bool:
    return LOCAL_VL_MODEL_ENABLED


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
    for defect in defects:
        defect_id = defect.get("id", "?")
        defect_type = defect.get("type", "未知隐患")
        area = defect.get("area", 0)
        lines.append(f"- 序号{defect_id}：{defect_type}，像素面积约 {float(area):.1f}px")
    return "\n".join(lines)


def build_inspection_prompt(
    material: str,
    floor: str,
    has_extension: str,
    defects: list[dict[str, Any]],
    image_count: int = 1,
) -> str:
    lines = [
        "你是住建外立面巡检报告助手，请结合图像和结构化检测结果生成中文巡检报告。",
        "",
        "结构化检测结果：",
        f"- 材质：{material or 'Unknown'}",
        f"- 楼层：{floor or 'Unknown'}",
        f"- 加层：{has_extension or 'Unknown'}",
        f"- 隐患：",
        _format_defects(defects),
        "",
    ]
    if image_count > 1:
        lines.append(f"本次共 {image_count} 张图片。报告中如需引用图片，请在对应位置写入标记 [图N]（N 为图片编号）。例如'[图1] 显示建筑正面...'。")
    lines.extend([
        "",
        "重要约束：",
        "1. 隐患 area 是图像像素面积 px²，只能用于相对大小参考，禁止换算为平方米或平方厘米。",
        "2. 不要编造检测结果之外的事实。",
        "3. 输出 120 到 350 字中文。",
        "4. 内容包含巡检结论、主要风险、处置建议。",
        "5. 不要输出标题、Markdown 语法、base64 编码或 HTML 标签。",
    ])
    return "\n".join(lines)


class LocalVLModelClient:
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
            dtype=self.torch_dtype,
            trust_remote_code=True,
        ).to("cuda")
        self.model.eval()

    def generate(
        self,
        image_path: str,
        prompt: str,
        max_new_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> str:
        """单图生成 — 兼容旧接口。"""
        return self.generate_multi(
            image_paths=[image_path],
            prompt=prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )

    def generate_multi(
        self,
        image_paths: list[str],
        prompt: str,
        max_new_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> str:
        """多图生成 — 所有图片一起传给 VL 模型。"""
        self.load()
        images = []
        for p in image_paths:
            img = Image.open(p)
            img.load()  # 强制读完，Windows 需要释放文件句柄
            images.append(img.convert("RGB"))
        content = []
        for img in images:
            content.append({"type": "image", "image": img})
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]
        text = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.processor(
            text=[text],
            images=images,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self.model.device)
        do_sample = temperature > 0
        generate_kwargs = {
            "max_new_tokens": max_new_tokens or LOCAL_VL_MAX_NEW_TOKENS,
            "do_sample": do_sample,
        }
        if do_sample:
            generate_kwargs["temperature"] = temperature
        generated_ids = self.model.generate(**inputs, **generate_kwargs)
        generated_ids = [
            output_ids[len(input_ids) :]
            for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
        ]
        return self.processor.batch_decode(
            generated_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()

    def chat(
        self,
        messages: list[dict],
        max_new_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> str:
        """纯文本对话 — 不走图像，直接 tokenize 消息列表生成回复。

        Args:
            messages: OpenAI 格式消息列表 [{"role":"system","content":"..."}, ...]
            max_new_tokens: 最大生成 token 数
            temperature: 采样温度

        Returns:
            生成的文本回复
        """
        self.load()
        # 用 processor 的 chat_template 格式化消息
        text = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.processor(
            text=[text],
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(self.model.device)
        do_sample = temperature > 0
        generate_kwargs = {
            "max_new_tokens": max_new_tokens or LOCAL_VL_MAX_NEW_TOKENS,
            "do_sample": do_sample,
        }
        if do_sample:
            generate_kwargs["temperature"] = temperature
        generated_ids = self.model.generate(**inputs, **generate_kwargs)
        generated_ids = [
            output_ids[len(input_ids):]
            for input_ids, output_ids in zip(inputs.input_ids, generated_ids)
        ]
        return self.processor.batch_decode(
            generated_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()

    def _build_multi_image_prompt(
        self,
        image_count: int,
        material: str,
        floor: str,
        has_extension: str,
        defects: list[dict[str, Any]],
    ) -> str:
        """多图巡检 prompt — 告知模型共有 N 张图，每张图的缺陷已标注来源编号。"""
        defect_lines = []
        for d in defects:
            img_idx = d.get("image_index", "?")
            defect_lines.append(
                f"- 图{img_idx}: {d.get('type', '未知')} (面积: {float(d.get('area', 0)):.0f}px²)"
            )
        defect_text = "\n".join(defect_lines) if defect_lines else "无明显隐患"

        return (
            f"你是住建外立面巡检报告助手。现有一栋建筑共 {image_count} 张不同角度照片。\n"
            f"请结合图像和以下所有图片的结构化检测结果生成中文巡检报告。\n"
            f"报告中引用图片时请使用标记 [图N]（N 为图片编号），如'[图1] 显示建筑正面...'。\n\n"
            f"结构化检测结果（共 {image_count} 张图片汇总）：\n"
            f"- 材质：{material or 'Unknown'}\n"
            f"- 楼层：{floor or 'Unknown'}\n"
            f"- 加层：{has_extension or 'Unknown'}\n"
            f"- 隐患明细（按图片编号）：\n{defect_text}\n\n"
            f"重要约束：\n"
            f"1. 隐患 area 是图像像素面积 px²，只能用于相对大小参考，禁止换算为平方米或平方厘米。\n"
            f"2. 不要编造检测结果之外的事实。\n"
            f"3. 输出 200 到 350 字中文。\n"
            f"4. 内容包含：检测概况 → 逐图分析 → 综合评定 → 处理建议。\n"
            f"5. 每个隐患描述必须标注来源图片编号。\n"
            f"6. 不要输出标题、Markdown 标记、base64 编码或 HTML 标签。"
        )

    def generate_report(
        self,
        image_path: str,
        material: str,
        floor: str,
        has_extension: str,
        defects: list[dict[str, Any]],
        image_count: int = 1,
    ) -> str:
        prompt = build_inspection_prompt(material, floor, has_extension, defects, image_count)
        return self.generate(image_path=image_path, prompt=prompt)


def generate_local_inspection_report(
    image_path: str,
    material: str,
    floor: str,
    has_extension: str,
    defects: list[dict[str, Any]],
) -> str:
    return get_local_vl_client().generate_report(
        image_path=image_path,
        material=material,
        floor=floor,
        has_extension=has_extension,
        defects=defects,
    )


def chat_local(messages: list[dict], max_new_tokens: int | None = None, temperature: float = 0.7) -> str:
    """纯文本对话 — 模块级快捷函数。"""
    return get_local_vl_client().chat(messages, max_new_tokens=max_new_tokens, temperature=temperature)
