import os
from pathlib import Path

import cv2
import requests

from predictors.added_floor import AddedFloorPredictor
from predictors.floor import FloorPredictor
from predictors.hidden_danger import HiddenDangerPredictor
from predictors.material import MaterialPredictor

from .state import InspectionState

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:1.5b")
MODEL_DIR = Path(__file__).parent.parent / "models"

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


def report_node(state: InspectionState):
    defects = state.get("defects", []) or []
    if defects:
        defects_desc = "\n".join(
            [f"- Box {d.get('id', '?')}: {d.get('type', 'unknown')} ({d.get('area', 0):.1f}px)" for d in defects]
        )
    else:
        defects_desc = "- No obvious defects found"

    prompt = f"""
Generate a concise professional building inspection report in Chinese.

Detection result:
- Material: {state.get('material', 'Unknown')}
- Estimated floors: {state.get('floor', 'Unknown')}
- Extension: {state.get('has_extension', 'Unknown')}
- Defects:
{defects_desc}

Requirements:
- Keep the report objective and concise.
- Around 120-180 Chinese characters.
- Refer to defects by sequence number only.
"""

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3},
            },
            timeout=60,
        )
        if response.status_code == 200:
            report = response.json().get("response", "").strip()
            if report:
                return {"report": report}
        fallback = (
            f"LLM call failed (HTTP {response.status_code}).\n"
            f"Material: {state.get('material')}\n"
            f"Floor: {state.get('floor')}\n"
            f"Extension: {state.get('has_extension')}\n"
            f"Defect count: {len(defects)}"
        )
        return {"report": fallback}
    except Exception as e:
        fallback = (
            f"LLM call failed: {e}\n"
            f"Material: {state.get('material')}\n"
            f"Floor: {state.get('floor')}\n"
            f"Extension: {state.get('has_extension')}\n"
            f"Defect count: {len(defects)}"
        )
        return {"report": fallback}
