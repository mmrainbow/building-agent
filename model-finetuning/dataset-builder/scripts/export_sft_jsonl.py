import argparse
import json
from pathlib import Path

from common import read_csv, write_jsonl


def parse_defects(defects_json: str) -> list[dict]:
    try:
        data = json.loads(defects_json or "[]")
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def main():
    parser = argparse.ArgumentParser(description="将四指标数据导出为微调训练 JSONL（文本监督格式）")
    parser.add_argument(
        "--features-csv",
        default="output/features/features.csv",
        help="extract_cv_features.py 生成的 csv",
    )
    parser.add_argument(
        "--split",
        default="train",
        choices=["train", "val", "test", "all"],
        help="导出哪个 split",
    )
    parser.add_argument(
        "--output-jsonl",
        default="output/jsonl/train_supervised.jsonl",
        help="输出训练 JSONL",
    )
    args = parser.parse_args()

    dataset_root = Path(__file__).resolve().parents[1]

    features_csv = Path(args.features_csv)
    if not features_csv.is_absolute():
        features_csv = (dataset_root / features_csv).resolve()
    rows = read_csv(features_csv)
    if not rows:
        raise ValueError(f"features csv 为空: {features_csv}")

    if args.split != "all":
        rows = [x for x in rows if x.get("split") == args.split]
    if not rows:
        raise ValueError(f"筛选 split={args.split} 后无数据")

    output_rows = []
    for row in rows:
        defects = parse_defects(row.get("defects_json", "[]"))
        user_text = (
            "请基于以下巡检信息输出规范化报告：\n"
            f"材质={row.get('material', '未知')}\n"
            f"楼层={row.get('floor', '未知')}\n"
            f"加层={row.get('has_extension', '未知')}\n"
            f"隐患={json.dumps(defects, ensure_ascii=False)}"
        )
        assistant_text = (
            f"巡检结论：该建筑外立面材质为{row.get('material', '未知')}，"
            f"估计楼层为{row.get('floor', '未知')}，"
            f"加层情况为{row.get('has_extension', '未知')}。"
            f"共识别隐患{len(defects)}处，建议按风险等级开展复核与处置。"
        )
        output_rows.append(
            {
                "id": f"T_{row['split']}_{row['id']}",
                "image": row.get("file_path"),
                "messages": [
                    {"role": "system", "content": "你是住建巡检报告助手。"},
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": assistant_text},
                ],
            }
        )

    output_jsonl = Path(args.output_jsonl)
    if not output_jsonl.is_absolute():
        output_jsonl = (dataset_root / output_jsonl).resolve()
    write_jsonl(output_jsonl, output_rows)

    print(f"训练 JSONL 导出完成: {output_jsonl}")
    print(f"样本数: {len(output_rows)}")


if __name__ == "__main__":
    main()


