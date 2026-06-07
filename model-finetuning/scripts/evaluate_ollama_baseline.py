import argparse
import base64
import json
import statistics
import time
import urllib.request
from pathlib import Path
from typing import Optional


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


def load_existing_rows(path: Path):
    if not path.exists():
        return []
    return load_jsonl(path)


def check_ollama_available(base_url: str):
    url = f"{base_url.rstrip('/')}/api/tags"
    req = urllib.request.Request(url=url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
    except Exception as exc:
        raise RuntimeError(
            "无法连接 Ollama 服务。请先启动 Ollama，并确认 --base-url 正确。"
            f" 当前地址: {base_url}。原始错误: {exc}"
        ) from exc


def validate_eval_samples(samples: list, eval_path: Path):
    invalid_rows = []
    for idx, sample in enumerate(samples[:20], start=1):
        if not sample.get("task") or not sample.get("input"):
            invalid_rows.append(idx)
    if invalid_rows:
        raise ValueError(
            f"评测集格式不正确: {eval_path}\n"
            "当前文件像是 features.jsonl 或 split 清单，不是正式 eval_set。\n"
            "正式评测集每行至少需要包含: id, task, input, reference, image。\n"
            "请使用 model-finetuning/dataset-builder/output/jsonl/eval_set_teacher.jsonl，"
            "或先复制它到 model-finetuning/data/eval_set.jsonl。"
        )


def request_ollama(base_url: str, payload: dict) -> dict:
    url = f"{base_url.rstrip('/')}/api/chat"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def percentile(values, p):
    if not values:
        return 0.0
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * p
    floor_index = int(k)
    ceil_index = min(floor_index + 1, len(sorted_values) - 1)
    if floor_index == ceil_index:
        return float(sorted_values[floor_index])
    return float(
        sorted_values[floor_index]
        + (sorted_values[ceil_index] - sorted_values[floor_index]) * (k - floor_index)
    )


def ns_to_s(value):
    if value is None:
        return None
    return float(value) / 1_000_000_000.0


def resolve_image_to_b64(image_value: str, eval_set_path: Path, image_root: Optional[str]) -> str:
    text = str(image_value).strip()
    if not text:
        raise ValueError("image 字段为空")

    if text.startswith("data:image") and "," in text:
        return text.split(",", 1)[1]

    maybe_b64 = "".join(text.split())
    if len(maybe_b64) > 256:
        try:
            base64.b64decode(maybe_b64, validate=True)
            return maybe_b64
        except Exception:
            pass

    image_path = Path(text)
    if not image_path.is_absolute():
        base_dir = Path(image_root) if image_root else eval_set_path.parent
        image_path = (base_dir / image_path).resolve()

    if not image_path.exists():
        raise FileNotFoundError(f"找不到图像文件: {image_path}")

    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


def build_payload(args, user_input: str, image_b64: Optional[str] = None):
    user_message = {"role": "user", "content": user_input}
    if image_b64 and not args.text_only:
        user_message["images"] = [image_b64]

    return {
        "model": args.model,
        "messages": [
            {"role": "system", "content": args.system_prompt},
            user_message,
        ],
        "stream": False,
        "options": {
            "temperature": args.temperature,
            "top_p": args.top_p,
            "num_ctx": args.num_ctx,
        },
    }


def output_key(row: dict):
    return str(row.get("id", ""))


def summarize(rows: list, model: str):
    durations = [float(row.get("latency_sec", 0.0)) for row in rows]
    output_lengths = [len(str(row.get("output") or "")) for row in rows]
    success_count = sum(1 for row in rows if row.get("ok"))

    tps_list = []
    for row in rows:
        tokens_per_sec = row.get("tokens_per_sec")
        if tokens_per_sec is not None:
            tps_list.append(float(tokens_per_sec))

    sample_count = len(rows)
    success_rate = success_count / sample_count * 100.0 if sample_count else 0.0
    return {
        "model": model,
        "sample_count": sample_count,
        "success_count": success_count,
        "success_rate_percent": round(success_rate, 2),
        "avg_latency_sec": round(statistics.mean(durations), 6) if durations else 0.0,
        "p95_latency_sec": round(percentile(durations, 0.95), 6) if durations else 0.0,
        "avg_output_length": round(statistics.mean(output_lengths), 2) if output_lengths else 0.0,
        "std_output_length": round(statistics.pstdev(output_lengths), 2) if len(output_lengths) > 1 else 0.0,
        "avg_tokens_per_sec": round(statistics.mean(tps_list), 4) if tps_list else None,
        "p95_tokens_per_sec": round(percentile(tps_list, 0.95), 4) if tps_list else None,
    }


def write_summary(output_path: Path, rows: list, model: str):
    summary_path = output_path.with_suffix(".summary.json")
    summary = summarize(rows, model)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8-sig")
    return summary_path, summary


def main():
    parser = argparse.ArgumentParser(description="批量评测 Ollama 模型并输出性能与结果")
    parser.add_argument("--model", required=True, help="模型名，例如 qwen3-vl:8b")
    parser.add_argument("--eval-set", required=True, help="评测集 JSONL 文件")
    parser.add_argument("--output", required=True, help="评测输出 JSONL 文件")
    parser.add_argument("--base-url", default="http://localhost:11434", help="Ollama 地址")
    parser.add_argument("--system-prompt", required=True, help="system prompt")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--num-ctx", type=int, default=4096)
    parser.add_argument("--image-root", default=None, help="image 为相对路径时的根目录")
    parser.add_argument("--max-samples", type=int, default=0, help="最多评测多少条，0 表示不限制")
    parser.add_argument("--resume", action="store_true", help="从已有 output 中断点续跑")
    parser.add_argument("--skip-existing", action="store_true", help="跳过 output 中已有 id")
    parser.add_argument("--text-only", action="store_true", help="不向 Ollama 传图片，只评测文本输入")
    parser.add_argument("--summary-every", type=int, default=10, help="每 N 条写一次 summary")
    args = parser.parse_args()

    eval_path = Path(args.eval_set)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    samples = load_jsonl(eval_path)
    if not samples:
        raise ValueError("评测集为空，请先准备数据。")
    validate_eval_samples(samples, eval_path)
    if args.max_samples > 0:
        samples = samples[: args.max_samples]
    check_ollama_available(args.base_url)

    existing_rows = load_existing_rows(out_path) if (args.resume or args.skip_existing) else []
    existing_keys = {output_key(row) for row in existing_rows if output_key(row)}
    rows_for_summary = list(existing_rows)

    mode = "a" if (args.resume or args.skip_existing) and out_path.exists() else "w"
    completed_this_run = 0

    try:
        with out_path.open(mode, encoding="utf-8-sig") as writer:
            for idx, sample in enumerate(samples, start=1):
                sample_id = str(sample.get("id", f"NO_ID_{idx}"))
                if (args.resume or args.skip_existing) and sample_id in existing_keys:
                    print(f"[{idx}/{len(samples)}] {sample_id} 已存在，跳过")
                    continue

                user_input = str(sample.get("input", ""))
                reference = sample.get("reference", "")
                task = sample.get("task", "unknown")
                image_value = sample.get("image")

                try:
                    image_b64 = None
                    if image_value is not None and not args.text_only:
                        image_b64 = resolve_image_to_b64(image_value, eval_path, args.image_root)
                    payload = build_payload(args, user_input, image_b64=image_b64)

                    t0 = time.perf_counter()
                    resp = request_ollama(args.base_url, payload)
                    elapsed = time.perf_counter() - t0

                    ok = True
                    error_msg = ""
                    output_text = (resp.get("message") or {}).get("content", "")
                except Exception as exc:
                    ok = False
                    error_msg = str(exc)
                    output_text = ""
                    resp = {}
                    elapsed = 0.0

                total_duration_s = ns_to_s(resp.get("total_duration"))
                eval_duration_s = ns_to_s(resp.get("eval_duration"))
                eval_count = resp.get("eval_count")
                tps = None
                if eval_duration_s and eval_duration_s > 0 and eval_count is not None:
                    tps = float(eval_count) / eval_duration_s

                row = {
                    "id": sample_id,
                    "task": task,
                    "input": user_input,
                    "reference": reference,
                    "image": image_value,
                    "model": args.model,
                    "ok": ok,
                    "error": error_msg,
                    "output": output_text,
                    "latency_sec": round(elapsed, 6),
                    "total_duration_ns": resp.get("total_duration"),
                    "total_duration_sec": round(total_duration_s, 6) if total_duration_s else None,
                    "eval_count": eval_count,
                    "eval_duration_ns": resp.get("eval_duration"),
                    "eval_duration_sec": round(eval_duration_s, 6) if eval_duration_s else None,
                    "tokens_per_sec": round(tps, 4) if tps is not None else None,
                    "text_only": args.text_only,
                }
                writer.write(json.dumps(row, ensure_ascii=False) + "\n")
                writer.flush()
                rows_for_summary.append(row)
                completed_this_run += 1

                print(f"[{idx}/{len(samples)}] {sample_id} 完成, latency={elapsed:.3f}s, ok={ok}")

                if args.summary_every > 0 and completed_this_run % args.summary_every == 0:
                    write_summary(out_path, rows_for_summary, args.model)
    except KeyboardInterrupt:
        print("\n收到中断信号，已完成的结果已写入输出文件。正在写入当前 summary...")
    finally:
        summary_path, summary = write_summary(out_path, rows_for_summary, args.model)
        print("\n评测阶段结束。")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"结果文件: {out_path}")
        print(f"汇总文件: {summary_path}")


if __name__ == "__main__":
    main()


