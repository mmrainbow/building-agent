"""ReAct Agent 编排器 — Manager Agent + Memory Agent 协同。

核心流程:
    context → [LLM ⇄ Tool] 循环 → _save_turn → Memory Agent 提取记忆 → 返回结果

Manager Agent (self.llm): 通义千问 qwen3.6-flash — 推理 + 工具调度
Memory Agent:            通义千问 qwen-turbo   — 自动提取长期记忆
Report Agent:            本地 Qwen2.5-VL       — generate_report 工具调用

依赖:
    llm/client.py       → LLMClient (OpenAI 兼容)
    llm/memory_agent.py → get_memory_agent()
    llm/tools.py        → build_tools, get_tool_schemas, execute_tool
    db/chat_crud.py     → Conversation + ChatMessage CRUD
"""

import json
import os
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from agent.context import (
    SYSTEM_PROMPT,
    history_to_messages,
    make_user_message,
    strip_base64_for_llm,
)
from agent.memory_manager import MemoryManager
from llm.tools import execute_tool, get_tool_schemas


# ── Agent ─────────────────────────────────────────────────


class ManagerAgent:
    """Manager Agent — ReAct 推理 + 工具调度。

    用法:
        from llm.client import LLMClient
        from llm.tools import build_tools

        llm = LLMClient(api_key="sk-xxx")
        agent = ManagerAgent(llm)
        agent.tools = build_tools()

        result = agent.run(
            user_id=1,
            conversation_id=conv.id,
            message="这栋楼有什么安全隐患？",
            image=cv2_image,       # numpy ndarray, 可选
            db=db_session,
            # recent_messages / memories 省略时自动 build_context
        )
        # result["response"]   → AI 文本回复
        # result["tool_log"]   → [{name, args, result, elapsed_ms}, ...]
    """

    def __init__(self, llm_client: Any, max_rounds: int = 10):
        self.llm = llm_client
        self.tools: dict[str, Any] = {}
        self.max_rounds = max_rounds
        self._tool_schemas: list[dict] | None = None
        self.memory_manager = MemoryManager()

    @property
    def tool_schemas(self) -> list[dict]:
        if self._tool_schemas is None and self.tools:
            self._tool_schemas = get_tool_schemas(self.tools)
        return self._tool_schemas or []

    def run(
        self,
        user_id: int,
        conversation_id: int,
        message: str,
        db: Any,
        images=None,
        image_blobs: list[bytes] | None = None,
        recent_messages: list | None = None,
        memories: list | None = None,
        on_step: Callable | None = None,
    ) -> dict:
        """执行一次完整的 Agent 对话轮次。

        Args:
            user_id: 用户 ID
            conversation_id: 对话会话 ID
            message: 用户输入文本
            db: SQLAlchemy Session
            images: 可选的 numpy 图像数组列表（多图支持）
            image_blobs: JPEG 字节列表，与 images 一一对应
            recent_messages: 最近历史消息；为 None 时由 build_context 自动拉取
            memories: 长期记忆；为 None 时由 build_context 自动拉取

        Returns:
            {
                "response": str,          # AI 文本回复
                "tool_log": list[dict],   # 工具调用记录
                "rounds": int,            # ReAct 循环轮数
                "usage": dict,            # token 用量总计
            }
        """
        # 1. 聊前上下文（未传入时隐式组装）
        if recent_messages is None or memories is None:
            ctx = self.memory_manager.build_context(
                db, user_id, conversation_id, message
            )
            if recent_messages is None:
                recent_messages = ctx["recent_messages"]
            if memories is None:
                memories = ctx["memories"]

        # 2. 组装消息列表
        system_content = SYSTEM_PROMPT
        if memories:
            mem_text = "## 历史相关记忆\n" + "\n".join(
                f"- [{m.memory_type}] {m.content}" for m in memories[:5]
            )
            system_content = f"{SYSTEM_PROMPT}\n\n{mem_text}"

        messages = [{"role": "system", "content": system_content}]

        if recent_messages:
            messages.extend(history_to_messages(recent_messages))

        image_count = len(images) if images else 0
        messages.append(make_user_message(message, image_count=image_count))

        # 预创建 ChatImage，tool 执行时可直接关联缺陷
        _chat_image_ids: list[int] = []
        _user_msg_id: int | None = None
        if image_blobs:
            from db.models import ChatMessage as CM, ChatImage as CI
            _user_msg = CM(
                conversation_id=conversation_id,
                role="user",
                content=message,
                metadata_={"has_image": True, "image_count": len(image_blobs)},
            )
            db.add(_user_msg)
            db.flush()
            _user_msg_id = _user_msg.id
            _chat_image_ids = []
            for blob in image_blobs:
                _pre_img = CI(message_id=_user_msg.id, data=blob)
                db.add(_pre_img)
                db.flush()
                _chat_image_ids.append(_pre_img.id)
            _user_msg.metadata_["chat_image_ids"] = _chat_image_ids
            db.flush()

        # 3. ReAct 循环
        tool_log = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        final_text = ""

        for round_idx in range(self.max_rounds):
            resp = self.llm.chat(messages, tools=self.tool_schemas)

            # 累加 token 用量
            for k in total_usage:
                total_usage[k] += resp.get("usage", {}).get(k, 0)

            if on_step:
                on_step({"type": "think", "round": round_idx + 1, "content": resp.get("content") or "分析中..."})

            if resp["tool_calls"]:
                # LLM 决定调用工具 → 执行并反馈结果
                assistant_msg = {
                    "role": "assistant",
                    "content": resp["content"],
                    "tool_calls": resp["tool_calls"],
                }
                messages.append(assistant_msg)

                for tc in resp["tool_calls"]:
                    fn_name = tc["function"]["name"]
                    try:
                        fn_args = json.loads(tc["function"]["arguments"])
                    except (json.JSONDecodeError, KeyError):
                        fn_args = {}

                    t_start = time.perf_counter()
                    if on_step:
                        on_step({"type": "tool", "name": fn_name, "status": "running"})
                    result = execute_tool(
                        self.tools, fn_name, images=images, db=db,
                        chat_image_ids=_chat_image_ids, user_id=str(user_id), **fn_args
                    )
                    elapsed_ms = round((time.perf_counter() - t_start) * 1000)
                    if on_step:
                        on_step({"type": "tool", "name": fn_name, "status": "done", "elapsed_ms": elapsed_ms})

                    tool_log.append({
                        "name": fn_name,
                        "arguments": fn_args,
                        "result": result[:1000],  # 截断，避免撑爆上下文
                        "elapsed_ms": elapsed_ms,
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": strip_base64_for_llm(result[:3000]),
                    })
            else:
                # LLM 生成最终文本回复
                final_text = resp.get("content") or ""
                if on_step:
                    on_step({"type": "done", "rounds": len(tool_log)})
                break
        else:
            # 达到最大循环次数 → 强制 LLM 生成总结
            messages.append({
                "role": "user",
                "content": "请基于以上工具返回的数据，生成巡检报告。",
            })
            final_resp = self.llm.chat(messages)
            final_text = final_resp.get("content") or "无法生成报告。"

        # 4. 从 generate_report 工具结果中提取标注图注入到最终回复
        for tl in tool_log:
            if tl["name"] == "generate_report":
                imgs = re.findall(r'<img[^>]+src="data:image[^"]+"[^>]*>', tl["result"])
                if imgs:
                    final_text = "\n".join(imgs) + "\n\n" + final_text
                break

        # 5. 持久化短期记忆，并提炼长期记忆
        self._save_turn(db, conversation_id, message, final_text, tool_log,
                        user_msg_id=_user_msg_id)
        self._extract_memory(db, user_id, conversation_id)

        return {
            "response": final_text,
            "tool_log": tool_log,
            "rounds": len(tool_log),
            "usage": total_usage,
        }

    # ── 持久化 ──────────────────────────────────────────

    def _save_turn(
        self,
        db: Any,
        conversation_id: int,
        user_msg: str,
        assistant_msg: str,
        tool_log: list[dict],
        user_msg_id: int | None = None,
    ) -> None:
        """保存本轮对话到 ChatMessage 表。user_msg_id 非空时跳过用户消息创建。"""
        if user_msg_id:
            # 用户消息+图片已预创建，更新消息计数
            from db.models import Conversation
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if conv:
                conv.message_count = (conv.message_count or 0) + 2  # user + assistant
                db.commit()
        else:
            from db.chat_crud import add_message
            add_message(db, conversation_id, "user", user_msg)
        if assistant_msg:
            from db.chat_crud import add_message
            meta = {"tool_calls": tool_log} if tool_log else None
            add_message(
                db,
                conversation_id,
                "assistant",
                assistant_msg,
                metadata=meta,
            )

    def _extract_memory(self, db: Any, user_id: int, conversation_id: int) -> None:
        """上下文 Token 管理 — 仅在接近窗口上限时触发 Memory Agent 压缩提取。"""
        from db.chat_crud import get_recent_messages
        from llm.memory_agent import get_memory_agent

        recent = get_recent_messages(db, conversation_id, limit=50)
        if len(recent) < 3:
            return

        # 估算当前上下文大小 (1 中文字符 ≈ 1.5 tokens)
        total_chars = sum(len(getattr(m, "content", "") or "") for m in recent)
        threshold = int(os.getenv("MEMORY_EXTRACT_THRESHOLD", "6000"))

        if total_chars < threshold:
            return  # 未达阈值，跳过提取

        memory_llm = get_memory_agent()
        self.memory_manager.extract_and_save_memory(
            db, user_id, conversation_id, memory_llm, recent
        )
