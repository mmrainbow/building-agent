"""Predictor → OpenAI Function Call Tool 封装。

每个 Tool 的输出会被 LLM 阅读并用于生成巡检报告，因此返回值统一为中文可读文本。

延迟加载: CV Predictor 只在首次调用时加载模型权重，避免 import 时依赖 torch。
"""

import json
import os
from pathlib import Path
from typing import Any

# ── Tool Schema 定义（OpenAI function call 格式）─────────────

# 4 个 CV Tool 无显式参数 —— 图像由 orchestrator 在处理时注入
MATERIAL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "classify_material",
        "description": "识别建筑外墙材质类型。返回列表如 Face Brick(面砖)、Coating(涂料)、Stone Hanging(石材干挂)、Glass Curtain Wall(玻璃幕墙)、Aluminum Plate(铝板)、Real Stone Paint(真石漆)等。",
        "parameters": {"type": "object", "properties": {}},
    },
}

FLOOR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "estimate_floors",
        "description": "基于建筑外立面窗户排列估算楼层数量。返回如'5层'。",
        "parameters": {"type": "object", "properties": {}},
    },
}

EXTENSION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "detect_extension",
        "description": "检测建筑是否存在违建加层（屋顶私自加盖）。返回'有加层'或'无加层'。",
        "parameters": {"type": "object", "properties": {}},
    },
}

DEFECT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "detect_defects",
        "description": "检测建筑外墙隐患，包括空鼓、渗水、脱落、裂缝四种类型。返回隐患列表，每项含编号(id)、类型(type)、面积(area)、坐标框(box)。",
        "parameters": {"type": "object", "properties": {}},
    },
}

KNOWLEDGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_knowledge",
        "description": "检索建筑规范、巡检标准、缺陷判定阈值、常见处理方法等相关知识。用于辅助生成专业报告。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索关键词或问题，如'面砖脱落原因分析'、'裂缝宽度危险标准'、'外墙渗水处理方案'",
                }
            },
            "required": ["query"],
        },
    },
}


# ── Tool 实现 ──────────────────────────────────────────────


class CVToolWrapper:
    """将 BasePredictor 子类包装为 OpenAI Tool。

    延迟加载 — 首次调用 execute() 时才加载模型权重。
    """

    def __init__(self, schema: dict, predictor_factory: callable):
        self.schema = schema
        self._predictor = None
        self._factory = predictor_factory

    def _ensure_loaded(self):
        if self._predictor is None:
            self._predictor = self._factory()

    def execute(self, image=None, **kwargs) -> str:
        """执行推理，返回中文可读文本结果。"""
        if image is None:
            return "错误：需要图片输入，但当前未提供图片。"
        self._ensure_loaded()
        try:
            result = self._predictor.predict([image])
            value = result[0] if result else None
            return self._format_output(value)
        except Exception as e:
            return f"推理失败: {e}"

    def _format_output(self, value):
        """子类可覆盖以定制输出格式。"""
        if value is None:
            return "未识别出结果。"
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=False)
        return str(value)


class DefectToolWrapper(CVToolWrapper):
    """隐患检测专用 — 输出包含中文类型名和面积信息。"""

    def _format_output(self, value):
        if not value:
            return "未检测到明显隐患。"
        items = []
        for d in value:
            items.append(
                f"隐患#{d.get('id', '?')}: {d.get('type', '未知')} "
                f"(面积: {d.get('area', 0):.0f}px²)"
            )
        return "检测到 {} 处隐患:\n{}".format(len(items), "\n".join(items))


class KnowledgeSearchTool:
    """建筑规范知识检索 Tool — ChromaDB 语义检索 + SQLite 用户记忆回退。

    优先从 ChromaDB 检索建筑规范条文（agent/rag.py），
    向量库不可用时回退到用户长期记忆（conversation_memories）。
    """

    @property
    def schema(self):
        return KNOWLEDGE_SCHEMA

    def execute(self, query=None, user_id=None, image=None, **kwargs) -> str:
        if not query:
            return "错误：请提供检索关键词。"

        # 优先: ChromaDB 建筑规范检索
        try:
            from agent.rag import search_regulations

            regs = search_regulations(query, k=5)
            if regs:
                return f"📋 建筑规范条文:\n\n{regs}"
        except Exception as e:
            print(f"[KnowledgeSearch] ChromaDB 检索异常: {e}")

        # 回退: 用户长期记忆
        try:
            from db import SessionLocal, search_memories_by_keyword

            db = SessionLocal()
            try:
                results = search_memories_by_keyword(
                    db, user_id or 0, query, limit=5
                )
                if results:
                    items = [
                        f"- [{m.memory_type}] {m.content[:200]}" for m in results
                    ]
                    return "💾 用户记忆（规范库不可用时的回退）:\n" + "\n".join(items)
            finally:
                db.close()
        except Exception:
            pass

        return f"未找到与'{query}'相关的规范或记忆。"


