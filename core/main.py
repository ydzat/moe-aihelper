import sys
import logging
import asyncio
from pathlib import Path
from core.message_bus import MessageBus
from core.module_manager import ModuleManager
from core.module_meta import ModuleMeta
from core.scheduler import ResourceScheduler
from core.config import ConfigCenter
from core.generated import message_pb2 as proto

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 确保模块目录可被发现
MODULES_DIR = PROJECT_ROOT / "modules"
sys.path.insert(0, str(MODULES_DIR))


async def main():
    logging.basicConfig(level=logging.DEBUG)

    # 初始化核心组件
    bus = MessageBus()
    config = ConfigCenter()
    scheduler = ResourceScheduler()
    manager = ModuleManager(bus)

    logging.info("开始启动核心系统...")

    # 启动消息总线的异步事件循环
    asyncio.create_task(bus.start_message_loop())  # ✅ 使用异步任务启动消息循环

    
    await asyncio.sleep(1)  # 确保事件循环稳定
    logging.info("🔄 加载模块")
    # 加载基础模块
    try:
        
        echo_meta = ModuleMeta.from_yaml("modules/echo_module/manifest.yaml")
        if not await scheduler.allocate(
            echo_meta.name, {}
        ):  # ✅ 修改 allocate() 为异步方法
            logging.error("❌ 资源不足，无法加载模块")
            return

        await manager.load_module(echo_meta, config)

    except Exception as e:
        logging.error(f"❌ 模块加载失败: {e}")
        raise e

    logging.info("✅ 核心系统启动完成，等待消息...")

    last_log_time = 0  # 记录上次打印 "正在监听" 的时间

    while True:
        try:
            current_time = asyncio.get_event_loop().time()

            if current_time - last_log_time >= 1:
                logging.info("🎧 正在监听消息通道...")
                last_log_time = current_time

            try:
                raw_msg = (
                    await bus.cmd_socket.recv_multipart()
                )  # ✅ 使用异步方法接收消息
                envelope = proto.Envelope()
                envelope.ParseFromString(raw_msg[2])
                logging.info(f"📩 监听到消息: {envelope}")

                # 路由消息
                target = envelope.header.route[0]
                module = manager.get_module(target)

                if module:
                    response = await module.handle_message(
                        envelope
                    )  # ✅ 确保处理器支持异步

                    if isinstance(response, proto.Envelope):
                        await bus.cmd_socket.send_multipart(
                            [
                                raw_msg[0],  # 客户端标识符
                                b"",
                                response.SerializeToString(),
                            ]
                        )
                    else:
                        logging.error(
                            f"❌ 处理消息时出错: 返回了无效类型 {type(response)}"
                        )
                        error_response = proto.Envelope()
                        error_response.header.route.append(envelope.header.source)
                        error_response.header.source = "core"
                        error_response.body.type = proto.MessageType.ERROR
                        error_response.body.command = "internal_error"
                        error_response.body.payload = b"Unexpected response type"

                        await bus.cmd_socket.send_multipart(
                            [raw_msg[0], b"", error_response.SerializeToString()]
                        )

            except asyncio.TimeoutError:
                await asyncio.sleep(1)  # ✅ 避免空循环报错，并降低 CPU 占用

        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.error(f"❌ 处理消息时出错: {e}")
            await asyncio.sleep(1)  # ✅ 避免日志过多


if __name__ == "__main__":
    asyncio.run(main())
