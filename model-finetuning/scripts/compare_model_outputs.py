import argparse
import csv
import json
import random
import statistics
from pathlib import Path


DEFECT_TYPES = ["裂缝", "渗水", "空鼓", "脱落"]
REPORT_KEYWORDS = ["巡检", "材质", "楼层", "建议"]
QA_KEYWORDS = ["建议", "优先", "原因", "处理"]


def load_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8-sig") as file:
        for line_no, line in enumerate(file, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL 解析失败: {path} 第 {line_no} 行: {exc}") from exc
    return rows


def safe_mean(values):
    return float(statistics.mean(values)) if values else 0.0


def pct_change(base, new):
    if base == 0:
        return 0.0
    return (new - base) / base * 100.0


def detect_expected_tokens(user_input: str):
    expected = []
    for token in ["有加层", "无加层", "玻璃幕墙", "涂料", "楼层", "材质"]:
        if token in user_input:
            expected.append(token)
    for defect in DEFECT_TYPES:
        if defect in user_input:
            expected.append(defect)
    return expected


def evaluate_quality(row):
    user_input = str(row.get("input", ""))
    output = str(row.get("output", ""))
    task = str(row.get("task", ""))

    required_tokens = detect_expected_tokens(user_input)
    matched = sum(1 for token in required_tokens if token in output)
    fact_consistency = (matched / len(required_tokens)) if required_tokens else 1.0

    keywords = REPORT_KEYWORDS if task == "report" else QA_KEYWORDS
    format_ok = 1.0 if any(k in output for k in keywords) else 0.0

    input_defects = {d for d in DEFECT_TYPES if d in user_input}
    output_defects = {d for d in DEFECT_TYPES if d in output}
    hallucinated = output_defects - input_defects
    hallucination_flag = 1.0 if hallucinated else 0.0

    return {
        "format_score": format_ok,
        "fact_score": fact_consistency,
        "hallucination_flag": hallucination_flag,
    }


def summarize(rows):
    if not rows:
        return {
            "sample_count": 0,
            "avg_latency_sec": 0.0,
            "avg_output_length": 0.0,
            "ok_rate_percent": 0.0,
            "avg_tokens_per_sec": 0.0,
            "format_compliance_percent": 0.0,
            "fact_consistency_percent": 0.0,
            "hallucination_rate_percent": 0.0,
        }

    lat = [float(r.get("latency_sec", 0.0)) for r in rows]
    out_len = [len(str(r.get("output") or "")) for r in rows]
    ok_rate = sum(1 for r in rows if r.get("ok")) / len(rows) * 100.0

    tps_values = []
    for row in rows:
        tokens_per_sec = row.get("tokens_per_sec")
        if tokens_per_sec is not None:
            tps_values.append(float(tokens_per_sec))
            continue
        eval_count = row.get("eval_count")
        eval_duration_ns = row.get("eval_duration_ns")
        if eval_count is not None and eval_duration_ns:
            duration_sec = float(eval_duration_ns) / 1_000_000_000.0
            if duration_sec > 0:
                tps_values.append(float(eval_count) / duration_sec)

    quality_rows = [evaluate_quality(r) for r in rows]
    format_rate = safe_mean([q["format_score"] for q in quality_rows]) * 100.0
    fact_rate = safe_mean([q["fact_score"] for q in quality_rows]) * 100.0
    hallucination_rate = safe_mean([q["hallucination_flag"] for q in quality_rows]) * 100.0

    return {
        "sample_count": len(rows),
        "avg_latency_sec": safe_mean(lat),
        "avg_output_length": safe_mean(out_len),
        "ok_rate_percent": ok_rate,
        "avg_tokens_per_sec": safe_mean(tps_values),
        "format_compliance_percent": format_rate,
        "fact_consistency_percent": fact_rate,
        "hallucination_rate_percent": hallucination_rate,
    }


def build_blind_review_csv(baseline_rows, finetuned_rows, output_csv: Path, seed: int = 42):
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    ft_map = {r.get("id"): r for r in finetuned_rows}
    random.seed(seed)

    with output_csv.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "sample_id",
                "task",
                "candidate_a",
                "candidate_b",
                "input",
                "reference",
                "output_a",
                "output_b",
                "专业性(1-5)",
                "事实一致性(1-5)",
                "术语规范性(1-5)",
                "可执行性(1-5)",
                "总体评分(1-5)",
                "备注",
            ]
        )

        for base in baseline_rows:
            sample_id = base.get("id")
            ft = ft_map.get(sample_id)
            if not ft:
                continue

            if random.random() < 0.5:
                label_a, out_a = "基线模型", base.get("output", "")
                label_b, out_b = "微调模型", ft.get("output", "")
            else:
                label_a, out_a = "微调模型", ft.get("output", "")
                label_b, out_b = "基线模型", base.get("output", "")

            writer.writerow(
                [
                    sample_id,
                    base.get("task", ""),
                    label_a,
                    label_b,
                    base.get("input", ""),
                    base.get("reference", ""),
                    out_a,
                    out_b,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )


def main():
    parser = argparse.ArgumentParser(description="对比基线模型与微调模型评测结果")
    parser.add_argument("--baseline", required=True, help="基线结果 JSONL")
    parser.add_argument("--finetuned", required=True, help="微调结果 JSONL")
    parser.add_argument("--report", required=True, help="输出 Markdown 报告路径")
    parser.add_argument(
        "--blind-review-csv",
        default="model-finetuning/reports/blind_review_samples.csv",
        help="输出盲评 CSV 路径",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    finetuned_path = Path(args.finetuned)
    report_path = Path(args.report)
    blind_csv_path = Path(args.blind_review_csv)

    report_path.parent.mkdir(parents=True, exist_ok=True)

    baseline_rows = load_jsonl(baseline_path)
    finetuned_rows = load_jsonl(finetuned_path)

    base = summarize(baseline_rows)
    ft = summarize(finetuned_rows)

    latency_change = pct_change(base["avg_latency_sec"], ft["avg_latency_sec"])
    length_change = pct_change(base["avg_output_length"], ft["avg_output_length"])
    ok_change = ft["ok_rate_percent"] - base["ok_rate_percent"]
    tps_change = pct_change(base["avg_tokens_per_sec"], ft["avg_tokens_per_sec"]) if base["avg_tokens_per_sec"] else 0.0
    format_change = ft["format_compliance_percent"] - base["format_compliance_percent"]
    fact_change = ft["fact_consistency_percent"] - base["fact_consistency_percent"]
    hallucination_change = ft["hallucination_rate_percent"] - base["hallucination_rate_percent"]

    build_blind_review_csv(baseline_rows, finetuned_rows, blind_csv_path)

    lines = []
    lines.append("# 大模型前后对比报告")
    lines.append("")
    lines.append(f"- 基线结果: `{baseline_path}`")
    lines.append(f"- 微调结果: `{finetuned_path}`")
    lines.append(f"- 盲评文件: `{blind_csv_path}`")
    lines.append("")
    lines.append("## 性能与质量指标")
    lines.append("")
    lines.append("| 指标 | 基线 | 微调后 | 变化 |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| 样本数 | {base['sample_count']} | {ft['sample_count']} | - |")
    lines.append(f"| 成功率(%) | {base['ok_rate_percent']:.2f} | {ft['ok_rate_percent']:.2f} | {ok_change:+.2f}pp |")
    lines.append(f"| 平均时延(秒) | {base['avg_latency_sec']:.4f} | {ft['avg_latency_sec']:.4f} | {latency_change:+.2f}% |")
    lines.append(f"| 平均输出长度(字符) | {base['avg_output_length']:.2f} | {ft['avg_output_length']:.2f} | {length_change:+.2f}% |")
    lines.append(f"| 平均生成速度(tokens/s) | {base['avg_tokens_per_sec']:.2f} | {ft['avg_tokens_per_sec']:.2f} | {tps_change:+.2f}% |")
    lines.append(f"| 格式合规率(%) | {base['format_compliance_percent']:.2f} | {ft['format_compliance_percent']:.2f} | {format_change:+.2f}pp |")
    lines.append(f"| 事实一致率(%) | {base['fact_consistency_percent']:.2f} | {ft['fact_consistency_percent']:.2f} | {fact_change:+.2f}pp |")
    lines.append(f"| 幻觉率(%) | {base['hallucination_rate_percent']:.2f} | {ft['hallucination_rate_percent']:.2f} | {hallucination_change:+.2f}pp |")
    lines.append("")
    lines.append("## 结论建议")
    lines.append("")
    lines.append("- 若微调后事实一致率与格式合规率上升，且幻觉率下降，可判定微调有效。")
    lines.append("- 建议结合盲评文件进行人工评分，补充“专业性、术语规范性、可执行性”结论。")

    report_path.write_text("\n".join(lines), encoding="utf-8-sig")

    print("对比完成。")
    print(f"报告输出: {report_path}")
    print(f"盲评文件: {blind_csv_path}")


if __name__ == "__main__":
    main()


