"""ReAct Agent 第三阶段 — CV Tool（detect_defects）封装测试（独立脚本）。

用法（项目根目录）:
    python scripts/test_agent_step2_tool.py
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from llm.tools import build_tools  # noqa: E402


def main() -> None:
    print("=" * 60)
    print("ReAct Step2 Tool: detect_defects 封装测试")
    print("=" * 60)

    tools = build_tools()
    tool_name = "detect_defects"

    if tool_name not in tools:
        print(f"错误: 未找到工具 '{tool_name}'")
        print("可用工具:", list(tools.keys()))
        raise SystemExit(1)

    defect_tool = tools[tool_name]
    print(f"\n工具类型: {type(defect_tool).__name__}")
    print(f"Schema 名称: {defect_tool.schema['function']['name']}")
    print(f"延迟加载状态 (_predictor is None): {defect_tool._predictor is None}")

    fake_image = np.zeros((640, 640, 3), dtype=np.uint8)
    print(f"\n输入图像: shape={fake_image.shape}, dtype={fake_image.dtype}")
    print("执行 defect_tool.execute(image=fake_image) ...\n")
    print("-" * 60)

    result = defect_tool.execute(image=fake_image)

    print("返回字符串:")
    wrapped = textwrap.fill(result, width=58, initial_indent="  ", subsequent_indent="  ")
    print(wrapped)
    print("-" * 60)
    print(f"\n执行后 _predictor 已加载: {defect_tool._predictor is not None}")
    print("=" * 60)


if __name__ == "__main__":
    main()
