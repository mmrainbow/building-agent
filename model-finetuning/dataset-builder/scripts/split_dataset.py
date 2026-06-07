import argparse
import random
from pathlib import Path

from common import (
    infer_id_from_filename,
    infer_material_from_filename,
    list_images,
    load_config,
    write_csv,
)


def main():
    parser = argparse.ArgumentParser(description="按配置将图片随机划分为 train/val/test")
    parser.add_argument(
        "--config",
        default="config/config.json",
        help="配置文件路径（相对 dataset-builder 或绝对路径）",
    )
    parser.add_argument(
        "--out-dir",
        default="output/splits",
        help="输出目录（相对 dataset-builder 或绝对路径）",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    images_dir = Path(cfg["images_dir"]).resolve()
    exts = cfg.get("image_extensions", [".jpg", ".jpeg", ".png"])
    split_cfg = cfg.get("split", {})
    val_size = int(split_cfg.get("val_size", 200))
    test_size = int(split_cfg.get("test_size", 200))
    seed = int(split_cfg.get("seed", 2026))
    naming_rule = cfg.get("naming_rule", {})

    if not images_dir.exists():
        raise FileNotFoundError(f"图片目录不存在: {images_dir}")

    images = list_images(images_dir, exts)
    total = len(images)
    if total == 0:
        raise ValueError("未找到任何图片，请检查 images_dir 和 image_extensions")

    if val_size + test_size >= total:
        raise ValueError(
            f"划分失败：总数={total}，val={val_size}，test={test_size}，训练集将为空。"
        )

    random.seed(seed)
    random.shuffle(images)

    val_files = images[:val_size]
    test_files = images[val_size : val_size + test_size]
    train_files = images[val_size + test_size :]

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (Path(__file__).resolve().parents[1] / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    def convert_rows(paths: list[Path], split_name: str):
        rows = []
        for path in paths:
            stem = path.stem
            rows.append(
                {
                    "split": split_name,
                    "id": infer_id_from_filename(stem),
                    "filename": path.name,
                    "file_path": str(path),
                    "material_from_name": infer_material_from_filename(stem, naming_rule),
                }
            )
        return rows

    train_rows = convert_rows(train_files, "train")
    val_rows = convert_rows(val_files, "val")
    test_rows = convert_rows(test_files, "test")
    all_rows = train_rows + val_rows + test_rows

    headers = ["split", "id", "filename", "file_path", "material_from_name"]
    write_csv(out_dir / "train.csv", train_rows, headers=headers)
    write_csv(out_dir / "val.csv", val_rows, headers=headers)
    write_csv(out_dir / "test.csv", test_rows, headers=headers)
    write_csv(out_dir / "all_splits.csv", all_rows, headers=headers)

    print("数据集划分完成：")
    print(f"- 总数: {total}")
    print(f"- train: {len(train_rows)}")
    print(f"- val: {len(val_rows)}")
    print(f"- test: {len(test_rows)}")
    print(f"- 输出目录: {out_dir}")


if __name__ == "__main__":
    main()


