import os
import tempfile

import cv2
import numpy as np
import pandas as pd

from agent.graph import build_agent
from db import SessionLocal, save_inspection

from .constants import TEXT

agent = build_agent()


def draw_defects(image, defects):
    rendered = image.copy()
    for defect in defects:
        box = defect.get("box", [])
        if len(box) != 4:
            continue
        points = np.array(box, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(rendered, [points], isClosed=True, color=(0, 0, 255), thickness=2)

        label = str(defect.get("id", "?"))
        x, y = points[0][0]
        (text_w, text_h), _ = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
        )
        cv2.rectangle(
            rendered, (x, y - text_h - 4), (x + text_w, y), (255, 255, 255), -1
        )
        cv2.putText(
            rendered,
            label,
            (x, y - 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2,
        )
    return rendered


def do_inspect(image):
    if image is None:
        return None, TEXT["no_image"]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        success, encoded = cv2.imencode(".jpg", image)
        if not success:
            return None, TEXT["encode_failed"]
        tmp.write(encoded.tobytes())
        tmp_path = tmp.name

    try:
        result = agent.invoke({"image_path": tmp_path})
        if result.get("error"):
            return None, f"{TEXT['inspect_failed']}: {result['error']}"
        return {
            "annotated": draw_defects(image, result.get("defects", [])),
            "report": result.get("report", TEXT["no_report"]),
            "material": result.get("material", ""),
            "floor": result.get("floor", ""),
            "has_extension": result.get("has_extension", ""),
            "defects": result.get("defects", []),
        }, None
    except Exception as e:
        return None, f"{TEXT['inspect_failed']}: {e}"
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def inspect_and_save(image, user_state):
    if image is None:
        return None, TEXT["no_image"], user_state
    if not user_state:
        return None, TEXT["login_required"], user_state

    result, error = do_inspect(image)
    if error:
        return None, error, user_state

    db = SessionLocal()
    try:
        save_inspection(
            db=db,
            user_id=user_state["user_id"],
            image_name=f"inspection_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}",
            material=result["material"],
            floor=result["floor"],
            has_extension=result["has_extension"],
            report=result["report"],
            defects=result["defects"],
        )
    finally:
        db.close()

    next_state = {
        **user_state,
        "last_material": result["material"],
        "last_floor": result["floor"],
        "last_has_extension": result["has_extension"],
        "last_defects": result["defects"],
        "last_report": result["report"],
        "last_image": image,
    }
    return result["annotated"], result["report"], next_state
