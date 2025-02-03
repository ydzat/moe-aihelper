"""
Author: @ydzat
Date: 2025-02-03 19:57:12
LastEditors: @ydzat
LastEditTime: 2025-02-03 20:00:37
Description:
"""

import sys
import asyncio
import pytest
import logging
from pathlib import Path

# **手动添加 core 目录到 Python 路径**
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.message_bus import MessageBus
from core.module_manager import ModuleManager
from core.module_meta import ModuleMeta
from core.generated import message_pb2 as proto

logger = logging.getLogger(__name__)


@pytest.fixture
async def message_bus():
    """清理单例实例，创建新的 MessageBus"""
    await MessageBus.cleanup_sockets()
    bus = MessageBus()
    # 新增：启用测试模式，直接调用处理器
    bus.test_mode = True
    yield bus
    await MessageBus.cleanup_sockets()


@pytest.mark.asyncio
async def test_echo_workflow(message_bus):
    """测试 EchoModule 工作流"""
    bus = message_bus
    response_received = asyncio.Event()
    response_data = None
    handler_called = asyncio.Event()  # 添加处理器调用标志

    async def test_handler(envelope):
        """测试处理器，返回相同的 payload"""
        nonlocal response_data
        logger.info(f"📩 test_handler 被调用，收到消息: {envelope}")
        handler_called.set()  # 标记处理器被调用
        try:
            # 修改：使用 getattr 以防 RESPONSE 未定义（默认为 3）
            response = bus.create_envelope(
                getattr(proto.MessageType, "RESPONSE", 3), envelope.header.source
            )
            response.body.command = "echo_response"
            response.body.payload = envelope.body.payload
            response_data = response
            response_received.set()
            logger.info("处理器已生成响应")
            return response
        except Exception as e:
            logger.error(f"❌ test_handler 处理失败: {e}")
            raise

    # 启动消息循环
    await bus.start_message_loop()
    await asyncio.sleep(0.5)  # 增加等待时间，确保消息循环启动

    # 新增：加载 echo_module 模块
    manager = ModuleManager(bus)
    echo_meta = ModuleMeta.from_yaml("modules/echo_module/config.yaml")
    await manager.load_module(echo_meta, {})

    try:
        module_name = "echo_module"
        test_payload = b"test_payload"

        # 注册处理器并等待确保注册完成
        bus.register_handler(module_name, test_handler)
        await asyncio.sleep(0.2)  # 增加等待时间

        logging.info(f"准备发送测试命令到 {module_name}")
        # 发送命令
        await bus.send_command(target=module_name, command="echo", payload=test_payload)

        # 等待处理器被调用
        try:
            logging.info("等待处理器被调用...")
            await asyncio.wait_for(handler_called.wait(), timeout=3.0)
            logging.info("处理器已被调用")

            logging.info("等待响应...等待时间可能较长，需要耐心等待处理程序响应。")
            await asyncio.wait_for(response_received.wait(), timeout=3.0)
            logging.info("收到响应")

            assert response_data.body.command == "echo_response"
            assert response_data.body.payload == test_payload
            logger.info("✅ 测试成功完成")
        except asyncio.TimeoutError:
            pytest.fail("❌ 等待响应超时")

    except Exception as e:
        pytest.fail(f"❌ 测试失败: {e}")
    finally:
        await bus.stop_message_loop()
