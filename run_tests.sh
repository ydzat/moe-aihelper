#!/bin/bash
###
 # @Author: @ydzat
 # @Date: 2025-02-02 01:26:02
 # @LastEditors: @ydzat
 # @LastEditTime: 2025-02-03 10:09:18
 # @Description: 自动运行核心并执行 pytest-asyncio 测试
###

conda_env="ai-core"
python_start_core="python -m core.main"
python_test="pytest test/test_integration.py::test_echo_workflow -v"

# 激活 conda 环境
conda init bash
source ~/.bashrc
conda activate $conda_env

# 🔄 先清理旧的 ZeroMQ 端口
echo "🔄 清理旧的 ZeroMQ 端口..."
pkill -f "$python_start_core"
sleep 2  # 确保端口释放

# 启动核心程序（让日志直接输出到终端）
echo "🚀 启动 core.main..."
$python_start_core &  # ✅ 这里不再使用 `nohup`，直接在后台运行 core.main

# 🔄 动态等待 core.main 启动
echo "⌛ 等待 core 系统启动..."
RETRIES=10
COUNT=0
while ! pgrep -f "$python_start_core" > /dev/null; do
    sleep 1
    COUNT=$((COUNT+1))
    if [ "$COUNT" -ge "$RETRIES" ]; then
        echo "❌ core.main 启动失败，测试无法进行"
        exit 1
    fi
done
echo "✅ core.main 已启动"

# 运行 pytest-asyncio 测试
echo "🔍 运行 pytest-asyncio 测试..."
$python_test

# 终止 core.main (确保只在测试结束后停止)
echo "🛑 终止 core.main..."
pkill -f "$python_start_core"
