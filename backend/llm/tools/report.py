"""Report Agent Tool — 将检测结果和图片发送给本地 Report Agent 生成专业报告。

支持多图: 将选定图片的缺陷标注框画到图上，一起发送给 Report Agent。
"""

import os
import re
from typing import Any

from .base import _last_defects_cache, _select_images
from .schemas import REPORT_SCHEMA


class ReportAgentTool:
    """Report Agent Tool — 委托本地微调 Qwen2.5-VL 模型生成巡检报告。"""

    def __init__(self, report_agent_url: str | None = None):
        self.url = (report_agent_url or os.getenv("REPORT_AGENT_URL", "http://localhost:8000")).rstrip("/")

    @property
    def schema(self):
        return REPORT_SCHEMA

    def execute(self, images=None, image_indices=None, material="", floor="", has_extension="", defects_summary="", **kwargs) -> str:
        if not images:
            return "错误：需要图片才能生成报告。请先确保用户已上传图片。"

        import base64

        global _last_defects_cache

        selected = _select_images(images, image_indices)
        if not selected:
            selected = [(i + 1, img) for i, img in enumerate(images)]

        images_b64 = []
        all_defects = []
        for idx, img in selected:
            defects = _last_defects_cache.get(idx, [])
            if defects:
                rendered = img.copy()
                for d in defects:
                    box = d.get("box", [])
                    if len(box) == 4:
                        pts = __import__("numpy").array(box, dtype=__import__("numpy").int32).reshape((-1, 1, 2))
                        __import__("cv2").polylines(rendered, [pts], isClosed=True, color=(255, 0, 0), thickness=3)
                        label = str(d.get("id", "?"))
                        x, y = pts[0][0]
                        __import__("cv2").putText(rendered, label, (x, y - 8), __import__("cv2").FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
                _, buf = __import__("cv2").imencode(".jpg", rendered)
                images_b64.append(base64.b64encode(buf.tobytes()).decode("utf-8"))
                for d in defects:
                    d_copy = dict(d)
                    d_copy["image_index"] = idx
                    all_defects.append(d_copy)
            else:
                _, buf = __import__("cv2").imencode(".jpg", img)
                images_b64.append(base64.b64encode(buf.tobytes()).decode("utf-8"))

        _last_defects_cache = {}

        payload = {
            "images_base64": images_b64,
            "image_base64": images_b64[0] if images_b64 else "",
            "material": material or "Unknown",
            "floor": floor or "Unknown",
            "has_extension": has_extension or "Unknown",
            "defects": all_defects,
        }

        try:
            resp = __import__("requests").post(
                f"{self.url}/v1/report",
                json=payload,
                timeout=300,
            )
            if resp.status_code == 200:
                data = resp.json()
                elapsed = data.get("elapsed_seconds", 0)
                report_text = data['report']
                # 剥离模型输出的任何 base64 数据（完整或截断均处理）
                report_text = re.sub(r'!\[.*?\]\(data:image[^)]*\)?', '', report_text)
                report_text = re.sub(r'<img[^>]*data:image[^>]*>', '', report_text)
                report_text = re.sub(r'data:image\S+', '', report_text)
                # [图N] 标记 → 对应标注图 <img>
                def _insert_img(m):
                    n = int(m.group(1)) - 1
                    if 0 <= n < len(images_b64):
                        return f'<img src="data:image/jpeg;base64,{images_b64[n]}" style="max-width:400px;border:1px solid #ddd;border-radius:8px;margin:8px 0">'
                    return m.group(0)
                report_text = re.sub(r'\[图(\d+)\]', _insert_img, report_text)
                # 如果模型没放任何 [图N] 标记，在开头展示所有标注图
                if not re.search(r'\[图\d+\]', data['report']):
                    img_tags = "".join(
                        f'<img src="data:image/jpeg;base64,{b64}" style="max-width:400px;border:1px solid #ddd;border-radius:8px;margin:8px 0">'
                        for b64 in images_b64
                    )
                    report_text = f"{img_tags}\n\n{report_text}"
                return f"📋 **专业巡检报告** (生成耗时 {elapsed:.1f}s):\n\n{report_text.strip() or data['report']}"
            return f"Report Agent 调用失败: HTTP {resp.status_code}"
        except Exception as e:
            return f"Report Agent 不可达 ({self.url}): {e}"
