"""
Author: @ydzat
Date: 2025-02-03 01:55:53
LastEditors: @ydzat
LastEditTime: 2025-02-03 12:59:51
Description:
"""

# Copyright (C) 2024 @ydzat
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later



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
        self.cmd_socket.setsockopt(zmq.LINGER, 1000)  # 设置延迟关闭时间
        self.cmd_socket.setsockopt(zmq.RCVTIMEO, -1)  # 无限超时
        self.cmd_socket.setsockopt(zmq.SNDTIMEO, 1000)  # 发送超时
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

        self._message_loop_running = False
        self._initialized = True
        self._cmd_lock = asyncio.Lock()  # 新增：保护 cmd_socket 的锁
        self._response_futures = {}  # 新增：保存待响应的 Future
        # 新增：测试模式标识（默认 False）
        self.test_mode = False

    def register_handler(self, target: str, handler):
        """注册消息处理器"""
        if target in self.message_handlers:
            logging.warning(f"⚠️ 处理器 {target} 已存在，覆盖旧的")
        self.message_handlers[target] = handler
        logging.info(f"✅ 处理器已注册: {target}")

    async def start_message_loop(self):
        """异步启动消息处理循环"""
        if self._message_loop_running:
            return

        self._message_loop_running = True
        logging.info("🚀 正在启动消息循环...")
        # 使用独立的事件循环任务
        self._loop_task = asyncio.create_task(self._message_loop())
        await asyncio.sleep(0.1)  # 确保消息循环启动
        logging.info("✅ 消息循环已启动")

    async def stop_message_loop(self):
        """停止消息处理循环"""
        logging.info("🚀 正在停止消息循环...")
        if hasattr(self, "_loop_task"):
            self._message_loop_running = False
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass

        # 关闭所有套接字
        if hasattr(self, "cmd_socket"):
            self.cmd_socket.close()
            logging.info("✅ cmd_socket 已关闭")
        if self.route_socket:
            self.route_socket.close()
            logging.info("✅ route_socket 已关闭")
        if self.event_socket:
            self.event_socket.close()
            logging.info("✅ event_socket 已关闭")
        if self.heartbeat_socket:
            self.heartbeat_socket.close()
            logging.info("✅ heartbeat_socket 已关闭")

        await asyncio.sleep(0.1)  # 确保套接字关闭
        self.context.term()
        logging.info("✅ ZeroMQ 上下文已终止")

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
        poller = zmq.asyncio.Poller()
        poller.register(self.cmd_socket, zmq.POLLIN)

        while self._message_loop_running:
            try:
                events = dict(await poller.poll(timeout=100))

                if self.cmd_socket in events:
                    try:
                        async with self._cmd_lock:  # 加锁接收消息
                            frames = await self.cmd_socket.recv_multipart()
                        logging.debug(f"消息循环收到消息: {frames}")

                        if len(frames) >= 4:
                            msg_id = frames[1]
                            envelope = proto.Envelope()
                            envelope.ParseFromString(frames[3])
                            # 如果是响应消息，则通知等待的 Future
                            if envelope.body.type == proto.MessageType.RESPONSE:
                                future = self._response_futures.get(msg_id)
                                if future and not future.done():
                                    future.set_result(envelope)
                                    logging.debug(
                                        f"已通过 Future 返回响应，msg_id={msg_id}"
                                    )
                                continue  # 不再调用处理器

                            # 否则为请求消息，按老逻辑处理
                            target = frames[0].decode()
                            handler = self.message_handlers.get(target)
                            if handler:
                                logging.debug(f"调用处理器 {target} 处理消息 {msg_id}")
                                try:
                                    response = await handler(envelope)
                                    if response:
                                        response_frames = [
                                            frames[0],
                                            msg_id,
                                            b"",
                                            response.SerializeToString(),
                                        ]
                                        async with self._cmd_lock:  # 加锁发送响应
                                            await self.cmd_socket.send_multipart(
                                                response_frames
                                            )
                                        logging.debug(f"已发送响应，msg_id={msg_id}")
                                except Exception as handler_error:
                                    logging.error(f"处理器执行出错: {handler_error}")
                                    traceback.print_exc()
                            else:
                                logging.error(f"未找到处理器: {target}")

                    except zmq.Again:
                        continue
                    except Exception as e:
                        logging.error(f"接收消息时出错: {e}")
                        traceback.print_exc()
                else:
                    await asyncio.sleep(0.01)

            except Exception as e:
                if isinstance(e, zmq.ZMQError) and e.errno == zmq.ETERM:
                    break
                logging.error(f"消息循环错误: {e}")
                traceback.print_exc()
                await asyncio.sleep(0.1)

        logging.info("✅ 消息循环正常退出")

    async def send_command(
        self, target: str, command: str, payload: bytes = b""
    ) -> proto.Envelope:
        """异步发送命令型消息，带重试机制"""
        # 新增：测试模式下直接调用处理器
        if self.test_mode:
            if target not in self.message_handlers:
                raise ValueError(f"未注册的目标模块: {target}")
            envelope = self.create_envelope(proto.MessageType.COMMAND, target)
            envelope.body.command = command
            envelope.body.payload = payload
            logging.debug(f"(Test Mode) 直接调用处理器 {target}, command={command}")
            return await self.message_handlers[target](envelope)

        if target not in self.message_handlers:
            raise ValueError(f"未注册的目标模块: {target}")

        envelope = self.create_envelope(proto.MessageType.COMMAND, target)
        envelope.body.command = command
        envelope.body.payload = payload
        msg_id = str(uuid.uuid4()).encode()

        retry_count = 0
        max_retries = 3
        timeout_sec = 2.0

        logging.debug(
            "准备发送命令到 {}，command={}，msg_id={}".format(target, command, msg_id)
        )

        poller = zmq.asyncio.Poller()
        poller.register(self.cmd_socket, zmq.POLLIN)

        while retry_count < max_retries:
            try:
                async with self._cmd_lock:  # 加锁发送命令
                    frames = [
                        target.encode(),
                        msg_id,
                        b"",
                        envelope.SerializeToString(),
                    ]
                    await self.cmd_socket.send_multipart(frames, flags=0)
                logging.debug(
                    "命令已发送到 {}，等待响应中... msg_id={}".format(target, msg_id)
                )

                future = asyncio.get_event_loop().create_future()
                self._response_futures[msg_id] = future
                try:
                    response_envelope = await asyncio.wait_for(
                        future, timeout=timeout_sec
                    )
                    return response_envelope
                except asyncio.TimeoutError:
                    retry_count += 1
                    timeout_sec *= 2
                    logging.debug(
                        "重试 {}/{}，超时 {}s".format(
                            retry_count, max_retries, timeout_sec
                        )
                    )
                finally:
                    self._response_futures.pop(msg_id, None)

            except Exception as e:
                logging.error(f"发送命令时出现异常: {e}")
                retry_count += 1
                if retry_count >= max_retries:
                    raise

        error_msg = f"发送命令到 {target} 失败，已重试 {max_retries} 次"
        logging.error(error_msg)
        raise zmq.error.Again(error_msg)

    async def send_response(self, envelope: proto.Envelope) -> None:
        """发送响应消息"""
        if not isinstance(envelope, proto.Envelope):
            raise ValueError("响应必须是 Envelope 类型")

        try:
            target = envelope.header.route[0]
            await self.cmd_socket.send_multipart(
                [target.encode(), envelope.SerializeToString()]
            )
            logging.info(f"✅ 响应已发送到 {target}")
        except Exception as e:
            logging.error(f"❌ 发送响应失败: {e}")
            raise

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
        """优化命令处理流程"""
        logging.info(f"🔄 处理命令: {msg}")
        try:
            client_id, _, data = msg[:3]  # 解析消息格式
            envelope = proto.Envelope()
            envelope.ParseFromString(data)

            target = envelope.header.route[0]
            handler = self.message_handlers.get(target)

            if not handler:
                logging.error(f"❌ 未找到处理器: {target}")
                return

            logging.info(f"✅ 找到处理器: {target}")
            response = await handler(envelope)
            reply_msg = [client_id, b"", response.SerializeToString()]
            await self.cmd_socket.send_multipart(reply_msg)
            logging.info(f"✅ 已处理 {target} 的请求")

        except Exception as e:
            logging.error(f"处理命令异常: {e}")
            traceback.print_exc()

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
