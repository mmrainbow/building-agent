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
import time
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any

from agent.memory_manager import MemoryManager
from llm.tools import execute_tool, get_tool_schemas

# ── System Prompt ─────────────────────────────────────────

SYSTEM_PROMPT = """你是建筑外立面巡检 Manager Agent，负责协调多个专业工具完成巡检任务。

## ⚠️ 核心判断（最高优先级，每次回复前先判断）

**第一步 — 判断问题类型：**
- **闲聊类**（打招呼、自我介绍、"你是谁"、"你会什么"、天气等与巡检无关的话题）
  → **直接文字回复，不调用任何工具，立即结束，不要思考要不要调工具！**
- **巡检类**（材质、楼层、隐患、报告等建筑检测相关）
  → 用户有上传图片时才调工具；没图片则提示上传

## 你的团队（仅在巡检时使用）

**CV 检测工具:**
- classify_material  — 识别外墙材质
- estimate_floors    — 估算楼层数
- detect_extension   — 检测屋顶违建加层
- detect_defects     — 检测外墙隐患（空鼓/渗水/脱落/裂缝）
- search_knowledge   — 检索建筑规范

**报告工具:**
- generate_report    — 委托 Report Agent 生成正式报告（仅"全面检测"/"出报告"时调用）

## 决策示例（严格遵循）
  用户:"你好" → **不调任何工具**，直接回"你好！我是建筑外立面巡检助手..."
  用户:"介绍一下你自己" → **不调任何工具**，直接介绍
  用户:"今天天气怎么样" → **不调任何工具**，直接回"抱歉，我是巡检助手，无法查天气"
  用户:"这栋楼是什么材质"（有图）→ 调 classify_material
  用户:"这栋楼是什么材质"（无图）→ 提示"请先上传建筑图片"
  用户:"全面检测这栋楼"（有图）→ 调 CV 工具 + generate_report

## 铁律
1. 闲聊/介绍/非巡检问题 → 秒回文字，**严禁调用任何工具**
2. 巡检但无图 → 提示上传，不调工具
3. 巡检有图 → 按需调用，不全调
4. 中文回复，简洁专业"""

# ── Message 构建辅助函数 ──────────────────────────────────


def _make_user_message(text: str, image_count: int = 0) -> dict:
    """构建发送给 LLM 的用户消息。"""
    if image_count == 1:
        prefix = "[用户已上传 1 张建筑图片，你可以调用 CV 工具来分析图片]\n\n"
    elif image_count > 1:
        prefix = f"[用户已上传 {image_count} 张建筑图片，编号为 图1~图{image_count}。调用 CV 工具时可通过 image_indices 参数指定分析哪些图片，如 image_indices=[1] 只分析图1，不填则分析全部]\n\n"
    else:
        prefix = ""
    return {"role": "user", "content": f"{prefix}{text}"}


def _history_to_messages(records: list) -> list[dict]:
    """将 ChatMessage ORM 对象列表转为 LLM 消息格式。

    有图片的用户消息自动标注 [图片 N/M]，LLM 可以引用"图1""图2"等。
    tool 消息保留原 role，避免 LLM 重复调用已执行过的工具。
    """
    # 预先统计所有带图片的用户消息，计算序号
    img_indices: dict[int, int] = {}
    counter = 0
    for r in records:
        if r.role == "user" and (r.metadata_ or {}).get("has_image"):
            counter += 1
            img_indices[r.id] = counter

    msgs = []
    for r in records:
        content = r.content or ""
        if len(content) > 2000:
            content = content[:2000] + "..."
        idx = img_indices.get(r.id)
        if idx is not None:
            img_id = (r.metadata_ or {}).get("chat_image_id", "?")
            content = f"[图片 #{img_id} ({idx}/{counter})] {content}"
        msgs.append({"role": r.role, "content": content})
    return msgs


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
            messages.extend(_history_to_messages(recent_messages))

        image_count = len(images) if images else 0
        messages.append(_make_user_message(message, image_count=image_count))

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
                        "content": result[:2000],
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

        # 4. 持久化短期记忆，并提炼长期记忆
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
