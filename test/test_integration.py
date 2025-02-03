import sys
import os
import pytest
import logging
import asyncio
import zmq.asyncio
from pathlib import Path

# **手动添加 core 目录到 Python 路径**
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.message_bus import MessageBus
from core.module_manager import ModuleManager
from core.module_meta import ModuleMeta
from core.generated import message_pb2 as proto
from core.config import ConfigCenter

logger = logging.getLogger(__name__)


@pytest.fixture
async def message_bus():
    """清理单例实例，创建新的 MessageBus"""
    await MessageBus.cleanup_sockets()
    bus = MessageBus()
    yield bus
    await MessageBus.cleanup_sockets()


@pytest.mark.asyncio
async def test_echo_workflow(message_bus):
    """测试 EchoModule 工作流"""
    logger.info("✅ test_echo_workflow() 开始执行！")
    bus = message_bus
    await bus.start_message_loop()
    logger.info("✅ 消息循环已启动")

    print("✅ test_echo_workflow() 等待事件循环启动！")
    await asyncio.sleep(0)

    print("✅ test_echo_workflow() 读取模块配置！")
    config_center = ConfigCenter()
    module_config = config_center.get_module_config(
        "echo_module"
    )  # ✅ **读取 `echo_module` 的 `config.yaml`**
    module_name = module_config.get(
        "name", "echo_module"
    )  # ✅ **获取 `name` 作为注册名称**

    print(f"✅ test_echo_workflow() 注册测试处理器: {module_name}！")

    # 1. 注册测试处理器
    received = asyncio.Future()  # 用于捕获响应

    async def test_handler(envelope):
        """测试处理器，返回相同的 payload"""
        logger.info(f"📩 test_handler 收到消息: {envelope}")
        response = bus.create_envelope(
            proto.MessageType.RESPONSE, envelope.header.source
        )
        response.body.command = "echo_response"
        response.body.payload = envelope.body.payload

        received.set_result(response)
        return response

    logger.info(f"🚀 尝试注册 test_handler 处理器: {module_name}")
    bus.register_handler(
        module_name, test_handler
    )  # ✅ **确保注册名称来自 `config.yaml`**
    logger.info(f"✅ 测试处理器已注册: {module_name}")

    try:
        # 2. 发送测试命令
        test_payload = b"test_payload"

        await asyncio.sleep(0.1)
        logger.info("✅ 准备发送测试命令")

        try:
            await bus.send_command(
                target=module_name, command="echo", payload=test_payload
            )
            logger.info(f"✅ 测试命令已发送，目标: {module_name}")
        except Exception as e:
            logger.error(f"❌ `send_command()` 失败: {e}")
            pytest.fail(f"❌ `send_command()` 失败: {e}")

        # 3. 使用 Poller 等待响应
        poller = zmq.asyncio.Poller()
        poller.register(bus.cmd_socket, zmq.POLLIN)

        print("🚀 等待 poller.poll() 事件...")
        logger.info(
            f"📋 当前处理器列表: {list(bus.message_handlers.keys())}"
        )  # ✅ **检查 `echo_module` 是否仍然存在**

        socks = dict(await poller.poll(5000))
        print("✅ poller.poll() 事件返回！")

        if not socks:
            pytest.fail("❌ 等待响应超时，未收到任何消息")

        if bus.cmd_socket in socks and socks[bus.cmd_socket] == zmq.POLLIN:
            response = await bus.cmd_socket.recv_multipart()

            # 验证响应格式
            assert len(response) == 3, f"❌ 无效响应格式: {response}"

            # 解析协议
            parsed = proto.Envelope()
            parsed.ParseFromString(response[2])

            # 验证响应内容
            assert parsed.body.command == "echo_response"
            assert parsed.body.payload == test_payload

            # ✅ 验证 Future 是否完成
            assert received.done(), "❌ 处理器未正确触发"
        else:
            pytest.fail(f"❌ 收到非预期 socket 事件: {socks}")

    finally:
        # 4. 清理处理器
        logger.info(f"✅ 测试完成，开始注销程序")
        bus.unregister_handler(module_name)
        await bus.stop_message_loop()
        logger.info("✅ 消息循环已停止")


# if __name__ == "__main__":
#     import asyncio
#     print("🚀 手动运行 test_echo_workflow()")

#     loop = asyncio.get_event_loop()
#     loop.run_until_complete(test_echo_workflow(MessageBus()))