REPORT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_report",
        "description": (
            "调用本地专业报告 Agent（微调 Qwen2.5-VL 模型）生成正式建筑巡检报告。"
            "当你已完成所需检测工具调用、收集了足够数据后，应调用此工具来生成专业报告。"
            "Report Agent 能生成比你自己写更专业、更符合住建规范的报告。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "material": {
                    "type": "string",
                    "description": "材质检测结果，如'面砖'、'涂料'",
                },
                "floor": {
                    "type": "string",
                    "description": "楼层检测结果，如'18层'",
                },
                "has_extension": {
                    "type": "string",
                    "description": "加层检测结果，如'有加层'或'无加层'",
                },
                "defects_summary": {
                    "type": "string",
                    "description": "隐患检测结果摘要，简述检测到的缺陷类型和数量",
                },
            },
            "required": [],
        },
    },
}


class ReportAgentTool:
    """Report Agent Tool — 将检测结果和图片发送给本地 Report Agent 生成专业报告。

    通过 HTTP POST 调用 localhost 上运行的 Report Agent 服务。
    """

    def __init__(self, report_agent_url: str | None = None):
        self.url = (report_agent_url or os.getenv("REPORT_AGENT_URL", "http://localhost:8000")).rstrip("/")

    @property
    def schema(self):
        return REPORT_SCHEMA

    def execute(self, image=None, material="", floor="", has_extension="", defects_summary="", **kwargs) -> str:
        if image is None:
            return "错误：需要图片才能生成报告。请先确保用户已上传图片。"

        import base64
        import tempfile

        # 编码图片为 base64
        _, buf = __import__("cv2").imencode(".jpg", image)
        image_b64 = base64.b64encode(buf.tobytes()).decode("utf-8")

        payload = {
            "image_base64": image_b64,
            "material": material or "Unknown",
            "floor": floor or "Unknown",
            "has_extension": has_extension or "Unknown",
            "defects": [],  # defects_summary 是文本摘要，不是原始缺陷列表
        }

        try:
            resp = __import__("requests").post(
                f"{self.url}/v1/report",
                json=payload,
                timeout=120,
            )
            if resp.status_code == 200:
                data = resp.json()
                elapsed = data.get("elapsed_seconds", 0)
                return f"📋 **专业巡检报告** (生成耗时 {elapsed:.1f}s):\n\n{data['report']}"
            return f"Report Agent 调用失败: HTTP {resp.status_code}"
        except Exception as e:
            return f"Report Agent 不可达 ({self.url}): {e}"


# ── Tool 构建工厂 ──────────────────────────────────────────


MODEL_DIR = Path(__file__).parent.parent / "model_weights"


def build_tools(model_dir: str | None = None) -> dict[str, Any]:
    """构建所有可用 Tool，返回 {tool_name: tool_instance}。

    CV Predictor 使用延迟加载，仅在首次被 LLM 调用时初始化。
    """
    if model_dir is None:
        model_dir = str(MODEL_DIR)

    return {
        "classify_material": CVToolWrapper(
            schema=MATERIAL_SCHEMA,
            predictor_factory=lambda: _make_material_predictor(model_dir),
        ),
        "estimate_floors": CVToolWrapper(
            schema=FLOOR_SCHEMA,
            predictor_factory=lambda: _make_floor_predictor(model_dir),
        ),
        "detect_extension": CVToolWrapper(
            schema=EXTENSION_SCHEMA,
            predictor_factory=lambda: _make_extension_predictor(model_dir),
        ),
        "detect_defects": DefectToolWrapper(
            schema=DEFECT_SCHEMA,
            predictor_factory=lambda: _make_defect_predictor(model_dir),
        ),
        "search_knowledge": KnowledgeSearchTool(),
        "generate_report": ReportAgentTool(),
    }


def get_tool_schemas(tools: dict) -> list[dict]:
    """提取所有 Tool 的 OpenAI schema，传给 LLM chat() 的 tools 参数。"""
    return [t.schema for t in tools.values()]


def execute_tool(tools: dict, name: str, image=None, **kwargs) -> str:
    """根据名称执行 Tool，返回结果字符串。"""
    if name not in tools:
        return f"未知工具 '{name}'，可用: {', '.join(tools.keys())}"
    tool = tools[name]
    return tool.execute(image=image, **kwargs)


def format_tool_result_for_llm(tool_name: str, result: str) -> str:
    """将 Tool 执行结果包装为 LLM 可读的消息内容。"""
    return result


# ── Predictor 工厂函数（延迟 import）────────────────────────


def _make_material_predictor(model_dir: str):
    from predictors.material import MaterialPredictor

    return MaterialPredictor(os.path.join(model_dir, "material.pth"))


def _make_floor_predictor(model_dir: str):
    from predictors.floor import FloorPredictor

    return FloorPredictor(
        os.path.join(model_dir, "main_building.pt"),
        os.path.join(model_dir, "outer_obj.pt"),
    )


def _make_extension_predictor(model_dir: str):
    from predictors.added_floor import AddedFloorPredictor

    return AddedFloorPredictor(os.path.join(model_dir, "add_predict.pth"))


def _make_defect_predictor(model_dir: str):
    from predictors.hidden_danger import HiddenDangerPredictor

    return HiddenDangerPredictor(os.path.join(model_dir, "best.pt"))
