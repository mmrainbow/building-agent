"""建筑巡检 Skill — 一次调用完成全套检测 + 报告生成 + 数据入库。

作为 Tool 注册给 LLM，替代逐个调用 classify_material / estimate_floors /
detect_extension / detect_defects。LLM 说一句"全面巡检"就自动走完整流程。
"""

import os
from datetime import datetime, timezone
from pathlib import Path

MODEL_DIR = Path(__file__).parent.parent.parent / "models"

INSPECT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "inspect_building",
        "description": (
            "建筑全面巡检：一次调用自动完成材质识别、楼层估算、加层检测、隐患检测，"
            "生成标准中文巡检报告并保存到数据库。用户说'全面检测'或'巡检'时直接调用此工具，"
            "无需单独调用 classify_material/estimate_floors/detect_defects 等工具。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


class InspectionSkill:
    """全面建筑巡检 — 内部调度 4 个 CV Predictor + LLM 报告生成 + 落库。"""

    def __init__(self):
        self._predictors = None

    @property
    def schema(self):
        return INSPECT_SCHEMA

    def _ensure_predictors(self):
        if self._predictors is not None:
            return
        from predictors.added_floor import AddedFloorPredictor
        from predictors.floor import FloorPredictor
        from predictors.hidden_danger import HiddenDangerPredictor
        from predictors.material import MaterialPredictor

        self._predictors = {
            "material": MaterialPredictor(str(MODEL_DIR / "material.pth")),
            "floor": FloorPredictor(
                str(MODEL_DIR / "main_building.pt"),
                str(MODEL_DIR / "outer_obj.pt"),
            ),
            "extension": AddedFloorPredictor(str(MODEL_DIR / "add_predict.pth")),
            "defect": HiddenDangerPredictor(str(MODEL_DIR / "best.pt")),
        }

    def execute(self, image=None, user_id=None, **kwargs) -> str:
        if image is None:
            return "错误：需要建筑图片才能执行巡检。"

        self._ensure_predictors()

        # 1. 并行跑 4 个 CV Predictor
        material = self._predict("material", image)
        floor = self._predict("floor", image)
        extension = self._predict("extension", image)
        defects = self._predict("defect", image)

        # 2. 调用 LLM 生成巡检报告
        report = self._generate_report(material, floor, extension, defects)

        # 3. 入库
        record_id = self._save_to_db(user_id, material, floor, extension, report, defects)

        return (
            f"=== 巡检完成 (record_id={record_id}) ===\n\n"
            f"## 检测结果\n"
            f"- 材质: {material}\n"
            f"- 楼层: {floor}\n"
            f"- 加层: {extension}\n"
            f"- 隐患数: {len(defects) if isinstance(defects, list) else 0}\n\n"
            f"## 巡检报告\n{report}"
        )

    def _predict(self, name: str, image) -> str | list:
        try:
            result = self._predictors[name].predict([image])
            return result[0] if result else ("无" if name != "defect" else [])
        except Exception as e:
            return f"检测失败: {e}"

    def _generate_report(self, material, floor, extension, defects) -> str:
        prompt = self._build_report_prompt(material, floor, extension, defects)
        try:
            import requests

            resp = requests.post(
                f"{os.getenv('LLM_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('DASHSCOPE_API_KEY', '')}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.getenv("LLM_MODEL", "qwen-plus"),
                    "messages": [
                        {"role": "system", "content": "你是建筑结构检测工程师，根据检测数据生成专业的中文巡检报告。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
            return f"[LLM HTTP {resp.status_code}]"
        except Exception as e:
            return f"[LLM Error: {e}]"

    def _build_report_prompt(self, material, floor, extension, defects) -> str:
        defects_desc = "无明显隐患"
        if defects and isinstance(defects, list) and len(defects) > 0:
            items = []
            for d in defects:
                t = d.get("type", "未知")
                a = d.get("area", 0)
                items.append(f"- {t} (面积: {a:.0f}px²)")
            defects_desc = "\n".join(items)

        return (
            "请根据以下检测数据生成一份 200-300 字的中文巡检报告：\n\n"
            f"材质: {material}\n"
            f"楼层: {floor}\n"
            f"加层: {extension}\n"
            f"隐患:\n{defects_desc}\n\n"
            "格式要求: [检测概况] → [缺陷分析] → [综合评定] → [处理建议]"
        )

    def _save_to_db(self, user_id, material, floor, extension, report, defects) -> int | None:
        if not user_id:
            return None
        try:
            from db import SessionLocal, save_inspection

            db = SessionLocal()
            try:
                record = save_inspection(
                    db=db,
                    user_id=int(user_id),
                    image_name=f"inspection_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                    material=str(material),
                    floor=str(floor),
                    has_extension=str(extension),
                    report=report,
                    defects=defects if isinstance(defects, list) else [],
                )
                return record.id
            finally:
                db.close()
        except Exception as e:
            return f"入库失败: {e}"
