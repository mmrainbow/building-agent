"""ReAct Agent 第二阶段 — LLM 与 Tool Schema 握手测试（独立脚本，不修改业务代码）。

用法（在项目根目录）:
    .venv\\Scripts\\python.exe scripts/test_agent_step1_llm.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from llm.client import LLMClient  # noqa: E402
from llm.tools import build_tools, get_tool_schemas  # noqa: E402

USER_MESSAGE = "外墙面砖脱落了，帮我查一下相关的建筑规范"


def main() -> None:
    print("=" * 60)
    print("ReAct Step1: LLM + Tool Schema handshake")
    print("=" * 60)

    tools = build_tools()
    schemas = get_tool_schemas(tools)
    print(f"\n已注册 Tool 数量: {len(schemas)}")
    print("Tool 名称:", [s["function"]["name"] for s in schemas])

    client = LLMClient()
    print(f"\n模型: {client.model}")
    print(f"API: {client.base_url}")
    print(f"API Key: {'已设置' if client.api_key else '未设置 — 将 401'}")

    messages = [{"role": "user", "content": USER_MESSAGE}]
    print(f"\nUser: {USER_MESSAGE}\n")
    print("-" * 60)
    print("client.chat() 返回（JSON）:\n")

    try:
        result = client.chat(messages=messages, tools=schemas)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e), "type": type(e).__name__}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from e

    print("-" * 60)
    if result.get("tool_calls"):
        for tc in result["tool_calls"]:
            fn = tc.get("function", {})
            print(f"\n模型请求调用工具: {fn.get('name')}")
            print(f"  参数 JSON 字符串: {fn.get('arguments')}")
    elif result.get("content"):
        print("\n模型未调用工具，直接文本回复（见 content）。")
    else:
        print("\ncontent 与 tool_calls 均为空，请检查 finish_reason 与 API 配置。")

    print(f"\nfinish_reason: {result.get('finish_reason')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
