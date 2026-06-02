@echo off
REM vLLM 本地模型服务启动器 (Windows)
REM 启动前请确认:
REM   1. pip install vllm 已完成
REM   2. CUDA 可用: python -c "import torch; print(torch.cuda.is_available())"
REM   3. 模型目录存在: outputs\qwen2_5_vl_3b_building_merged

echo ========================================
echo   vLLM 本地模型服务启动器
echo ========================================
echo.

REM 检查模型目录
if not exist "outputs\qwen2_5_vl_3b_building_merged" (
    echo [错误] 模型目录不存在: outputs\qwen2_5_vl_3b_building_merged
    echo 请确认微调 merged 模型已放置在正确位置。
    pause
    exit /b 1
)

REM 设置默认环境变量 (如未设置)
if "%LOCAL_VL_MODEL_ENABLED%"=="" set LOCAL_VL_MODEL_ENABLED=true
if "%LOCAL_VL_MODEL_PATH%"=="" set LOCAL_VL_MODEL_PATH=./outputs/qwen2_5_vl_3b_building_merged
if "%LOCAL_VL_DEVICE_MAP%"=="" set LOCAL_VL_DEVICE_MAP=auto
if "%LOCAL_VL_TORCH_DTYPE%"=="" set LOCAL_VL_TORCH_DTYPE=float16
if "%LOCAL_VL_MAX_NEW_TOKENS%"=="" set LOCAL_VL_MAX_NEW_TOKENS=512

echo 模型路径: %LOCAL_VL_MODEL_PATH%
echo 推理精度: %LOCAL_VL_TORCH_DTYPE%
echo 服务端口: 8000
echo.

echo 正在启动 vLLM 服务...
echo API 地址: http://localhost:8000/v1/chat/completions
echo.

python scripts/launch_vllm.py %*

pause
