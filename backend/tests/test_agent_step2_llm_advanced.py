"""ReAct Agent 第二阶段（进阶）— 复杂意图下的 Tool 选择验证（独立脚本）。

用法（项目根目录）:
    python scripts/test_agent_step2_llm_advanced.py
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from llm.client import LLMClient  # noqa: E402
from llm.tools import build_tools, get_tool_schemas  # noqa: E402

TEST_CASES = [
    {
        "id": "A",
        "label": "多重意图",
        "message": (
            "帮我看看这栋楼是几层的，外墙用的是什么材料？"
            "顺便查一下这种材料常见的脱落检测规范。"
        ),
    },
    {
        "id": "B",
        "label": "隐式推理",
        "message": (
            "业主投诉说楼顶好像被人私自搭了个棚子，而且二楼窗户边有水渍和裂缝，"
            "你帮我查明一下情况。"
        ),
    },
    {
        "id": "C",
        "label": "带参精准检索",
        "message": (
            "我正在写隐患排查报告，请帮我查一下关于'玻璃幕墙光污染'和"
            "'高层真石漆脱落'的判定标准。"
        ),
    },
    {
        "id": "D",
        "label": "无关意图 / 边界",
        "message": "今天天气不错，能帮我写一首关于建筑工人的诗吗？",
    },
]

SEP = "=" * 72
SUB = "-" * 72


def _parse_tool_calls(tool_calls: list | None) -> list[dict]:
    if not tool_calls:
        return []
    parsed = []
    for tc in tool_calls:
        fn = tc.get("function") or {}
        name = fn.get("name", "?")
        raw_args = fn.get("arguments", "{}")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            args = {"_raw": raw_args}
        parsed.append(
            {
                "id": tc.get("id"),
                "name": name,
                "arguments": args,
            }
        )
    return parsed


def _print_case_header(case_id: str, label: str) -> None:
    print(SEP)
    print(f"  用例 {case_id}  [{label}]")
    print(SEP)


def _print_wrapped(title: str, text: str) -> None:
    print(f"\n>>> {title}")
    wrapped = textwrap.fill(text or "(空)", width=68, initial_indent="    ", subsequent_indent="    ")
    print(wrapped)


def main() -> None:
    print(SEP)
    print("  ReAct Step2 Advanced: 复杂意图 Tool 选择验证")
    print(SEP)

    tools = build_tools()
    schemas = get_tool_schemas(tools)
    client = LLMClient()

    print(f"\n模型: {client.model}")
    print(f"已注册工具: {[s['function']['name'] for s in schemas]}")
    print(f"测试用例数: {len(TEST_CASES)}\n")

    summaries = []

    for case in TEST_CASES:
        _print_case_header(case["id"], case["label"])
        _print_wrapped("用户输入", case["message"])

        messages = [{"role": "user", "content": case["message"]}]

        try:
            result = client.chat(messages=messages, tools=schemas)
        except Exception as e:
            print(f"\n>>> 请求失败: {type(e).__name__}: {e}")
            summaries.append(
                {
                    "id": case["id"],
                    "error": str(e),
                    "tool_names": [],
                    "parallel": False,
                }
            )
            continue

        content = result.get("content")
        content_display = content if content not in (None, "") else "(无文本 — 模型选择调用工具或未生成正文)"
        tool_calls = _parse_tool_calls(result.get("tool_calls"))
        finish = result.get("finish_reason", "?")

        _print_wrapped("content", content_display)
        print(f"\n>>> finish_reason: {finish}")
        print(f">>> tool_calls 数量: {len(tool_calls)}")

        if tool_calls:
            print("\n>>> 解析后的工具调用:")
            for i, tc in enumerate(tool_calls, 1):
                print(SUB)
                print(f"    [{i}] 工具名: {tc['name']}")
                print(f"        call_id: {tc.get('id')}")
                print(f"        参数: {json.dumps(tc['arguments'], ensure_ascii=False)}")
        else:
            print("\n>>> 解析后的工具调用: (无)")

        usage = result.get("usage") or {}
        if usage:
            print(
                f"\n>>> tokens: prompt={usage.get('prompt_tokens')} "
                f"completion={usage.get('completion_tokens')} "
                f"total={usage.get('total_tokens')}"
            )

        names = [t["name"] for t in tool_calls]
        summaries.append(
            {
                "id": case["id"],
                "label": case["label"],
                "finish_reason": finish,
                "tool_names": names,
                "parallel": len(tool_calls) > 1,
                "content_nonempty": bool(content and str(content).strip()),
            }
        )
        print()

    # 汇总表
    print(SEP)
    print("  汇总")
    print(SEP)
    print(f"  {'用例':<6} {'finish':<14} {'并行?':<8} {'工具列表'}")
    print(SUB)
    for s in summaries:
        if "error" in s:
            print(f"  {s['id']:<6} {'ERROR':<14} {'—':<8} {s['error'][:40]}")
        else:
            tools_str = ", ".join(s["tool_names"]) if s["tool_names"] else "(无)"
            print(
                f"  {s['id']:<6} {s.get('finish_reason','?'):<14} "
                f"{'是' if s.get('parallel') else '否':<8} {tools_str}"
            )
    print(SEP)


if __name__ == "__main__":
    main()
