import argparse
import base64
import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

from common import load_config, read_csv, write_csv, write_jsonl
from question_bank import build_question_pool, build_report_task_pool, render_template


def parse_defects(defects_json):
    try:
        data = json.loads(defects_json or "[]")
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def image_to_data_url(image_path):
    path = Path(image_path)
    suffix = path.suffix.lower().lstrip(".")
    mime = "jpeg" if suffix in {"jpg", "jpeg"} else suffix or "png"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:image/{mime};base64,{encoded}"


def request_teacher_api(base_url, api_key, model, messages, temperature, timeout):
    clean_base_url = base_url.rstrip("/")
    url = clean_base_url if clean_base_url.endswith("/chat/completions") else f"{clean_base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url=url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {error_body}") from exc
    return str(data["choices"][0]["message"]["content"]).strip()


def feature_block(row, defects):
    return (
        "结构化检测结果：\n"
        f"- 材质：{row.get('material', '未知')}\n"
        f"- 楼层：{row.get('floor', '未知')}\n"
        f"- 加层：{row.get('has_extension', '未知')}\n"
        f"- 隐患：{json.dumps(defects, ensure_ascii=False)}\n"
    )


def area_constraint():
    return (
        "重要约束：隐患中的 area 字段是图像像素面积 px，仅用于相对大小参考，"
        "禁止换算为平方米、平方厘米等真实面积单位。\n"
    )


def build_report_prompt(row, defects, report_instruction):
    return (
        "请为住建管理场景生成一份可作为评测参考答案的巡检文本。\n"
        f"本次任务：{report_instruction}\n"
        "你需要结合图像和结构化检测结果，但不得编造检测结果之外的事实。\n\n"
        f"{feature_block(row, defects)}\n"
        f"{area_constraint()}\n"
        "输出要求：\n"
        "1. 使用中文；\n"
        "2. 120到220字；\n"
        "3. 内容必须覆盖任务要求中的重点；\n"
        "4. 不要输出标题、编号、Markdown，也不要使用“巡检结论：”“主要风险：”“处置建议：”这类分段标签。"
    )


def build_qa_prompt(row, defects, question):
    return (
        "请为住建巡检问答任务生成一条可作为评测参考答案的回答。\n"
        "你需要结合图像和结构化检测结果，但不得编造检测结果之外的事实。\n\n"
        f"{feature_block(row, defects)}"
        f"- 问题：{question}\n\n"
        f"{area_constraint()}\n"
        "输出要求：\n"
        "1. 使用中文；\n"
        "2. 2到5句话；\n"
        "3. 回答要具体、客观、可执行；\n"
        "4. 不要输出标题、编号、Markdown，也不要使用“巡检结论：”“主要风险：”“处置建议：”这类分段标签。"
    )


def build_messages(system_prompt, user_prompt, image_path, include_image):
    if include_image:
        user_content = [
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": image_to_data_url(image_path)}},
        ]
    else:
        user_content = user_prompt
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def ask_teacher(args, api_key, system_prompt, prompt, image_path, include_image):
    messages = build_messages(system_prompt, prompt, image_path, include_image)
    return request_teacher_api(args.base_url, api_key, args.model, messages, args.temperature, args.timeout)


def main():
    parser = argparse.ArgumentParser(description="使用外部教师模型 API 生成评测集参考答案")
    parser.add_argument("--config", default="config/config.json", help="配置文件路径")
    parser.add_argument("--features-csv", default="output/features/features.csv")
    parser.add_argument("--target-split", default="test", choices=["train", "val", "test", "all"])
    parser.add_argument("--output-jsonl", default="output/jsonl/eval_set_teacher.jsonl")
    parser.add_argument("--review-csv", default="output/jsonl/manual_review_teacher.csv")
    parser.add_argument("--base-url", default=os.getenv("TEACHER_BASE_URL", ""))
    parser.add_argument("--api-key-env", default="TEACHER_API_KEY")
    parser.add_argument("--model", default=os.getenv("TEACHER_MODEL", ""))
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--sleep", type=float, default=0.2, help="每次请求后的暂停秒数")
    parser.add_argument("--max-samples", type=int, default=0, help="调试用，0 表示不限制图片数量")
    parser.add_argument("--qa-per-image", type=int, default=1, help="每张图片最多生成几条 QA")
    parser.add_argument("--text-only", action="store_true", help="教师模型不支持图片时使用")
    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env, "")
    if not args.base_url:
        raise ValueError("缺少教师模型 API 地址，请设置 TEACHER_BASE_URL 或传入 --base-url")
    if not args.model:
        raise ValueError("缺少教师模型名称，请设置 TEACHER_MODEL 或传入 --model")
    if not api_key:
        raise ValueError(f"缺少 API Key，请先设置环境变量 {args.api_key_env}")

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
    if args.max_samples > 0:
        rows = rows[: args.max_samples]
    if not rows:
        raise ValueError("没有可处理的数据，请检查 features-csv 和 target-split")

    system_prompt = (
        "你是严谨的住建巡检数据标注专家。你的输出会作为评测参考答案，"
        "必须忠于图像和结构化检测结果，不能把不确定内容写成确定结论。"
    )

    random.seed(2026)
    samples = []
    review_rows = []
    include_image = not args.text_only

    for idx, row in enumerate(rows, start=1):
        defects = parse_defects(row.get("defects_json", "[]"))
        image_path = row["file_path"]

        if random.random() <= report_ratio:
            report_type, report_template = random.choice(build_report_task_pool(row, defects))
            report_instruction = render_template(report_template, row, defects)
            prompt = build_report_prompt(row, defects, report_instruction)
            try:
                reference = ask_teacher(args, api_key, system_prompt, prompt, image_path, include_image)
            except Exception as exc:
                reference = f"生成失败: {exc}"
            sample = {
                "id": f"R_{row['split']}_{row['id']}",
                "task": "report",
                "input": prompt,
                "reference": reference,
                "image": image_path,
                "report_type": report_type,
                "reference_source": f"teacher_api:{args.model}",
            }
            samples.append(sample)
            review_rows.append({**sample, "need_review": "抽检", "review_note": ""})
            time.sleep(args.sleep)

        question_pool = build_question_pool(row, defects)
        random.shuffle(question_pool)
        qa_limit = max(1, int(args.qa_per_image))
        for question_type, question_template in question_pool[:qa_limit]:
            if random.random() > qa_ratio:
                continue
            question = render_template(question_template, row, defects)
            prompt = build_qa_prompt(row, defects, question)
            try:
                reference = ask_teacher(args, api_key, system_prompt, prompt, image_path, include_image)
            except Exception as exc:
                reference = f"生成失败: {exc}"
            sample = {
                "id": f"Q_{row['split']}_{row['id']}_{question_type}",
                "task": "qa",
                "input": prompt,
                "reference": reference,
                "image": image_path,
                "question_type": question_type,
                "reference_source": f"teacher_api:{args.model}",
            }
            samples.append(sample)
            review_rows.append({**sample, "need_review": "抽检", "review_note": ""})
            time.sleep(args.sleep)

        print(f"[{idx}/{len(rows)}] 完成: {row.get('filename', row.get('id'))}")

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
            "reference_source",
            "need_review",
            "review_note",
        ],
    )

    print("教师模型评测集生成完成：")
    print(f"- 输出 JSONL: {output_jsonl}")
    print(f"- 抽检 CSV: {review_csv}")
    print(f"- 样本数: {len(samples)}")


if __name__ == "__main__":
    main()


