"""ReAct Agent 第四阶段 — ManagerAgent.run 端到端测试（独立脚本）。

用法（项目根目录）:
    python scripts/test_agent_step3_react.py

注意: 会调用通义 API 并可能加载 CV 模型，耗时较长。
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
# 内存库须在 import db.database 之前覆盖 .env 中的文件路径
os.environ["INSPECTION_DB_URL"] = "sqlite:///:memory:"

from db.models import Base  # noqa: E402
from db.database import SessionLocal, engine  # noqa: E402
from db.crud_user import create_user  # noqa: E402
from db.chat_crud import create_conversation  # noqa: E402
from llm.client import LLMClient  # noqa: E402
from llm.tools import build_tools  # noqa: E402
from agent.orchestrator import ManagerAgent  # noqa: E402

USER_MESSAGE = "这栋楼有什么隐患吗？材质是什么？帮我出个报告"
FAKE_IMAGE_SHAPE = (640, 640, 3)


def _banner(title: str, char: str = "=") -> None:
    width = 72
    print(char * width)
    print(f"  {title}")
    print(char * width)


def _print_tool_log(tool_log: list[dict]) -> None:
    if not tool_log:
        print("  (无工具调用记录)")
        return
    for i, entry in enumerate(tool_log, 1):
        print(f"\n  ┌─ 工具调用 #{i} ─────────────────────────────────")
        print(f"  │ 名称: {entry.get('name')}")
        args = entry.get("arguments") or {}
        print(f"  │ 参数: {args if args else '(无 — CV 工具由 orchestrator 注入 image)'}")
        print(f"  │ 耗时: {entry.get('elapsed_ms')} ms")
        print("  │ 返回:")
        result = entry.get("result") or ""
        for line in textwrap.wrap(result, width=64):
            print(f"  │   {line}")
        print("  └" + "─" * 40)


def _print_response(text: str) -> None:
    print("\n  ┌─ 最终回复 (response) ─────────────────────────────")
    if not text or not str(text).strip():
        print("  │  (空)")
    else:
        for line in str(text).splitlines():
            wrapped = textwrap.wrap(line, width=64) or [""]
            for w in wrapped:
                print(f"  │  {w}")
    print("  └" + "─" * 40)


def setup_memory_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user = create_user(db, "react_test_user", "testpass123")
    if user is None:
        from db.models import User

        user = db.query(User).filter(User.username == "react_test_user").first()
    conv = create_conversation(
        db, user_id=user.id, title="ReAct E2E 测试", model="qwen-test"
    )
    return db, user, conv


def main() -> None:
    _banner("ReAct Step3: ManagerAgent 端到端测试")

    if not os.getenv("DASHSCOPE_API_KEY"):
        print("\n错误: 未设置 DASHSCOPE_API_KEY，请在 .env 中配置后重试。")
        raise SystemExit(1)

    print("\n>>> 初始化 SQLite 内存库 ...")
    db, user, conv = setup_memory_db()
    print(f"    user_id={user.id}, conversation_id={conv.id}")

    print("\n>>> 初始化 Agent + Tools ...")
    llm = LLMClient()
    agent = ManagerAgent(llm, max_rounds=10)
    agent.tools = build_tools()
    print(f"    模型: {llm.model}")
    print(f"    工具: {list(agent.tools.keys())}")

    fake_image = np.zeros(FAKE_IMAGE_SHAPE, dtype=np.uint8)
    print(f"\n>>> 输入图像: shape={fake_image.shape}")
    print(f">>> 用户消息: {USER_MESSAGE}")
    print("\n>>> 调用 agent.run() ... (可能需要 1～3 分钟)\n")

    try:
        result = agent.run(
            user_id=user.id,
            conversation_id=conv.id,
            message=USER_MESSAGE,
            image=fake_image,
            db=db,
        )
    except Exception as e:
        print(f"\nagent.run 失败: {type(e).__name__}: {e}")
        raise SystemExit(1) from e
    finally:
        db.close()

    _banner("tool_log — 工具调用链（思维链的外部痕迹）", "-")
    _print_tool_log(result.get("tool_log") or [])

    _banner("最终报告", "-")
    _print_response(result.get("response") or "")

    usage = result.get("usage") or {}
    print(f"\n>>> ReAct 统计")
    print(f"    工具调用次数 (len tool_log): {len(result.get('tool_log') or [])}")
    print(f"    rounds 字段: {result.get('rounds')}")
    print(f"    tokens — prompt: {usage.get('prompt_tokens')}, "
          f"completion: {usage.get('completion_tokens')}, "
          f"total: {usage.get('total_tokens')}")

    _banner("完成")


if __name__ == "__main__":
    main()
