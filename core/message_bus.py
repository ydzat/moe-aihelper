"""
Author: @ydzat
Date: 2025-02-03 01:55:53
LastEditors: @ydzat
LastEditTime: 2025-02-03 12:59:51
Description:
"""

import zmq
import uuid
import logging
import asyncio
import zmq.asyncio
from datetime import datetime
from core.config import ConfigCenter  # Add this import statement
import traceback
from core.generated import message_pb2 as proto

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("/tmp/message_bus.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# Define the ZMQ_VERSION attribute
ZMQ_VERSION = zmq.zmq_version_info()

class MessageBus:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(MessageBus, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.context = zmq.asyncio.Context()

        # 读取核心配置，获取 `core` 作为名称
        config_center = ConfigCenter()
        core_config = config_center.get_core_config()
        self.module_name = core_config.get(
            "name", "core"
        )  # ✅ **确保 `MessageBus` 使用 `config.yaml` 里的 `name` 作为名称**

        # 路由表 {target: address}
        self.routing_table = {}

        # 存储客户端标识符 {message_id: identity}
        self.client_identities = {}

        # 消息处理器 {target: handler}
        self.message_handlers = {}

        # 命令通道 (ROUTER)
        self.cmd_socket = self.context.socket(zmq.ROUTER)
        self.cmd_socket.setsockopt(zmq.LINGER, 0)
        self.cmd_socket.setsockopt(zmq.RCVTIMEO, -1)
        self._bind_socket(self.cmd_socket, "ipc://core_cmd")

        # 路由管理通道 (DEALER)
        self.route_socket = self.context.socket(zmq.DEALER)
        self._bind_socket(self.route_socket, "ipc://core_route")

        # 事件通道 (PUB/SUB)
        self.event_socket = self.context.socket(zmq.PUB)
        self._bind_socket(self.event_socket, "ipc://core_event")

        # 心跳监测
        self.heartbeat_socket = self.context.socket(zmq.REP)
        self.heartbeat_socket.bind("inproc://heartbeat")

        self._initialized = True

    def register_handler(self, target: str, handler):
        """注册消息处理器"""
        if target in self.message_handlers:
            logging.warning(f"⚠️ 处理器 {target} 已存在，覆盖旧的")
        self.message_handlers[target] = handler
        logging.info(f"✅ 处理器已注册: {target}")

    async def start_message_loop(self):
        """异步启动消息处理循环"""
        self._message_loop_running = True
        logging.info("🚀 正在启动 `MessageBus` 消息循环...")
        asyncio.create_task(self._message_loop())
        logging.info("✅ `MessageBus` 消息循环已启动")

    async def stop_message_loop(self):
        """停止消息处理循环"""
        self._message_loop_running = False
        self.cmd_socket.close()  # ✅ 确保 `poller.poll()` 退出
        await asyncio.sleep(0.1)
        self.context.term()

    async def cleanup_sockets():
        """清理 ZeroMQ 端口，释放资源"""
        if MessageBus._instance:
            instance = MessageBus._instance
            await instance.stop_message_loop()

            instance.cmd_socket.close(linger=0)
            instance.route_socket.close(linger=0)
            instance.event_socket.close(linger=0)
            instance.heartbeat_socket.close(linger=0)

            instance.context.term()
            MessageBus._instance = None
            logging.info("✅ 所有 ZeroMQ 套接字已清理")

    def _bind_socket(self, socket, address):
        """安全绑定 ZeroMQ 套接字"""
        try:
            socket.bind(address)
            logging.info(f"✅ ZeroMQ 绑定成功: {address}")
        except zmq.ZMQError as e:
            if e.errno == zmq.EADDRINUSE:
                logging.error(
                    f"❌ 地址 {address} 已被占用，请检查是否有其他实例正在运行。"
                )
                raise RuntimeError(f"地址 {address} 已被占用。")
            else:
                logging.error(f"❌ ZMQ 绑定错误: {e}")
                raise e

    async def _message_loop(self):
        """异步消息处理循环"""
        poller = zmq.asyncio.Poller()
        poller.register(self.cmd_socket, zmq.POLLIN)

        while getattr(self, "_message_loop_running", True):
            try:
                if self.cmd_socket.closed:
                    logging.error("❌ `cmd_socket` 在消息循环中被关闭！")
                    break
                logging.debug(
                    "🔄 正在监听 `cmd_socket`，等待消息..."
                )  # 改为DEBUG级别避免日志过多
                socks = dict(await poller.poll(-1))  # 确保此处超时与配置一致

                if self.cmd_socket in socks and socks[self.cmd_socket] == zmq.POLLIN:
                    logging.info(
                        "📩 `cmd_socket` 收到新消息，即将调用 `_process_command()`"
                    )
                    try:
                        # 移除zmq.NOBLOCK，使用阻塞式接收（无标志）
                        msg = await self.cmd_socket.recv_multipart()
                        await self._process_command(msg)
                    except zmq.Again:
                        logging.warning("⚠️ 接收超时，可能数据尚未完全到达")
                    except Exception as e:
                        logging.error(f"❌ 接收消息时发生错误: {str(e)}")
                        traceback.print_exc()
            except zmq.ZMQError as e:
                logging.error(f"❌ ZeroMQ 轮询错误: {e}")
                traceback.print_exc()
            except Exception as e:
                logging.error(f"❌ 消息循环中出现未知错误: {str(e)}")
                traceback.print_exc()

    async def send_command(
        self, target: str, command: str, payload: bytes = b""
    ) -> proto.Envelope:
        """异步发送命令型消息"""
        if target not in self.message_handlers:
            logging.error(
                f"❌ 无法发送命令，目标 {target} 未注册，当前 handlers: {list(self.message_handlers.keys())}"
            )
            raise ValueError(f"未注册的目标模块: {target}")

        envelope = self.create_envelope(proto.MessageType.COMMAND, target)
        envelope.body.command = command
        envelope.body.payload = payload

        logger.debug(f"📤 发送命令到 {target}: {envelope}")

        try:
            # **确保 `cmd_socket` 绑定**
            if not self.cmd_socket:
                logging.error("❌ `cmd_socket` 未正确初始化！")
                return envelope

            # ✅ **确保 `cmd_socket` 是活跃的**
            socket_status = self.cmd_socket.getsockopt(zmq.LINGER)
            logging.info(f"🛠 `cmd_socket` 状态: LINGER={socket_status}")

            await self.cmd_socket.send_multipart(
                [target.encode(), b"", envelope.SerializeToString()]
            )
            logging.info(f"✅ 命令已成功发送到 {target}")
        except zmq.ZMQError as e:
            logging.error(f"❌ ZeroMQ 发送失败: {e}")
            return envelope

    def unregister_handler(self, target: str):
        """注销消息处理器"""
        if target in self.message_handlers:
            del self.message_handlers[target]
            logging.info(f"✅ 处理器 {target} 已注销")
        else:
            logging.warning(f"⚠️ 处理器 {target} 未注册，无法注销")

    def create_envelope(
        self, msg_type: proto.MessageType, target: str
    ) -> proto.Envelope:
        """创建标准消息信封"""
        envelope = proto.Envelope()
        envelope.header.msg_id = str(uuid.uuid4())
        envelope.header.timestamp = datetime.utcnow().isoformat() + "Z"
        envelope.header.source = "core"
        envelope.header.route.append(target)
        envelope.body.type = msg_type
        return envelope

    async def _process_command(self, msg):
        """处理命令消息"""

        try:
            client_identity = msg[0]
            message = msg[2]
            envelope = proto.Envelope()
            envelope.ParseFromString(message)

            target = envelope.header.route[0]
            logging.info(
                f"📩 `MessageBus` 收到消息: 目标={target}, 当前 handlers={list(self.message_handlers.keys())}"
            )

            if target in self.message_handlers:
                logging.info(f"✅ 目标 {target} 存在，调用 `handle_message()`...")
                handler = self.message_handlers[target]
                response = await handler(envelope)
                await self.cmd_socket.send_multipart(
                    [client_identity, b"", response.SerializeToString()]
                )
                logging.info(f"✅ 处理完成，已发送响应")
            else:
                logging.error(f"❌ 无法找到 {target} 的 handler")
        except Exception as e:
            logging.error(f"❌ 处理命令错误: {e}")

    def get_route(self, module_name: str):
        """获取模块的 ZeroMQ 路由"""
        return self.routing_table.get(module_name, None)
    
    def register_route(self, module_name: str, address: str):
        """注册模块的 ZeroMQ 路由"""
        logging.info(f"🚀 `register_route()` 注册 `{module_name}` -> `{address}`")
        self.routing_table[module_name] = address

    async def publish_event(self, event_type: str, data: bytes):
        """发布事件"""
        logging.info(f"📢 `publish_event()` 发送事件: {event_type}")

        try:
            await self.event_socket.send_multipart([event_type.encode(), data])
            logging.info(f"✅ `publish_event()` 事件发送成功: {event_type}")
        except zmq.ZMQError as e:
            logging.error(f"❌ `publish_event()` 失败: {e}")

