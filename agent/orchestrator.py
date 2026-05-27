"""ReAct Agent 编排器 — LLM 自主选择 Tool 执行建筑巡检。

核心流程:
    context → [LLM ⇄ Tool] 循环 → 保存消息 → 提取记忆 → 返回结果

依赖:
    llm/client.py   → LLMClient (通义千问 API)
    llm/tools.py    → build_tools, get_tool_schemas, execute_tool
    db/chat_crud.py → Conversation + ChatMessage CRUD
"""

import json
import time
from datetime import datetime, timezone
from typing import Any

from llm.tools import execute_tool, get_tool_schemas

# ── System Prompt ─────────────────────────────────────────

SYSTEM_PROMPT = """你是建筑外立面巡检专家 AI，协助住建管理人员分析建筑图片并生成巡检报告。

## 可用工具
- classify_material  — 识别外墙材质（面砖/涂料/石材干挂/玻璃幕墙/铝板/真石漆等）
- estimate_floors    — 基于窗户排列估算楼层数
- detect_extension   — 检测是否存在屋顶违建加层
- detect_defects     — 检测外墙隐患（空鼓/渗水/脱落/裂缝），含面积和位置
- search_knowledge   — 检索建筑规范、缺陷判定标准、处理方法

## 工作原则
1. 根据用户问题自主判断需要调用哪些工具，**不一定要全部调用**
2. 如用户只问材质 → 只需 classify_material；问隐患 → 只需 detect_defects
3. 如用户问"有什么问题"或"全面巡检" → 调用材质+隐患+加层
4. 发现隐患时优先查 search_knowledge 获取规范依据和处置建议
5. 工具返回的数据是真实的检测结果，不要猜测或编造

## 输出格式
- 使用中文，专业但易于理解
- 结构化输出：先总览，再分项说明
- 每个发现标注来源工具
- 隐患描述包含类型、大致面积
- 如有规范引用，注明出处"""

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
    """将 ChatMessage ORM 对象列表转为 LLM 消息格式。"""
    msgs = []
    for r in records:
        role = r.role if r.role != "tool" else "user"  # tool 消息折叠到 user 上下文
        content = r.content or ""
        # 截断过长消息，保持上下文在 token 限制内
        if len(content) > 2000:
            content = content[:2000] + "..."
        msgs.append({"role": role, "content": content})
    return msgs


# ── Agent ─────────────────────────────────────────────────


class InspectionAgent:
    """建筑巡检 ReAct Agent。

    用法:
        from llm.client import LLMClient
        from llm.tools import build_tools

        llm = LLMClient(api_key="sk-xxx")
        agent = InspectionAgent(llm)
        agent.tools = build_tools()

        result = agent.run(
            user_id=1,
            conversation_id=conv.id,
            message="这栋楼有什么安全隐患？",
            image=cv2_image,       # numpy ndarray, 可选
            db=db_session,
        )
        # result["response"]   → AI 文本回复
        # result["tool_log"]   → [{name, args, result, elapsed_ms}, ...]
    """

    def __init__(self, llm_client: Any, max_rounds: int = 10):
        self.llm = llm_client
        self.tools: dict[str, Any] = {}
        self.max_rounds = max_rounds
        self._tool_schemas: list[dict] | None = None

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
            recent_messages: 最近历史消息列表 (ChatMessage ORM 对象)
            memories: 长期记忆列表 (ConversationMemory ORM 对象)

        Returns:
            {
                "response": str,          # AI 文本回复
                "tool_log": list[dict],   # 工具调用记录
                "rounds": int,            # ReAct 循环轮数
                "usage": dict,            # token 用量总计
            }
        """
        # 1. 组装消息列表
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # 注入长期记忆
        if memories:
            mem_text = "## 历史相关记忆\n" + "\n".join(
                f"- [{m.memory_type}] {m.content}" for m in memories[:5]
            )
            messages.append({"role": "system", "content": mem_text})

        # 注入近期对话历史
        if recent_messages:
            messages.extend(_history_to_messages(recent_messages))

        # 注入当前用户消息
        messages.append(_make_user_message(message, has_image=image is not None))

        # 2. ReAct 循环
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
                        self.tools, fn_name, image=image, **fn_args
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

        # 3. 持久化消息
        self._save_turn(db, conversation_id, message, final_text, tool_log)

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
    ) -> None:
        """保存本轮对话到 ChatMessage 表。"""
        from db.chat_crud import add_message

        add_message(db, conversation_id, "user", user_msg)
        if assistant_msg:
            meta = {"tool_calls": tool_log} if tool_log else None
            add_message(
                db,
                conversation_id,
                "assistant",
                assistant_msg,
                metadata=meta,
            )
