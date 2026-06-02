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
import time
from datetime import datetime, timezone
from typing import Any

from agent.memory_manager import MemoryManager
from llm.tools import execute_tool, get_tool_schemas

# ── System Prompt ─────────────────────────────────────────

SYSTEM_PROMPT = """你是建筑外立面巡检 Manager Agent，负责协调多个专业工具完成巡检任务。你的角色是管理者，而不是报告撰写者。

## 你的团队
你管理以下工具，根据任务需求自主调度:

**CV 检测工具 (本地运行):**
- classify_material  — 识别外墙材质（面砖/涂料/石材干挂/玻璃幕墙/铝板/真石漆等）
- estimate_floors    — 估算楼层数
- detect_extension   — 检测屋顶违建加层
- detect_defects     — 检测外墙隐患（空鼓/渗水/脱落/裂缝），含面积和位置
- search_knowledge   — 检索建筑规范、缺陷判定标准、处理方法

**报告生成工具:**
- generate_report    — ⚠️ 调用本地专业 Report Agent（微调模型）生成正式巡检报告。
  重要: 当用户要求"全面巡检"、"生成报告"、"出报告"时，你必须在收集完检测数据后调用此工具，
  而不是自己写报告。Report Agent 能生成更专业、更符合住建规范的正式报告。

## 什么时候调用 generate_report（重要！）
generate_report 会启动本地 Report Agent 生成完整报告，耗时较长。只在以下场景调用:
✅ 用户说"全面检测"/"巡检"/"出报告"/"生成报告"
✅ 用户要求正式的书面巡检结果
❌ 简单问答、闲聊、单一检测 — 你直接回答即可，不需要报告

示例:
  用户:"你好" → 直接回复，不调任何工具
  用户:"这栋楼是什么材质" → 调 classify_material → 回复"这是面砖外墙"，不调 generate_report
  用户:"有没有裂缝" → 调 detect_defects → 回复"检测到2处裂缝…"，不调 generate_report
  用户:"全面检测这栋楼" → 调 classify_material + detect_defects + detect_extension → 最后调 generate_report
  用户:"帮我出份报告" → 如果之前已检测过，直接调 generate_report；否则先检测再报告

## 工作原则
1. 根据用户问题判断需要哪些工具，不要全部调用
2. 简单问题直接回答，不需要报告
3. 发现隐患时可查 search_knowledge 获取规范依据
4. 工具返回的是真实数据，不要编造

## 输出格式
- 使用中文，专业但易于理解
- 简单问答直接回复；正式报告委托 generate_report
- 每个发现标注来源工具"""

# ── Message 构建辅助函数 ──────────────────────────────────


def _make_user_message(text: str, has_image: bool = False) -> dict:
    """构建发送给 LLM 的用户消息。"""
    if has_image:
        content = (
            f"[用户已上传建筑图片，你可以调用 CV 工具来分析图片]\n\n{text}"
        )
    else:
        content = text
    return {"role": "user", "content": content}


def _history_to_messages(records: list) -> list[dict]:
    """将 ChatMessage ORM 对象列表转为 LLM 消息格式。

    tool 消息保留原 role，LLM 能区分"用户说了什么"和"工具返回了什么"，
    避免 LLM 在后续轮次重复调用已执行过的工具。
    """
    msgs = []
    for r in records:
        content = r.content or ""
        if len(content) > 2000:
            content = content[:2000] + "..."
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
        image=None,
        image_blob: bytes | None = None,
        recent_messages: list | None = None,
        memories: list | None = None,
    ) -> dict:
        """执行一次完整的 Agent 对话轮次。

        Args:
            user_id: 用户 ID
            conversation_id: 对话会话 ID
            message: 用户输入文本
            db: SQLAlchemy Session
            image: 可选的 numpy 图像数组
            image_blob: JPEG 字节，持久化到 chat_images 表
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

        messages.append(_make_user_message(message, has_image=image is not None))

        # 预创建 ChatImage，tool 执行时可直接关联缺陷
        _chat_image_id = None
        if image_blob:
            from db.models import ChatMessage as CM, ChatImage as CI
            _pre_msg = CM(conversation_id=conversation_id, role="user", content=f"[图片] {message[:50]}")
            db.add(_pre_msg)
            db.flush()
            _pre_img = CI(message_id=_pre_msg.id, data=image_blob)
            db.add(_pre_img)
            db.flush()
            _chat_image_id = _pre_img.id

        # 3. ReAct 循环
        tool_log = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        final_text = ""

        for round_idx in range(self.max_rounds):
            resp = self.llm.chat(messages, tools=self.tool_schemas)

            # 累加 token 用量
            for k in total_usage:
                total_usage[k] += resp.get("usage", {}).get(k, 0)

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
                    result = execute_tool(
                        self.tools, fn_name, image=image, db=db,
                        chat_image_id=_chat_image_id, user_id=str(user_id), **fn_args
                    )
                    elapsed_ms = round((time.perf_counter() - t_start) * 1000)

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
        # 已预创建 ChatImage，不再重复保存
        self._save_turn(db, conversation_id, message, final_text, tool_log, None)
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
        user_image_blob: bytes | None = None,
    ) -> None:
        """保存本轮对话到 ChatMessage 表。"""
        from db.chat_crud import add_message

        add_message(db, conversation_id, "user", user_msg, image_blob=user_image_blob)
        if assistant_msg:
            meta = {"tool_calls": tool_log} if tool_log else None
            add_message(
                db,
                conversation_id,
                "assistant",
                assistant_msg,
                metadata=meta,
            )

    def _extract_memory(self, db: Any, user_id: int, conversation_id: int) -> None:
        """ReAct 落库后，用 Memory Agent (独立廉价模型) 提炼长期记忆。"""
        from db.chat_crud import get_recent_messages
        from llm.memory_agent import get_memory_agent

        recent = get_recent_messages(db, conversation_id, limit=20)
        memory_llm = get_memory_agent()
        self.memory_manager.extract_and_save_memory(
            db, user_id, conversation_id, memory_llm, recent
        )
