"""vLLM 启动脚本 — 将微调 Qwen2.5-VL 模型部署为 OpenAI 兼容 API。

用法:
    python scripts/launch_vllm.py                          # 默认配置
    python scripts/launch_vllm.py --port 8001              # 自定义端口
    python scripts/launch_vllm.py --disable-tool-calling   # 禁用原生 tool calling (使用 prompt 回退)

环境变量:
    LOCAL_VL_MODEL_PATH    微调 merged 模型目录 (默认 ./outputs/qwen2_5_vl_3b_building_merged)
    LOCAL_VL_DEVICE_MAP    模型设备分配 (默认 auto)
    LOCAL_VL_TORCH_DTYPE   推理精度 (默认 float16)

启动后访问 http://localhost:8000/v1/chat/completions 即可使用。
"""

import argparse
import os
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

MODEL_PATH = os.getenv(
    "LOCAL_VL_MODEL_PATH",
    str(PROJECT_ROOT / "outputs" / "qwen2_5_vl_3b_building_merged"),
)


def main():
    parser = argparse.ArgumentParser(description="vLLM 本地模型服务启动器")
    parser.add_argument("--model", default=MODEL_PATH, help=f"模型路径 (默认: {MODEL_PATH})")
    parser.add_argument("--port", type=int, default=8000, help="API 端口 (默认: 8000)")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址 (默认: 127.0.0.1)")
    parser.add_argument(
        "--served-model-name",
        default="qwen2.5-vl-building",
        help="API 中暴露的模型名 (默认: qwen2.5-vl-building)",
    )
    parser.add_argument(
        "--max-model-len",
        type=int,
        default=4096,
        help="最大上下文长度 (默认: 4096)",
    )
    parser.add_argument(
        "--gpu-memory-utilization",
        type=float,
        default=0.85,
        help="GPU 显存利用率 (默认: 0.85)",
    )
    parser.add_argument(
        "--dtype",
        default=os.getenv("LOCAL_VL_TORCH_DTYPE", "float16"),
        help="推理精度 (默认: float16)",
    )
    parser.add_argument(
        "--disable-tool-calling",
        action="store_true",
        help="禁用原生 function calling (降级为 prompt 解析模式)",
    )
    parser.add_argument(
        "--max-num-seqs",
        type=int,
        default=4,
        help="最大并发序列数 (默认: 4)",
    )

    args = parser.parse_args()

    if not Path(args.model).exists():
        print(f"[vLLM] 错误: 模型目录不存在: {args.model}")
        print("[vLLM] 请确认 LOCAL_VL_MODEL_PATH 环境变量或 --model 参数指向正确的 merged 模型目录。")
        sys.exit(1)

    print(f"[vLLM] 模型路径: {args.model}")
    print(f"[vLLM] 服务地址: http://{args.host}:{args.port}/v1")
    print(f"[vLLM] 模型名称: {args.served_model_name}")
    print(f"[vLLM] 推理精度: {args.dtype}")
    print(f"[vLLM] 最大上下文: {args.max_model_len}")
    print(f"[vLLM] GPU 显存利用: {args.gpu_memory_utilization}")
    print(f"[vLLM] Tool Calling: {'禁用 (prompt 回退模式)' if args.disable_tool_calling else '启用'}")

    # 构建 vLLM CLI 参数
    cmd_args = [
        "vllm", "serve", args.model,
        "--host", args.host,
        "--port", str(args.port),
        "--served-model-name", args.served_model_name,
        "--max-model-len", str(args.max_model_len),
        "--gpu-memory-utilization", str(args.gpu_memory_utilization),
        "--dtype", args.dtype,
        "--max-num-seqs", str(args.max_num_seqs),
    ]

    if args.disable_tool_calling:
        # vLLM 某些版本对 Qwen2.5-VL 的 tool calling 支持可能不完善
        # 此 flag 会关闭服务端的 tool calling 解析
        cmd_args.append("--enable-auto-tool-choice")
        cmd_args.append("--tool-call-parser")
        cmd_args.append("hermes")  # 或 "qwen2.5" 取决于版本

    print(f"\n[vLLM] 执行命令: {' '.join(cmd_args)}\n")

    # 通过 subprocess 调用 vllm CLI
    import subprocess
    try:
        subprocess.run(cmd_args, check=True)
    except KeyboardInterrupt:
        print("\n[vLLM] 服务已停止。")
    except subprocess.CalledProcessError as e:
        print(f"\n[vLLM] 启动失败: {e}")
        print("[vLLM] 提示:")
        print("  1. 确认已安装 vllm: pip install vllm")
        print("  2. 确认 CUDA 可用: python -c 'import torch; print(torch.cuda.is_available())'")
        print("  3. 如需禁用 tool calling: python scripts/launch_vllm.py --disable-tool-calling")
        sys.exit(1)


if __name__ == "__main__":
    main()
