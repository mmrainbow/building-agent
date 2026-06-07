import argparse
import base64
import json
import re
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path


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


def append_jsonl(path: Path, row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8-sig") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_existing_rows(path: Path):
    if not path.exists():
        return []
    return load_jsonl(path)


def percentile(values, ratio):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * ratio))
    return float(ordered[index])


def safe_mean(values):
    return float(statistics.mean(values)) if values else 0.0


def safe_std(values):
    return float(statistics.pstdev(values)) if len(values) > 1 else 0.0


def summarize(rows, model_name):
    total = len(rows)
    success_rows = [row for row in rows if row.get("ok")]
    latencies = [float(row.get("latency_sec", 0.0)) for row in success_rows]
    output_lengths = [len(str(row.get("output") or "")) for row in success_rows]
    tokens_per_sec = [
        float(row["tokens_per_sec"])
        for row in success_rows
        if row.get("tokens_per_sec") is not None
    ]

    return {
        "model": model_name,
        "sample_count": total,
        "success_count": len(success_rows),
        "success_rate_percent": round(len(success_rows) / total * 100, 2) if total else 0.0,
        "avg_latency_sec": round(safe_mean(latencies), 6),
        "p95_latency_sec": round(percentile(latencies, 0.95), 6),
        "avg_output_length": round(safe_mean(output_lengths), 2),
        "std_output_length": round(safe_std(output_lengths), 2),
        "avg_tokens_per_sec": round(safe_mean(tokens_per_sec), 4),
        "p95_tokens_per_sec": round(percentile(tokens_per_sec, 0.95), 4),
    }


def write_summary(output_path: Path, rows: list, model_name: str):
    summary_path = output_path.with_suffix(".summary.json")
    summary = summarize(rows, model_name)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    return summary_path, summary


def resolve_image_path(sample: dict, image_root: str | None):
    image_value = sample.get("image")
    if not image_value:
        return None
    image_path = Path(image_value)
    if not image_path.is_absolute() and image_root:
        image_path = Path(image_root) / image_path
    return image_path


def image_to_base64(image_path: Path):
    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


def extract_line(input_text: str, label: str, default: str = "Unknown"):
    pattern = rf"-\s*{re.escape(label)}：(.+)"
    match = re.search(pattern, input_text)
    if not match:
        return default
    return match.group(1).strip()


def extract_defects(input_text: str):
    match = re.search(r"-\s*隐患：(.+)", input_text)
    if not match:
        return []
    raw = match.group(1).strip()
    try:
        defects = json.loads(raw)
        return defects if isinstance(defects, list) else []
    except json.JSONDecodeError:
        return []


def build_report_payload(sample: dict, image_root: str | None):
    input_text = str(sample.get("input") or "")
    image_path = resolve_image_path(sample, image_root)
    if not image_path or not image_path.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    return {
        "image_base64": image_to_base64(image_path),
        "material": extract_line(input_text, "材质"),
        "floor": extract_line(input_text, "楼层"),
        "has_extension": extract_line(input_text, "加层"),
        "defects": extract_defects(input_text),
    }


def post_json(url: str, payload: dict, timeout: int):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_health(base_url: str, timeout: int):
    url = f"{base_url.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


def main():
    parser = argparse.ArgumentParser(description="评测本地微调 Report Agent")
    parser.add_argument("--eval-set", required=True, help="评测集 JSONL 文件")
    parser.add_argument("--output", required=True, help="评测输出 JSONL 文件")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Report Agent 地址")
    parser.add_argument("--model-name", default="qwen2.5-vl-3b-building-merged", help="summary 中记录的模型名")
    parser.add_argument("--image-root", default=None, help="image 为相对路径时的根目录")
    parser.add_argument("--max-samples", type=int, default=0, help="最多评测多少条，0 表示不限制")
    parser.add_argument("--task-filter", default="report", help="只评测指定 task；传 all 表示不筛选")
    parser.add_argument("--resume", action="store_true", help="从已有 output 中断点续跑")
    parser.add_argument("--skip-existing", action="store_true", help="跳过 output 中已有 id")
    parser.add_argument("--summary-every", type=int, default=10, help="每 N 条写一次 summary")
    parser.add_argument("--timeout", type=int, default=600, help="单次请求超时时间")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    report_url = f"{base_url}/v1/report"

    if not check_health(base_url, min(args.timeout, 10)):
        raise RuntimeError(f"无法连接本地 Report Agent，请先启动服务: {base_url}")

    eval_rows = load_jsonl(Path(args.eval_set))
    if args.task_filter.lower() != "all":
        eval_rows = [row for row in eval_rows if str(row.get("task", "")).lower() == args.task_filter.lower()]
    if args.max_samples > 0:
        eval_rows = eval_rows[: args.max_samples]

    output_path = Path(args.output)
    existing_rows = load_existing_rows(output_path) if (args.resume or args.skip_existing) else []
    existing_ids = {row.get("id") for row in existing_rows}
    rows_for_summary = list(existing_rows)

    if not ((args.resume or args.skip_existing) and output_path.exists()):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("", encoding="utf-8-sig")

    completed_this_run = 0

    try:
        for index, sample in enumerate(eval_rows, start=1):
            sample_id = sample.get("id") or str(index)
            if (args.resume or args.skip_existing) and sample_id in existing_ids:
                print(f"[{index}/{len(eval_rows)}] {sample_id} 已存在，跳过")
                continue

            row = {
                "id": sample_id,
                "task": sample.get("task", ""),
                "input": sample.get("input", ""),
                "reference": sample.get("reference", ""),
                "image": sample.get("image", ""),
                "model": args.model_name,
            }

            started_at = time.time()
            try:
                payload = build_report_payload(sample, args.image_root)
                response = post_json(report_url, payload, args.timeout)
                latency = time.time() - started_at
                output = str(response.get("report", "")).strip()
                output_len = len(output)
                row.update(
                    {
                        "ok": bool(output),
                        "output": output,
                        "latency_sec": round(latency, 6),
                        "agent_elapsed_seconds": response.get("elapsed_seconds"),
                        "output_length": output_len,
                        "tokens_per_sec": round(output_len / latency, 4) if latency > 0 else None,
                        "error": "",
                    }
                )
            except Exception as exc:
                latency = time.time() - started_at
                row.update(
                    {
                        "ok": False,
                        "output": "",
                        "latency_sec": round(latency, 6),
                        "output_length": 0,
                        "tokens_per_sec": None,
                        "error": str(exc),
                    }
                )

            append_jsonl(output_path, row)
            rows_for_summary.append(row)
            completed_this_run += 1

            print(
                f"[{index}/{len(eval_rows)}] {sample_id} 完成, "
                f"latency={row['latency_sec']:.3f}s, ok={row['ok']}"
            )

            if args.summary_every > 0 and completed_this_run % args.summary_every == 0:
                write_summary(output_path, rows_for_summary, args.model_name)

    except KeyboardInterrupt:
        print("\n收到中断信号，已完成的结果已写入输出文件。正在写入 summary...")
    finally:
        summary_path, summary = write_summary(output_path, rows_for_summary, args.model_name)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"结果文件: {output_path}")
        print(f"汇总文件: {summary_path}")


if __name__ == "__main__":
    main()


