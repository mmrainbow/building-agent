import argparse
import json
import random
from pathlib import Path

from common import load_config, read_csv, write_csv, write_jsonl
from question_bank import build_question_pool, build_report_task_pool, priority_defect, render_template


def parse_defects(defects_json):
    try:
        data = json.loads(defects_json or "[]")
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def defect_summary(defects):
    if not defects:
        return "未检出明显隐患"
    parts = []
    for defect in defects:
        defect_type = defect.get("type", "未知隐患")
        area = defect.get("area", 0)
        try:
            area_text = f"{float(area):.1f}"
        except Exception:
            area_text = str(area)
        parts.append(f"{defect_type}（像素面积约{area_text}px）")
    return "、".join(parts)


def feature_text(row, defects):
    return (
        f"检测结果：材质={row.get('material', '未知')}；"
        f"楼层={row.get('floor', '未知')}；"
        f"加层={row.get('has_extension', '未知')}；"
        f"隐患={json.dumps(defects, ensure_ascii=False)}。"
    )


def build_report_input(row, defects, report_instruction):
    return f"请根据图像与检测结果生成住建巡检文本。本次任务：{report_instruction}{feature_text(row, defects)}"


def build_report_reference(row, defects):
    defect_text = defect_summary(defects)
    if defects:
        advice = "建议尽快组织现场复核，确认隐患范围和成因，按风险程度制定维修方案，并对重点区域持续跟踪。"
    else:
        advice = "当前未发现明显外立面隐患，建议保持周期性巡检，留存记录，并关注材料老化、节点松动和雨后渗漏迹象。"

    return (
        f"该建筑外立面材质为{row.get('material', '未知')}，估计楼层为{row.get('floor', '未知')}，"
        f"加层情况为{row.get('has_extension', '未知')}。本次检测显示：{defect_text}。{advice}"
    )


def build_qa_input(row, defects, question):
    return f"请基于图像与检测结果回答问题。{feature_text(row, defects)}问题：{question}"


def build_qa_reference(defects):
    if defects:
        priority = priority_defect(defects)
        return (
            f"应优先关注{priority}问题。该类问题可能影响外立面耐久性或使用安全，"
            "建议先进行现场复核，确认范围和成因后再制定维修、加固或防水处理方案。"
        )
    return (
        "当前未检出明显隐患，仍建议保留本次巡检记录，后续重点关注连接节点、外立面材料老化、"
        "疑似加层部位和雨后渗漏迹象。"
    )


def main():
    parser = argparse.ArgumentParser(description="基于四指标构建独立评测 JSONL，不调用待评估大模型")
    parser.add_argument("--config", default="config/config.json", help="配置文件路径")
    parser.add_argument("--features-csv", default="output/features/features.csv")
    parser.add_argument("--target-split", default="test", choices=["train", "val", "test", "all"])
    parser.add_argument("--output-jsonl", default="output/jsonl/eval_set_generated.jsonl")
    parser.add_argument("--review-csv", default="output/jsonl/manual_review.csv")
    parser.add_argument("--qa-per-image", type=int, default=1, help="每张图片最多生成几条 QA")
    args = parser.parse_args()

    cfg = load_config(args.config)
    dataset_cfg = cfg.get("dataset", {})
    report_ratio = float(dataset_cfg.get("generate_report_ratio", 1.0))
    qa_ratio = float(dataset_cfg.get("generate_qa_ratio", 0.6))

    dataset_root = Path(__file__).resolve().parents[1]
    features_csv = Path(args.features_csv)
    if not features_csv.is_absolute():
        features_csv = (dataset_root / features_csv).resolve()
    rows = read_csv(features_csv)
    if args.target_split != "all":
        rows = [x for x in rows if x.get("split") == args.target_split]
    if not rows:
        raise ValueError("没有可处理的数据，请检查 features-csv 和 target-split")

    random.seed(2026)
    samples = []
    review_rows = []

    for row in rows:
        defects = parse_defects(row.get("defects_json", "[]"))

        if random.random() <= report_ratio:
            report_type, report_template = random.choice(build_report_task_pool(row, defects))
            report_instruction = render_template(report_template, row, defects)
            sample = {
                "id": f"R_{row['split']}_{row['id']}",
                "task": "report",
                "input": build_report_input(row, defects, report_instruction),
                "reference": build_report_reference(row, defects),
                "image": row["file_path"],
                "report_type": report_type,
            }
            samples.append(sample)
            review_rows.append({**sample, "need_review": "是", "review_note": ""})

        question_pool = build_question_pool(row, defects)
        random.shuffle(question_pool)
        qa_limit = max(1, int(args.qa_per_image))
        for question_type, question_template in question_pool[:qa_limit]:
            if random.random() > qa_ratio:
                continue
            question = render_template(question_template, row, defects)
            sample = {
                "id": f"Q_{row['split']}_{row['id']}_{question_type}",
                "task": "qa",
                "input": build_qa_input(row, defects, question),
                "reference": build_qa_reference(defects),
                "image": row["file_path"],
                "question_type": question_type,
            }
            samples.append(sample)
            review_rows.append({**sample, "need_review": "是", "review_note": ""})

    output_jsonl = Path(args.output_jsonl)
    if not output_jsonl.is_absolute():
        output_jsonl = (dataset_root / output_jsonl).resolve()
    write_jsonl(output_jsonl, samples)

    review_csv = Path(args.review_csv)
    if not review_csv.is_absolute():
        review_csv = (dataset_root / review_csv).resolve()
    write_csv(
        review_csv,
        review_rows,
        headers=[
            "id",
            "task",
            "input",
            "reference",
            "image",
            "report_type",
            "question_type",
            "need_review",
            "review_note",
        ],
    )

    print("独立评测 JSONL 构建完成：")
    print(f"- 输出文件: {output_jsonl}")
    print(f"- 人工复核表: {review_csv}")
    print(f"- 样本总数: {len(samples)}")


if __name__ == "__main__":
    main()


