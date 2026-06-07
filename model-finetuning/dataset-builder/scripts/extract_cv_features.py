import argparse
import json
import sys
from pathlib import Path

import cv2

from common import load_config, read_csv, write_csv, write_jsonl


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def normalize_text(value: str) -> str:
    if value is None:
        return "未知"
    text = str(value).strip()
    return text if text else "未知"


def stringify_defects(defects: list[dict]) -> str:
    if not defects:
        return "[]"
    out = []
    for defect in defects:
        out.append(
            {
                "id": defect.get("id"),
                "type": defect.get("type"),
                "area": round(float(defect.get("area", 0.0)), 2),
            }
        )
    return json.dumps(out, ensure_ascii=False)


def load_predictors(model_cfg: dict):
    from predictors.added_floor import AddedFloorPredictor
    from predictors.floor import FloorPredictor
    from predictors.hidden_danger import HiddenDangerPredictor
    from predictors.material import MaterialPredictor

    root = Path(__file__).resolve().parents[3]
    floor_predictor = FloorPredictor(
        root / model_cfg["main_building_pt"],
        root / model_cfg["outer_obj_pt"],
    )
    added_predictor = AddedFloorPredictor(root / model_cfg["add_predict_pth"])
    material_predictor = MaterialPredictor(root / model_cfg["material_pth"])
    defect_predictor = HiddenDangerPredictor(root / model_cfg["hidden_best_pt"])

    return material_predictor, floor_predictor, added_predictor, defect_predictor


def main():
    parser = argparse.ArgumentParser(description="对 split 列表批量提取四项检测指标")
    parser.add_argument("--config", default="config/config.json", help="配置文件路径")
    parser.add_argument(
        "--input-csv",
        default="output/splits/all_splits.csv",
        help="split_dataset.py 输出的 csv",
    )
    parser.add_argument(
        "--output-csv",
        default="output/features/features.csv",
        help="四指标输出 csv",
    )
    parser.add_argument(
        "--output-jsonl",
        default="output/features/features.jsonl",
        help="四指标输出 jsonl",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    model_cfg = cfg.get("models", {})

    dataset_root = Path(__file__).resolve().parents[1]

    input_csv = Path(args.input_csv)
    if not input_csv.is_absolute():
        input_csv = (dataset_root / input_csv).resolve()
    rows = read_csv(input_csv)
    if not rows:
        raise ValueError(f"输入 CSV 为空: {input_csv}")

    material_model, floor_model, added_model, defect_model = load_predictors(model_cfg)

    output_rows = []
    output_jsonl = []
    total = len(rows)

    for idx, row in enumerate(rows, start=1):
        image_path = Path(row["file_path"])
        image = cv2.imread(str(image_path))
        if image is None:
            print(f"[{idx}/{total}] 跳过：无法读取图片 {image_path}")
            continue

        try:
            material = normalize_text(material_model.predict([image])[0])
        except Exception:
            material = normalize_text(row.get("material_from_name", "未知"))

        try:
            floor = normalize_text(floor_model.predict([image])[0])
        except Exception:
            floor = "未知"

        try:
            extension = normalize_text(added_model.predict([image])[0])
        except Exception:
            extension = "未知"

        try:
            defects = defect_model.predict([image])[0] or []
        except Exception:
            defects = []

        defects_json = stringify_defects(defects)

        out = {
            "split": row["split"],
            "id": row["id"],
            "filename": row["filename"],
            "file_path": row["file_path"],
            "material": material,
            "floor": floor,
            "has_extension": extension,
            "defects_json": defects_json,
            "defect_count": len(defects),
        }
        output_rows.append(out)

        output_jsonl.append(
            {
                "split": row["split"],
                "id": row["id"],
                "image": row["file_path"],
                "features": {
                    "material": material,
                    "floor": floor,
                    "has_extension": extension,
                    "defects": defects,
                },
            }
        )

        print(
            f"[{idx}/{total}] 完成: {row['filename']} | 材质={material} 楼层={floor} 加层={extension} 隐患数={len(defects)}"
        )

    output_csv = Path(args.output_csv)
    if not output_csv.is_absolute():
        output_csv = (dataset_root / output_csv).resolve()
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "split",
        "id",
        "filename",
        "file_path",
        "material",
        "floor",
        "has_extension",
        "defects_json",
        "defect_count",
    ]
    write_csv(output_csv, output_rows, headers=headers)

    output_jsonl_path = Path(args.output_jsonl)
    if not output_jsonl_path.is_absolute():
        output_jsonl_path = (dataset_root / output_jsonl_path).resolve()
    write_jsonl(output_jsonl_path, output_jsonl)

    print(f"四指标提取完成，CSV: {output_csv}")
    print(f"四指标提取完成，JSONL: {output_jsonl_path}")


if __name__ == "__main__":
    main()


