"""建筑巡检 Skill — 同一建筑至少 3 张图，收集完毕后自动巡检 + 报告 + 入库。

交互流程:
    Turn 1: 用户上传图1 + "巡检" → 创建 InspectionRecord(status=collecting)
    Turn 2: 用户上传图2         → 追加 ImageInspection
    Turn 3: 用户上传图3         → 达到最小张数 → 全部 CV 检测 → 生成报告 → 入库
    Turn N: 用户可继续追加更多图片，每次追加都重新汇总报告
"""

import os
from pathlib import Path

import cv2
import numpy as np

MODEL_DIR = Path(__file__).parent.parent.parent / "model_weights"
MIN_IMAGES = 3


def draw_defects(image: np.ndarray, defects: list[dict]) -> np.ndarray:
    """在图片上绘制缺陷框和编号标签。返回标注后的图片 (RGB)。"""
    rendered = image.copy()
    for d in defects:
        box = d.get("box", [])
        if len(box) != 4:
            continue
        pts = np.array(box, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(rendered, [pts], isClosed=True, color=(255, 0, 0), thickness=3)
        label = str(d.get("id", "?"))
        x, y = pts[0][0]
        cv2.putText(rendered, label, (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
    return rendered


def _save_annotated_images(record_id: int, annotated_b64_list: list[str]) -> list[str]:
    """将标注图片 base64 列表保存为文件，返回文件路径列表。"""
    paths = []
    chat_dir = Path(__file__).parent.parent.parent / "chat_images"
    chat_dir.mkdir(parents=True, exist_ok=True)
    for i, b64 in enumerate(annotated_b64_list):
        fpath = str(chat_dir / f"inspection_{record_id}_img{i + 1}_annotated.jpg")
        with open(fpath, "wb") as f:
            f.write(__import__("base64").b64decode(b64))
        paths.append(fpath)
    return paths

INSPECT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "inspect_building",
        "description": (
            "建筑巡检 — 上传建筑图片进行检测。同一建筑需至少 3 张不同角度照片。"
            "每次上传一张图片调用一次此工具。收集够图片后自动生成图文巡检报告并入库。"
            "用户说'巡检''检测''看看这栋楼'时调用。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


class InspectionSkill:
    """多图巡检 Skill — 收集 → 检测 → 报告 → 入库。"""

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
            return self._status_message(user_id)
        if not user_id:
            return "错误：无法识别用户身份。"

        self._ensure_predictors()
        db = self._get_db()

        try:
            record = self._get_or_create_record(db, int(user_id))
            seq = self._add_image(db, record, image)

            total = len(record.images or [])
            if total < MIN_IMAGES:
                return (
                    f"📸 已接收第 {seq} 张图片（共 {total} 张）。\n"
                    f"还需至少 {MIN_IMAGES - total} 张。请继续上传同一建筑的其他角度照片。\n"
                    f"（当前巡检 ID: {record.id}）"
                )

            # 达到最小张数 → 全量巡检
            self._run_inspection_on_all(db, record)
            report = record.report or "报告生成失败。"

            return (
                f"=== 巡检完成 (ID: {record.id}) ===\n\n"
                f"共检测 {total} 张图片。\n\n{report}"
            )

        finally:
            db.close()

    # ── DB 操作 ──────────────────────────────────────────

    def _get_db(self):
        from db import SessionLocal

        return SessionLocal()

    def _get_or_create_record(self, db, user_id: int):
        from db.models import InspectionRecord

        record = (
            db.query(InspectionRecord)
            .filter(
                InspectionRecord.user_id == user_id,
                InspectionRecord.status == "collecting",
            )
            .order_by(InspectionRecord.created_at.desc())
            .first()
        )
        if record is None:
            record = InspectionRecord(user_id=user_id, status="collecting")
            db.add(record)
            db.flush()
        return record

    def _add_image(self, db, record, image) -> int:
        """保存图片到 image_inspection + 编码为 chat_images BLOB。"""
        from db.models import ImageInspection, ChatImage, ChatMessage

        # 编码 JPEG
        _, buf = cv2.imencode(".jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        jpeg_bytes = buf.tobytes()

        # 创建或复用巡检专用 Conversation（__inspection__ 前缀会被聊天列表过滤）
        from db.models import Conversation
        conv = db.query(Conversation).filter(
            Conversation.user_id == record.user_id,
            Conversation.title == "__inspection__",
        ).first()
        if conv is None:
            conv = Conversation(user_id=record.user_id, title="图像巡检")
            db.add(conv)
            db.flush()

        msg = ChatMessage(conversation_id=conv.id, role="user", content=f"[巡检图片 {len(record.images or []) + 1}]")
        db.add(msg)
        db.flush()

        chat_img = ChatImage(message_id=msg.id, data=jpeg_bytes)
        db.add(chat_img)
        db.flush()

        # 创建 ImageInspection
        img_entry = ImageInspection(
            record_id=record.id,
            image_name=f"巡检图_{len(record.images or []) + 1}",
            chat_image_id=chat_img.id,
        )
        db.add(img_entry)
        db.commit()
        db.refresh(record)
        return len(record.images or [])

    # ── CV 检测 ──────────────────────────────────────────

    def _run_inspection_on_all(self, db, record) -> None:
        """对所有图片逐张 CV 检测，汇总生成报告。"""
        img_entries = record.images or []
        all_results = []

        for img_entry in img_entries:
            if img_entry.chat_image and img_entry.chat_image.data:
                nparr = np.frombuffer(img_entry.chat_image.data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    result = self._inspect_single(img)
                    # 回写检测结果
                    img_entry.material = result["material"]
                    img_entry.floor = result["floor"]
                    img_entry.has_extension = result["has_extension"]
                    for d in result["defects"]:
                        from db.models import Defect
                        defect = Defect(
                            chat_image_id=img_entry.chat_image_id,
                            defect_type=str(d.get("type", "")),
                            area=float(d.get("area", 0) or 0),
                            box_coords=d.get("box", []),
                        )
                        db.add(defect)
                    all_results.append(result)

        # 生成汇总报告（优先 Report Agent，回退远程 API）
        report, annotated_b64 = self._generate_report(all_results, img_entries)
        record.report = report
        # 保存标注图片到 chat_images/ 目录供前端展示
        _annotated_paths = _save_annotated_images(record.id, annotated_b64)
        record.status = "done"
        db.commit()
        db.refresh(record)
        # 把标注图片路径附加到 record 上（不存 DB，仅运行时传递）
        record._annotated_paths = _annotated_paths

    def _inspect_single(self, image) -> dict:
        return {
            "material": self._predict("material", image),
            "floor": self._predict("floor", image),
            "has_extension": self._predict("extension", image),
            "defects": self._predict("defect", image) or [],
        }

    def _predict(self, name: str, image):
        try:
            result = self._predictors[name].predict([image])
            return result[0] if result else ("无" if name != "defect" else [])
        except Exception as e:
            return f"检测失败: {e}"

    # ── 报告生成 ──────────────────────────────────────────

    def _generate_report(self, all_results: list[dict], img_entries: list) -> tuple[str, list[str]]:
        """汇总检测结果，优先 Report Agent（本地模型），失败回退远程 API。
        返回 (report_text, annotated_images_base64_list)。"""
        import base64
        import requests as req

        # 汇总材质/楼层/加层
        materials = [r["material"] for r in all_results]
        floors = [r["floor"] for r in all_results]
        extensions = [r["has_extension"] for r in all_results]
        all_defects = []
        annotated_b64_list = []

        for i, r in enumerate(all_results):
            for d in (r.get("defects") or []):
                d["image_index"] = i + 1
                all_defects.append(d)
            # 生成标注图片：在原始图上画缺陷框
            annotated = draw_defects(
                cv2.cvtColor(
                    cv2.imdecode(
                        np.frombuffer(img_entries[i].chat_image.data, np.uint8),
                        cv2.IMREAD_COLOR,
                    ),
                    cv2.COLOR_BGR2RGB,
                ),
                r.get("defects") or [],
            )
            _, buf = cv2.imencode(".jpg", cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR))
            annotated_b64_list.append(base64.b64encode(buf.tobytes()).decode("utf-8"))

        # ── 优先: Report Agent (本地模型) — 发送标注图片让模型看到缺陷框 ──
        report_url = os.getenv("REPORT_AGENT_URL", "http://localhost:8000")
        try:
            resp = req.post(
                f"{report_url}/v1/report",
                json={
                    "images_base64": annotated_b64_list,
                    "material": ", ".join(set(m for m in materials if m and m != "Unknown")) or "Unknown",
                    "floor": ", ".join(set(f for f in floors if f and f != "Unknown")) or "Unknown",
                    "has_extension": ", ".join(set(e for e in extensions if e and e != "Unknown")) or "Unknown",
                    "defects": all_defects,
                },
                timeout=180,
            )
            if resp.status_code == 200:
                data = resp.json()
                elapsed = data.get("elapsed_seconds", 0)
                print(f"[InspectionSkill] Report Agent 生成成功 ({elapsed:.1f}s)")
                # 标注图嵌入报告 — 图文并茂
                img_tags = "".join(
                    f'<img src="data:image/jpeg;base64,{b64}" style="max-width:400px;border:1px solid #ddd;border-radius:8px;margin:8px 0">'
                    for b64 in annotated_b64_list
                )
                report = f"{img_tags}\n\n{data['report']}"
                return report, annotated_b64_list
        except Exception as e:
            print(f"[InspectionSkill] Report Agent 不可用: {e}")

        # ── 回退: 远程 API ──
        prompt = self._build_prompt(materials, floors, extensions, all_defects)
        try:
            resp = req.post(
                f"{os.getenv('LLM_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.getenv('LLM_API_KEY', os.getenv('EMBEDDING_API_KEY', ''))}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.getenv("LLM_MODEL", "qwen-plus"),
                    "messages": [
                        {"role": "system", "content": "你是建筑结构检测工程师。根据多张建筑图片的检测数据，生成专业的中文巡检报告。引用具体图片编号佐证每个发现。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                print("[InspectionSkill] 回退远程 API 生成成功")
                return resp.json()["choices"][0]["message"]["content"].strip(), annotated_b64_list
            return f"[LLM HTTP {resp.status_code}]", annotated_b64_list
        except Exception as e:
            return f"[LLM Error: {e}]", annotated_b64_list

    def _build_prompt(self, materials, floors, extensions, defects) -> str:
        defect_lines = []
        for d in defects:
            defect_lines.append(
                f"- 图{d.get('image_index', '?')}: {d.get('type', '未知')} "
                f"(面积: {d.get('area', 0):.0f}px²)"
            )
        defect_text = "\n".join(defect_lines) if defect_lines else "无明显隐患"

        return (
            f"共检测 {len(materials)} 张图片，请生成 300-400 字的中文巡检报告。\n\n"
            f"材质: {', '.join(materials)}\n"
            f"楼层: {', '.join(floors)}\n"
            f"加层: {', '.join(extensions)}\n"
            f"隐患汇总 (按图片编号):\n{defect_text}\n\n"
            "格式: [检测概况(图片数+建筑概况)] → [逐图分析(引用图片编号)] → [综合评定] → [处理建议]\n"
            "重要: 每个隐患描述必须标注来源图片编号。"
        )

    def _status_message(self, user_id=None) -> str:
        """无图片时返回当前收集状态。"""
        if not user_id:
            return "inspect_building: 需要上传建筑图片。"
        db = self._get_db()
        try:
            from db.models import InspectionRecord

            record = (
                db.query(InspectionRecord)
                .filter(
                    InspectionRecord.user_id == int(user_id),
                    InspectionRecord.status == "collecting",
                )
                .first()
            )
            if record is None:
                return "当前没有进行中的巡检。上传建筑图片并说'巡检'开始。"
            total = len(record.images or [])
            return (
                f"当前巡检 (ID: {record.id}) 已收集 {total} 张图片，"
                f"至少需要 {MIN_IMAGES} 张。请继续上传。"
            )
        finally:
            db.close()
