"""CV Tool 包装器 — 将 BasePredictor 子类封装为 OpenAI Tool。

延迟加载 — 首次调用 execute() 时才加载模型权重。
多图支持 — 根据 image_indices 选择分析目标图片。
"""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from utils.materials import material_to_zh

from .schemas import DEFECT_SCHEMA, MATERIAL_SCHEMA, FLOOR_SCHEMA, EXTENSION_SCHEMA

MODEL_DIR = Path(__file__).parent.parent.parent / "model_weights"

# 缓存最近一次 defect 检测的原始结果 (dict: image_index → defects)，供 generate_report 画框用
_last_defects_cache: dict[int, list[dict]] = {}


def _select_images(images: list, image_indices: list[int] | None) -> list[tuple[int, Any]]:
    """根据 image_indices 筛选图片，返回 [(1-based index, image), ...]。

    image_indices 为 None 时返回全部图片。
    """
    if not images:
        return []
    if image_indices:
        result = []
        for i in image_indices:
            if 1 <= i <= len(images):
                result.append((i, images[i - 1]))
        return result
    return [(i + 1, img) for i, img in enumerate(images)]


class CVToolWrapper:
    """将 BasePredictor 子类包装为 OpenAI Tool。

    延迟加载 — 首次调用 execute() 时才加载模型权重。
    支持多图: 根据 image_indices 选择分析目标图片。
    """

    def __init__(self, schema: dict, predictor_factory: Callable):
        self.schema = schema
        self._predictor = None
        self._factory = predictor_factory

    def _ensure_loaded(self):
        if self._predictor is None:
            self._predictor = self._factory()

    def execute(self, images=None, image_indices=None, **kwargs) -> str:
        """执行推理，返回中文可读文本结果。"""
        if not images:
            return "错误：需要图片输入，但当前未提供图片。"
        self._ensure_loaded()
        selected = _select_images(images, image_indices)
        if not selected:
            return "错误：指定的图片编号无效。"
        results = []
        for idx, img in selected:
            try:
                result = self._predictor.predict([img])
                value = result[0] if result else None
                label = f"[图{idx}]" if len(images) > 1 else ""
                out = self._format_output(value)
                results.append(f"{label} {out}".strip())
            except Exception as e:
                results.append(f"[图{idx}] 推理失败: {e}")
        return "\n".join(results)

    def _format_output(self, value):
        """子类可覆盖以定制输出格式。"""
        if value is None:
            return "未识别出结果。"
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=False)
        return str(value)


class DefectToolWrapper(CVToolWrapper):
    """隐患检测专用 — 输出中文类型名和面积，同步入库到 Defect 表。"""

    def execute(self, images=None, image_indices=None, db=None, chat_image_ids=None, **kwargs) -> str:
        _last_defects_cache.clear()
        if not images:
            return "错误：需要图片输入，但当前未提供图片。"
        self._ensure_loaded()
        selected = _select_images(images, image_indices)
        if not selected:
            return "错误：指定的图片编号无效。"

        all_results = []
        for idx, img in selected:
            try:
                raw = self._predictor.predict([img])
                defects = raw[0] if raw else []
                if not isinstance(defects, list):
                    defects = []
                _last_defects_cache[idx] = defects
            except Exception:
                defects = []
                _last_defects_cache[idx] = []

            # 入库: 关联对应图片的 chat_image_id
            cid = None
            if chat_image_ids and 1 <= idx <= len(chat_image_ids):
                cid = chat_image_ids[idx - 1]
            if db and cid and defects:
                try:
                    from db.models import Defect
                    for d in defects:
                        db.add(Defect(
                            chat_image_id=cid,
                            defect_type=str(d.get("type", "")),
                            area=float(d.get("area", 0) or 0),
                            box_coords=d.get("box", []),
                        ))
                    db.commit()
                except Exception as e:
                    print(f"[DefectTool] 入库失败: {e}")

            label = f"[图{idx}]" if len(images) > 1 else ""
            all_results.append(f"{label} {self._format_output(defects)}".strip())

        return "\n".join(all_results)

    def _format_output(self, value):
        if not value:
            return "未检测到明显隐患。"
        items = []
        for d in value:
            items.append(
                f"隐患#{d.get('id', '?')}: {d.get('type', '未知')} "
                f"(面积: {d.get('area', 0):.0f}px²)"
            )
        return f"检测到 {len(items)} 处隐患:\n" + "\n".join(items) if items else "未检测到明显隐患。"


class MaterialToolWrapper(CVToolWrapper):
    """材质识别专用 — 将模型英文标签转换为中文名称。"""

    def _format_output(self, value):
        return material_to_zh(str(value or ""))


# ── Predictor 工厂函数（延迟 import torch/ultralytics）────────


def _make_material_predictor(model_dir: str):
    from predictors.material import MaterialPredictor
    return MaterialPredictor(os.path.join(model_dir, "material.pth"))


def _make_floor_predictor(model_dir: str):
    from predictors.floor import FloorPredictor
    return FloorPredictor(
        os.path.join(model_dir, "main_building.pt"),
        os.path.join(model_dir, "outer_obj.pt"),
    )


def _make_extension_predictor(model_dir: str):
    from predictors.added_floor import AddedFloorPredictor
    return AddedFloorPredictor(os.path.join(model_dir, "add_predict.pth"))


def _make_defect_predictor(model_dir: str):
    from predictors.hidden_danger import HiddenDangerPredictor
    return HiddenDangerPredictor(os.path.join(model_dir, "best.pt"))
