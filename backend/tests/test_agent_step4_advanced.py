"""ReAct Agent 第四阶段（进阶）— 多轮对话 + 长期记忆准生产级测试。

用法（项目根目录）:
    python scripts/test_agent_step4_advanced.py
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
os.environ["INSPECTION_DB_URL"] = "sqlite:///:memory:"

from db.models import Base, ConversationMemory, MemoryType  # noqa: E402
from db.database import SessionLocal, engine  # noqa: E402
from db.crud import create_user  # noqa: E402
from db.chat_crud import create_conversation, get_recent_messages  # noqa: E402
from llm.client import LLMClient  # noqa: E402
from llm.tools import build_tools  # noqa: E402
from agent.orchestrator import ManagerAgent  # noqa: E402

ROUND1_MESSAGE = (
    "我上传了这栋楼的照片，帮我看一下材质和大概层数。"
    "注意结合我的偏好给出结论。"
)
ROUND2_MESSAGE = (
    "那这栋楼有没有安全隐患？如果有的话，"
    "请立刻去知识库检索一下这种隐患的危险等级和处理规范！"
)

MEMORIES_SPEC = [
    {
        "memory_type": MemoryType.preference.value,
        "content": "用户偏好：生成的巡检报告必须非常简短，且语气要极其严厉。",
    },
    {
        "memory_type": MemoryType.building_info.value,
        "content": "历史建筑事实：这栋楼上个月刚做过防水外墙涂料翻新。",
    },
]


def _banner(title: str, char: str = "=") -> None:
    w = 72
    print(f"\n{char * w}\n  {title}\n{char * w}")


def _print_tool_log(tool_log: list[dict], indent: str = "  ") -> None:
    if not tool_log:
        print(f"{indent}(无工具调用)")
        return
    for i, e in enumerate(tool_log, 1):
        print(f"{indent}[{i}] {e.get('name')}  args={e.get('arguments') or {}}  "
              f"elapsed={e.get('elapsed_ms')}ms")
        result = (e.get("result") or "").replace("\n", " ")
        print(f"{indent}    → {textwrap.fill(result, width=66, initial_indent='      ', subsequent_indent='      ')}")


def _print_response(text: str, indent: str = "  ") -> None:
    if not text or not str(text).strip():
        print(f"{indent}(空回复)")
        return
    for line in str(text).splitlines():
        for w in textwrap.wrap(line, width=68) or [""]:
            print(f"{indent}{w}")


def _print_usage(usage: dict, indent: str = "  ") -> None:
    print(
        f"{indent}prompt_tokens={usage.get('prompt_tokens', 0)}  "
        f"completion_tokens={usage.get('completion_tokens', 0)}  "
        f"total_tokens={usage.get('total_tokens', 0)}"
    )


def _estimate_llm_rounds(tool_log: list[dict]) -> str:
    """orchestrator 未导出 LLM 外层循环次数；按工具调用分布给出说明。"""
    n = len(tool_log)
    if n == 0:
        return "0 次外层 LLM 请求（直接文本回复）"
    return (
        f"工具执行 {n} 次（result['rounds']={n}）；"
        f"外层 LLM 请求通常为 1～{min(n + 1, 10)} 次（有 tool_calls 则至少 2 次）"
    )


def setup_db():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    user = create_user(db, "advanced_test_user", "pass123456")
    if user is None:
        from db.models import User

        user = db.query(User).filter(User.username == "advanced_test_user").first()
    conv = create_conversation(db, user_id=user.id, title="Step4 高级测试")
    return db, user, conv


def build_memory_objects(user_id: int, conversation_id: int) -> list[ConversationMemory]:
    """未写入 DB，仅作为 run(memories=...) 的注入对象。"""
    objs = []
    for spec in MEMORIES_SPEC:
        m = ConversationMemory(
            user_id=user_id,
            conversation_id=conversation_id,
            memory_type=spec["memory_type"],
            content=spec["content"],
        )
        objs.append(m)
    return objs


def main() -> None:
    _banner("ReAct Step4 Advanced: 多轮 + 长期记忆")

    if not os.getenv("DASHSCOPE_API_KEY"):
        print("错误: 需要 DASHSCOPE_API_KEY")
        raise SystemExit(1)

    db, user, conv = setup_db()
    user_id, conv_id = user.id, conv.id
    print(f"  user_id={user_id}, conversation_id={conv_id}")

    memories = build_memory_objects(user_id, conv_id)
    print("  注入长期记忆:")
    for m in memories:
        print(f"    - [{m.memory_type}] {m.content[:50]}...")

    llm = LLMClient()
    agent = ManagerAgent(llm, max_rounds=10)
    agent.tools = build_tools()
    fake_image = np.zeros((640, 640, 3), dtype=np.uint8)

    # ── 第一轮 ─────────────────────────────────────────────
    _banner("第一轮：材质 + 层数 + 偏好记忆", "-")
    print(f"  User: {ROUND1_MESSAGE}\n")

    r1 = agent.run(
        user_id=user_id,
        conversation_id=conv_id,
        message=ROUND1_MESSAGE,
        image=fake_image,
        db=db,
        memories=memories,
    )

    print("  ▶ ReAct 轮次说明:", _estimate_llm_rounds(r1.get("tool_log") or []))
    print("  ▶ 工具日志 (tool_log):")
    _print_tool_log(r1.get("tool_log") or [])
    print("\n  ▶ 最终回复:")
    _print_response(r1.get("response") or "")
    print("\n  ▶ Token 消耗:")
    _print_usage(r1.get("usage") or {})

    # ── 第二轮 ─────────────────────────────────────────────
    _banner("第二轮：隐患 + 知识库（带对话历史）", "-")

    recent = get_recent_messages(db, conv_id, limit=20)
    print(f"  从 DB 加载 recent_messages: {len(recent)} 条")
    for m in recent:
        preview = (m.content or "")[:60].replace("\n", " ")
        print(f"    [{m.role}] id={m.id}: {preview}...")

    print(f"\n  User: {ROUND2_MESSAGE}\n")

    r2 = agent.run(
        user_id=user_id,
        conversation_id=conv_id,
        message=ROUND2_MESSAGE,
        image=fake_image,
        db=db,
        recent_messages=recent,
        memories=memories,
    )

    print("  ▶ 工具日志 (tool_log):")
    _print_tool_log(r2.get("tool_log") or [])
    print("\n  ▶ 最终回复:")
    _print_response(r2.get("response") or "")
    print("\n  ▶ Token 消耗:")
    _print_usage(r2.get("usage") or {})

    # 串行链观察
    names = [e.get("name") for e in (r2.get("tool_log") or [])]
    if names:
        print("\n  ▶ 第二轮工具调用顺序:", " → ".join(names))

    db.close()
    _banner("完成")


if __name__ == "__main__":
    main()
