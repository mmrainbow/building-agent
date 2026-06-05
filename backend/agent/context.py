"""Agent 上下文构建 — System Prompt、消息组装、历史转换。"""

import re

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


# ── 辅助函数 ──────────────────────────────────────────────


def strip_base64_for_llm(text: str) -> str:
    """移除 base64 图片数据避免撑爆 LLM 上下文。"""
    return re.sub(r'data:image[^"\')\s]+', 'data:image/...', text)


def make_user_message(text: str, image_count: int = 0) -> dict:
    """构建发送给 LLM 的用户消息。"""
    if image_count == 1:
        prefix = "[用户已上传 1 张建筑图片，你可以调用 CV 工具来分析图片]\n\n"
    elif image_count > 1:
        prefix = f"[用户已上传 {image_count} 张建筑图片，编号为 图1~图{image_count}。调用 CV 工具时可通过 image_indices 参数指定分析哪些图片，如 image_indices=[1] 只分析图1，不填则分析全部]\n\n"
    else:
        prefix = ""
    return {"role": "user", "content": f"{prefix}{text}"}


def history_to_messages(records: list) -> list[dict]:
    """将 ChatMessage ORM 对象列表转为 LLM 消息格式。

    有图片的用户消息自动标注 [图片 N/M]，LLM 可以引用"图1""图2"等。
    tool 消息保留原 role，避免 LLM 重复调用已执行过的工具。
    """
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
