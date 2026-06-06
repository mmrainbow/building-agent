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

        print(f"\n[ReportAgentTool] === generate_report 被调用 ===")
        print(f"  LLM 传入参数: material={material!r}, floor={floor!r}, has_extension={has_extension!r}")
        print(f"  images 数量: {len(images)}, image_indices: {image_indices}")
        print(f"  _last_defects_cache 内容: { {k: f'{len(v)}条' for k, v in _last_defects_cache.items()} }")

        selected = _select_images(images, image_indices)
        if not selected:
            selected = [(i + 1, img) for i, img in enumerate(images)]
        print(f"  实际处理图片: {[idx for idx, _ in selected]}")

        images_b64 = []
        all_defects = []
        for idx, img in selected:
            defects = _last_defects_cache.get(idx, [])
            print(f"  图{idx}: cache defects={len(defects)}条 → ", end="")
            if defects:
                print("画框 + 标注")
                from agent.skills.inspection_skill import get_defect_color

                rendered = img.copy()
                for d in defects:
                    box = d.get("box", [])
                    if len(box) == 4:
                        color = get_defect_color(d.get("type", ""))
                        pts = __import__("numpy").array(box, dtype=__import__("numpy").int32).reshape((-1, 1, 2))
                        __import__("cv2").polylines(rendered, [pts], isClosed=True, color=color, thickness=3)
                        label = str(d.get("id", "?"))
                        x, y = pts[0][0]
                        __import__("cv2").putText(rendered, label, (x, y - 8), __import__("cv2").FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                _, buf = __import__("cv2").imencode(".jpg", rendered)
                images_b64.append(base64.b64encode(buf.tobytes()).decode("utf-8"))
                for d in defects:
                    d_copy = dict(d)
                    d_copy["image_index"] = idx
                    all_defects.append(d_copy)
            else:
                print("无标注，原图编码")
                _, buf = __import__("cv2").imencode(".jpg", img)
                images_b64.append(base64.b64encode(buf.tobytes()).decode("utf-8"))

        print(f"  发送到 Report Agent: {len(images_b64)} 张图片, {len(all_defects)} 条隐患, material={material!r}, floor={floor!r}, has_extension={has_extension!r}")

        _last_defects_cache.clear()

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
                # 剥离模型可能幻觉输出的 base64 / HTML 碎片
                report_text = re.sub(r'!\[.*?\]\(data:image[^)]*\)?', '', report_text)
                report_text = re.sub(r'<img[^>]*data:image[^>]*>', '', report_text)
                report_text = re.sub(r'data:image\S+', '', report_text)
                # 标注图前置 — 横向缩略图条，点击放大
                if images_b64:
                    items = "".join(
                        f'<img src="data:image/jpeg;base64,{b64}"'
                        f' style="height:120px;border-radius:6px;cursor:pointer;flex-shrink:0">'
                        for b64 in images_b64
                    )
                    report_text = (
                        f'<div style="display:flex;gap:6px;overflow-x:auto;margin-bottom:10px;padding-bottom:4px">{items}</div>\n'
                        + report_text
                    )
                print(f"  Report Agent 返回: {len(data['report'])} 字符, 耗时 {elapsed:.1f}s\n")
                return f"📋 **专业巡检报告** (生成耗时 {elapsed:.1f}s):\n\n{report_text.strip() or data['report']}"
            print(f"  Report Agent HTTP {resp.status_code}\n")
            return f"Report Agent 调用失败: HTTP {resp.status_code}"
        except Exception as e:
            print(f"  Report Agent 异常: {e}\n")
            return f"Report Agent 不可达 ({self.url}): {e}"
