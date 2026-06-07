import argparse
import json
from pathlib import Path

from common import read_jsonl, write_jsonl


def is_failed_reference(text):
    value = str(text or "").strip()
    return not value or value.startswith("生成失败")


def normalize_path(path):
    return str(Path(path)) if path else ""


def build_user_content(input_text, include_image_token):
    text = str(input_text or "").strip()
    if include_image_token:
        return f"<image>\n{text}"
    return text


def convert_rows(rows, include_image=True, include_image_token=True, skip_missing_images=True):
    converted = []
    skipped = {
        "failed_reference": 0,
        "missing_input": 0,
        "missing_image": 0,
    }

    for row in rows:
        input_text = row.get("input", "")
        reference = row.get("reference", "")
        image_path = row.get("image", "")

        if not str(input_text).strip():
            skipped["missing_input"] += 1
            continue
        if is_failed_reference(reference):
            skipped["failed_reference"] += 1
            continue

        item = {
            "id": row.get("id", ""),
            "task": row.get("task", ""),
            "messages": [
                {
                    "role": "user",
                    "content": build_user_content(input_text, include_image_token and include_image),
                },
                {
                    "role": "assistant",
                    "content": str(reference).strip(),
                },
            ],
        }

        if include_image:
            if not image_path or not Path(image_path).exists():
                if skip_missing_images:
                    skipped["missing_image"] += 1
                    continue
            item["images"] = [normalize_path(image_path)]

        for key in ["report_type", "question_type", "reference_source"]:
            if row.get(key):
                item[key] = row.get(key)

        converted.append(item)

    return converted, skipped


def main():
    parser = argparse.ArgumentParser(description="将 teacher JSONL 转换为 LoRA 微调对话格式")
    parser.add_argument("--input", required=True, help="输入 teacher JSONL")
    parser.add_argument("--output", required=True, help="输出 LoRA JSONL")
    parser.add_argument("--text-only", action="store_true", help="不输出 images 字段，也不添加 <image>")
    parser.add_argument("--no-image-token", action="store_true", help="保留 images 字段，但 user content 不加 <image>")
    parser.add_argument("--keep-missing-images", action="store_true", help="图片不存在时仍保留样本")
    args = parser.parse_args()

    rows = read_jsonl(args.input)
    converted, skipped = convert_rows(
        rows,
        include_image=not args.text_only,
        include_image_token=not args.no_image_token,
        skip_missing_images=not args.keep_missing_images,
    )
    write_jsonl(args.output, converted)

    print("LoRA 数据转换完成：")
    print(f"- 输入样本数: {len(rows)}")
    print(f"- 输出样本数: {len(converted)}")
    print(f"- 输出文件: {args.output}")
    print(f"- 跳过失败 reference: {skipped['failed_reference']}")
    print(f"- 跳过空 input: {skipped['missing_input']}")
    print(f"- 跳过缺失图片: {skipped['missing_image']}")


if __name__ == "__main__":
    main()


