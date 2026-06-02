import os
from pathlib import Path

import cv2
import requests
from dotenv import load_dotenv

from llm.local_vl_model import generate_local_inspection_report, is_local_vl_enabled
from predictors.added_floor import AddedFloorPredictor
from predictors.floor import FloorPredictor
from predictors.hidden_danger import HiddenDangerPredictor
from predictors.material import MaterialPredictor

from .state import InspectionState
from .rag import load_vectorstore, retrieve_regulations

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("EMBEDDING_API_KEY", ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen-turbo")
MODEL_DIR = Path(__file__).parent.parent / "model_weights"

_floor = FloorPredictor(MODEL_DIR / "main_building.pt", MODEL_DIR / "outer_obj.pt")
_added = AddedFloorPredictor(MODEL_DIR / "add_predict.pth")
_material = MaterialPredictor(MODEL_DIR / "material.pth")
_hidden = HiddenDangerPredictor(MODEL_DIR / "best.pt")


def load_image(image_path: str):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Failed to read image: {image_path}")
    return image


def load_image_node(state: InspectionState):
    try:
        image = load_image(state["image_path"])
        return {"image": image}
    except Exception as e:
        return {"error": f"Image loading failed: {e}"}


def material_node(state: InspectionState):
    try:
        result = _material.predict([state["image"]])
        return {"material": result[0] if result else "Unknown"}
    except Exception as e:
        return {"error": f"Material detection failed: {e}"}


def floor_node(state: InspectionState):
    try:
        result = _floor.predict([state["image"]])
        return {"floor": result[0] if result else "Unknown"}
    except Exception as e:
        return {"error": f"Floor estimation failed: {e}"}


def extension_node(state: InspectionState):
    try:
        result = _added.predict([state["image"]])
        return {"has_extension": result[0] if result else "Unknown"}
    except Exception as e:
        return {"error": f"Extension detection failed: {e}"}


def defect_node(state: InspectionState):
    try:
        result = _hidden.predict([state["image"]])
        return {"defects": result[0] if result else []}
    except Exception as e:
        return {"error": f"Defect detection failed: {e}"}


def rag_node(state: InspectionState):
    try:
        vs = load_vectorstore()
        regs = retrieve_regulations(
            vs,
            material=state.get("material", "未知"),
            defects=state.get("defects", []) or [],
            floor=state.get("floor", "未知"),
            has_extension=state.get("has_extension", "未知"),
        )
        return {"regulations": regs}
    except Exception as e:
        # 终极兜底：完全失败时返回空字符串
        print(f"[RAG Node] 检索失败：{e}")
        return {"regulations": ""}


def report_node(state: InspectionState):
    defects = state.get("defects", []) or []
    local_vl_error = None
    if is_local_vl_enabled():
        try:
            report = generate_local_inspection_report(
                image_path=state["image_path"],
                material=state.get("material", "Unknown"),
                floor=state.get("floor", "Unknown"),
                has_extension=state.get("has_extension", "Unknown"),
                defects=defects,
            )
            if report:
                return {"report": report, "report_no_rag": report}
        except Exception as e:
            local_vl_error = e

    if defects:
        defects_desc = "\n".join(
            [f"- Box {d.get('id', '?')}: {d.get('type', 'unknown')} ({d.get('area', 0):.1f}px)" for d in defects]
        )
    else:
        defects_desc = "- No obvious defects found"

    material = state.get('material', 'Unknown')
    floor = state.get('floor', 'Unknown')
    extension = state.get('has_extension', 'Unknown')
    regulations = state.get('regulations', '')

    # 有 RAG 规范的 prompt
    prompt_with_rag = f"""Generate a professional building inspection report in Chinese. Follow the format strictly.

Detection result:
- Material: {material}
- Estimated floors: {floor}
- Extension: {extension}
- Defects:
{defects_desc}

Reference regulations:
{regulations if regulations else '暂无可用规范引用。'}

Report format requirements:
1. [检测概况] 简述建筑基本信息（材料、层数、加层情况）。
2. [缺陷分析] 逐个分析每个缺陷的严重程度，引用相关规范条文（标注规范编号）。
3. [综合评定] 根据规范给出结构安全等级评定（A/B/C/D级）及依据。
4. [处理建议] 给出具体可操作的处理建议。

Style:
- 保持客观专业，语言简洁。
- 约 200-300 字。
- 必须引用至少 1 条规范条文。
"""

    # 无 RAG 规范的 prompt
    prompt_no_rag = f"""Generate a professional building inspection report in Chinese. Follow the format strictly.

Detection result:
- Material: {material}
- Estimated floors: {floor}
- Extension: {extension}
- Defects:
{defects_desc}

Report format requirements:
1. [检测概况] 简述建筑基本信息（材料、层数、加层情况）。
2. [缺陷分析] 逐个分析每个缺陷的严重程度（基于常识判断）。
3. [综合评定] 给出结构安全等级评定（A/B/C/D级）及常识依据。
4. [处理建议] 给出具体可操作的处理建议。

Style:
- 保持客观专业，语言简洁。
- 约 200-300 字。
- 不要引用任何规范或标准条文。
"""

    def _call_llm(prompt_text: str) -> str:
        try:
            response = requests.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": "你是一名专业的建筑结构检测工程师，请根据检测数据生成客观、简洁的中文检测报告。"},
                        {"role": "user", "content": prompt_text},
                    ],
                    "temperature": 0.3,
                },
                timeout=60,
            )
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            return f"[LLM HTTP {response.status_code}]"
        except Exception as e:
            return f"[LLM Error: {e}]"

    report_with_rag = _call_llm(prompt_with_rag)
    report_no_rag = _call_llm(prompt_no_rag)

    # fallback：如果 LLM 都失败了
    if report_with_rag.startswith("[LLM"):
        report_with_rag = (
            f"LLM call failed.\n"
            f"Material: {material}\nFloor: {floor}\nExtension: {extension}\n"
            f"Defect count: {len(defects)}\n"
            f"Regulations: {regulations}"
        )
    if report_no_rag.startswith("[LLM"):
        # 本地 VL 失败 + LLM 也失败 → 兜底
        vl_info = f"Local VL error: {local_vl_error}\n" if local_vl_error else ""
        report_no_rag = (
            f"LLM call failed.\n{vl_info}"
            f"Material: {material}\nFloor: {floor}\nExtension: {extension}\n"
            f"Defect count: {len(defects)}"
        )

    return {
        "report": report_with_rag,
        "report_no_rag": report_no_rag,
    }
