import csv
import json
import re
from pathlib import Path
from typing import Union


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def dataset_builder_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config(config_path: Union[str, Path]) -> dict:
    path = Path(config_path)
    if not path.is_absolute():
        path = (dataset_builder_root() / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"配置文件不是合法 JSON: {path}\n"
            "如果填写 Windows 路径，建议使用正斜杠，例如 "
            '"D:/data/images"，不要写成 "D:\\data\\images"。'
        ) from exc


def ensure_parent(path: Union[str, Path]):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def write_jsonl(path: Union[str, Path], rows: list):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Union[str, Path]) -> list:
    rows = []
    with Path(path).open("r", encoding="utf-8-sig") as file:
        for line in file:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def write_csv(path: Union[str, Path], rows: list, headers: list):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Union[str, Path]) -> list:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def list_images(images_dir: Path, exts: list) -> list:
    ext_set = {x.lower() for x in exts}
    files = []
    for file_path in images_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() in ext_set:
            files.append(file_path.resolve())
    files.sort()
    return files


def infer_id_from_filename(filename_stem: str) -> str:
    match = re.match(r"^(\d+)", filename_stem)
    if match:
        return match.group(1)
    return filename_stem


def infer_material_from_filename(filename_stem: str, naming_rule: dict) -> str:
    if not naming_rule.get("enabled", False):
        return "未知"

    separator = str(naming_rule.get("separator", "_"))
    material_index = int(naming_rule.get("material_part_index", 1))

    parts = filename_stem.split(separator) if separator else [filename_stem]
    if 0 <= material_index < len(parts) and parts[material_index].strip():
        return parts[material_index].strip()

    fallback = re.sub(r"^\d+[_\-\s]*", "", filename_stem).strip()
    return fallback if fallback else "未知"


