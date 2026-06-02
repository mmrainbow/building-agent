"""ReAct 文本解析器 — 当 LLM 不支持原生 function calling 时，从文本输出中提取工具调用。

支持的格式 (与 vLLM + Qwen2.5 的 prompt 配合):
    <tool_call>
    {"name": "classify_material", "arguments": {}}
    </tool_call>

也兼容:
    <tool_call>{"name": "search_knowledge", "arguments": {"query": "裂缝标准"}}</tool_call>

返回格式与 OpenAI tool_calls 兼容:
    [{"id": "call_0", "function": {"name": "...", "arguments": "..."}, "type": "function"}]
"""

import json
import re
from typing import Any

_TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL | re.IGNORECASE
)


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    """从 LLM 文本输出中提取 tool_calls。

    Args:
        text: LLM 生成的原始文本，可能包含 <tool_call> 标记

    Returns:
        OpenAI 兼容的 tool_calls 列表；如果没有找到则返回空列表
    """
    matches = _TOOL_CALL_PATTERN.findall(text)
    if not matches:
        # 也尝试解析 ```json...``` 代码块中的 tool_call
        json_block = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if json_block:
            try:
                data = json.loads(json_block.group(1))
                if isinstance(data, dict) and "name" in data:
                    matches = [json.dumps(data, ensure_ascii=False)]
                elif isinstance(data, list):
                    matches = [json.dumps(item, ensure_ascii=False) for item in data if isinstance(item, dict) and "name" in item]
            except json.JSONDecodeError:
                pass

    tool_calls = []
    for i, match in enumerate(matches):
        try:
            call_data = json.loads(match.strip())
        except json.JSONDecodeError:
            # 尝试修复不完整的 JSON
            continue

        if not isinstance(call_data, dict) or "name" not in call_data:
            continue

        arguments = call_data.get("arguments", {})
        if isinstance(arguments, dict):
            arguments = json.dumps(arguments, ensure_ascii=False)

        tool_calls.append({
            "id": f"call_{i}",
            "type": "function",
            "function": {
                "name": call_data["name"],
                "arguments": arguments,
            },
        })

    return tool_calls


def build_tool_prompt(tools: list[dict]) -> str:
    """将 OpenAI tool schema 列表转为 ReAct 提示词文本。

    Args:
        tools: OpenAI 格式的 tool schema 列表

    Returns:
        可嵌入 system prompt 的工具描述文本
    """
    if not tools:
        return ""

    lines = ["## 可用工具\n"]
    for tool in tools:
        func = tool.get("function", tool)
        name = func.get("name", "unknown")
        desc = func.get("description", "")
        params = func.get("parameters", {}).get("properties", {})

        lines.append(f"### {name}")
        lines.append(f"描述: {desc}")

        if params:
            lines.append("参数:")
            for param_name, param_info in params.items():
                param_desc = param_info.get("description", "")
                required = "必填" if param_name in func.get("parameters", {}).get("required", []) else "可选"
                lines.append(f"  - {param_name} ({required}): {param_desc}")

        lines.append("")

    lines.append("## 工具调用格式\n")
    lines.append("当你需要调用工具时，请严格按以下格式输出:\n")
    lines.append("<tool_call>")
    lines.append('{"name": "工具名", "arguments": {"参数名": "参数值"}}')
    lines.append("</tool_call>\n")
    lines.append("可以连续输出多个 <tool_call> 块来调用多个工具。")
    lines.append("调用完成后，等待工具返回结果，然后直接给出最终回答。\n")

    return "\n".join(lines)


def build_tool_result_message(tool_call_id: str, result: str) -> str:
    """将工具执行结果格式化为回传给 LLM 的消息内容。"""
    return f"<tool_result id=\"{tool_call_id}\">\n{result}\n</tool_result>"


def strip_tool_calls(text: str) -> str:
    """从 LLM 输出中移除 <tool_call> 块，只保留文本内容。"""
    return _TOOL_CALL_PATTERN.sub("", text).strip()
