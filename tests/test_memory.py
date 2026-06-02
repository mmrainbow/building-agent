"""MemoryManager + ManagerAgent 三轮对话集成测试。

用法（项目根目录，已激活 .venv）:
    $env:PYTHONPATH = (Get-Location).Path
    python scripts/test_memory.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from db.models import Base  # noqa: E402
from db.crud import create_user  # noqa: E402
from db.chat_crud import create_conversation  # noqa: E402
from llm.client import LLMClient  # noqa: E402
from llm.tools import build_tools  # noqa: E402
from agent.orchestrator import ManagerAgent  # noqa: E402
from agent.memory_manager import MemoryManager  # noqa: E402

DB_URL = "sqlite:///./memory_test.db"
engine = create_engine(DB_URL)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def setup_test_data(db):
    user = create_user(db, "test_manager", "pass123456")
    if user is None:
        from db.models import User

        user = db.query(User).filter(User.username == "test_manager").first()
    conv = create_conversation(db, user_id=user.id, title="一号楼巡检测试")
    return user.id, conv.id


def run_one_round(agent, memory_manager, db, user_id, conv_id, query, round_no):
    print(f"\n[用户 第{round_no}轮]: {query}")

    context = memory_manager.build_context(db, user_id, conv_id, query)
    print(f"  build_context → 历史 {len(context['recent_messages'])} 条, 长期记忆 {len(context['memories'])} 条")

    result = agent.run(
        user_id=user_id,
        conversation_id=conv_id,
        message=query,
        db=db,
        recent_messages=context["recent_messages"],
        memories=context["memories"],
    )
    print(f"[AI回复]: {result.get('response', '')}")
    print(f"  (agent.run 内已自动执行记忆提炼)")


def main():
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("错误: 请在 .env 中配置 DASHSCOPE_API_KEY")
        raise SystemExit(1)

    db = SessionLocal()
    user_id, conv_id = setup_test_data(db)

    llm_client = LLMClient()
    agent = ManagerAgent(llm_client)  # 第一个位置参数是 llm_client，不是 client=
    agent.tools = build_tools()
    memory_manager = MemoryManager()

    print("\n" + "=" * 50)
    print("开始双层记忆系统端到端测试")
    print("=" * 50)

    run_one_round(
        agent, memory_manager, db, user_id, conv_id,
        "这栋楼看起来很旧，主要结构是什么？", 1,
    )
    run_one_round(
        agent, memory_manager, db, user_id, conv_id,
        "明白了。顺便提一下，我是这栋楼的物业经理，以后的报告必须控制在100字以内，并且语气要严厉。",
        2,
    )
    run_one_round(
        agent, memory_manager, db, user_id, conv_id,
        "现在帮我生成一份二号楼外墙脱落的巡检报告。",
        3,
    )

    db.close()
    print("\n测试脚本执行完毕。可查看 memory_test.db 中的 conversation_memories 表。")


if __name__ == "__main__":
    main()
