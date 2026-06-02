"""本地 LLM 服务 — 将微调 Qwen2.5-VL 模型部署为 OpenAI 兼容 API (Windows 原生)。

用法:
    python scripts/launch_local_llm.py
    python scripts/launch_local_llm.py --port 8001
    python scripts/launch_local_llm.py --model ./qwen2_5_vl_3b_building_merged

端点:
    POST /v1/chat/completions   纯文本对话 (OpenAI 兼容)
    POST /v1/report             图片+结构化数据 → 巡检报告 (Report Agent)
    GET  /health                健康检查

环境变量:
    LOCAL_VL_MODEL_PATH     模型目录 (默认 ./qwen2_5_vl_3b_building_merged)
    LOCAL_VL_DEVICE_MAP     设备分配 (默认 auto)
    LOCAL_VL_TORCH_DTYPE    推理精度 (默认 float16)
    LOCAL_VL_MAX_NEW_TOKENS 最大生成长度 (默认 512)
"""

import argparse
import base64
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 在 import 本地模型之前设环境变量
MODEL_PATH = os.getenv(
    "LOCAL_VL_MODEL_PATH",
    str(PROJECT_ROOT / "qwen2_5_vl_3b_building_merged"),
)
os.environ["LOCAL_VL_MODEL_PATH"] = MODEL_PATH
os.environ["LOCAL_VL_MODEL_ENABLED"] = "true"

from llm.local_vl_model import get_local_vl_client


def build_app():
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    # ── 请求/响应模型 ──

    class ChatMessage(BaseModel):
        role: str
        content: str | None = None

    class ChatRequest(BaseModel):
        model: str = "qwen2.5-vl-building"
        messages: list[ChatMessage]
        temperature: float = 0.7
        max_tokens: int = 2000

    class ChatResponse(BaseModel):
        id: str
        object: str = "chat.completion"
        created: int
        model: str
        choices: list[dict]
        usage: dict

    class ReportRequest(BaseModel):
        images_base64: list[str] = []    # 多张图片 base64
        image_base64: str = ""           # 兼容单张
        material: str = "Unknown"
        floor: str = "Unknown"
        has_extension: str = "Unknown"
        defects: list[dict] = []

    class ReportResponse(BaseModel):
        report: str
        elapsed_seconds: float

    app = FastAPI(title="Local Qwen2.5-VL Report Agent")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        return {"status": "ok", "model_loaded": True}

    @app.post("/v1/chat/completions", response_model=ChatResponse)
    def chat_completions(req: ChatRequest):
        msgs = [m.model_dump() for m in req.messages]
        started_at = time.time()

        generated = get_local_vl_client().chat(
            messages=msgs,
            max_new_tokens=req.max_tokens,
            temperature=req.temperature,
        )

        elapsed = time.time() - started_at
        return ChatResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
            created=int(time.time()),
            model=req.model,
            choices=[{
                "index": 0,
                "message": {"role": "assistant", "content": generated},
                "finish_reason": "stop",
            }],
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "elapsed_seconds": round(elapsed, 2),
            },
        )

    @app.post("/v1/report", response_model=ReportResponse)
    def generate_report(req: ReportRequest):
        """Report Agent — 接收图片+结构化数据，返回专业巡检报告。支持单张/多张图片。"""
        started_at = time.time()

        # 确定图片列表：优先 images_base64，回退 image_base64
        images = req.images_base64 if req.images_base64 else ([req.image_base64] if req.image_base64 else [])
        if not images:
            return ReportResponse(report="错误: 未提供图片", elapsed_seconds=0)

        # 多图时使用第一张作为 VL 模型的视觉输入（代表性正面图）
        image_bytes = base64.b64decode(images[0])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            client = get_local_vl_client()

            # 多图时：构造增强 prompt，包含所有图片的编号信息
            if len(images) > 1:
                prompt = client._build_multi_image_prompt(
                    image_count=len(images),
                    material=req.material,
                    floor=req.floor,
                    has_extension=req.has_extension,
                    defects=req.defects,
                )
                report = client.generate(image_path=tmp_path, prompt=prompt)
            else:
                report = client.generate_report(
                    image_path=tmp_path,
                    material=req.material,
                    floor=req.floor,
                    has_extension=req.has_extension,
                    defects=req.defects,
                )
            elapsed = time.time() - started_at
            return ReportResponse(report=report, elapsed_seconds=round(elapsed, 2))
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    return app


def main():
    parser = argparse.ArgumentParser(description="本地 LLM OpenAI 兼容服务")
    parser.add_argument("--port", type=int, default=8000, help="API 端口 (默认: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址 (默认: 127.0.0.1)")
    parser.add_argument("--model", default=MODEL_PATH, help=f"模型路径 (默认: {MODEL_PATH})")
    args = parser.parse_args()

    if not Path(args.model).exists():
        print(f"[Server] 错误: 模型目录不存在: {args.model}")
        sys.exit(1)

    os.environ["LOCAL_VL_MODEL_PATH"] = args.model

    print(f"[Server] 模型路径: {args.model}")
    print(f"[Server] 正在加载模型...")

    import uvicorn

    # 预加载模型
    try:
        client = get_local_vl_client()
        client.load()
        print(f"[Server] 模型加载完成")
    except Exception as e:
        print(f"[Server] 模型加载失败: {e}")
        print("[Server] 将继续启动，首次请求时加载")

    print(f"[Server] 服务地址: http://{args.host}:{args.port}")
    print(f"[Server] Chat API: http://{args.host}:{args.port}/v1/chat/completions")

    app = build_app()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
