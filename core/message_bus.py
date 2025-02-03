'''
Author: @ydzat
Date: 2025-01-31 22:49:35
LastEditors: @ydzat
LastEditTime: 2025-02-01 03:34:09
Description: 
'''
# core/message_bus.py
import zmq
import uuid
import logging
from datetime import datetime
from core.generated import message_pb2 as proto

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/message_bus.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ZMQ version info
ZMQ_VERSION = tuple(map(int, zmq.zmq_version().split('.')))

class MessageBus:
    def __init__(self):
        self.context = zmq.Context()
        
        # 路由表 {target: address}
        self.routing_table = {}
        
        # 存储客户端标识符 {message_id: identity}
        self.client_identities = {}
        
        # 消息处理器 {target: handler}
        self.message_handlers = {}
        
        # 命令通道 (ROUTER)
        self.cmd_socket = self.context.socket(zmq.ROUTER)
        self.cmd_socket.setsockopt(zmq.RCVTIMEO, 1000)  # 设置1秒超时
        self.cmd_socket.bind("tcp://*:5555")
        
        # 路由管理通道 (DEALER)
        self.route_socket = self.context.socket(zmq.DEALER)
        self.route_socket.bind("tcp://*:5557")
        
        # 事件通道 (PUB/SUB)
        self.event_socket = self.context.socket(zmq.PUB)
        self.event_socket.bind("tcp://*:5556")
        
        # 心跳监测
        self.heartbeat_socket = self.context.socket(zmq.REP)
        self.heartbeat_socket.bind("inproc://heartbeat")

    def create_envelope(self, msg_type: proto.MessageType, target: str) -> proto.Envelope:
        """创建标准消息信封"""
        envelope = proto.Envelope()
        header = envelope.header
        header.msg_id = str(uuid.uuid4())
        header.timestamp = datetime.utcnow().isoformat() + "Z"
        header.source = "core"
        header.route.append(target)
        
        body = envelope.body
        body.type = msg_type
        return envelope

    def send_command(self, target: str, command: str, payload: bytes = b"") -> proto.Envelope:
        """发送命令型消息"""
        envelope = self.create_envelope(proto.MessageType.COMMAND, target)
        envelope.body.command = command
        envelope.body.payload = payload
        self.cmd_socket.send_multipart([
            target.encode(),  # 目标模块的标识符
            b"",  # 空帧
            envelope.SerializeToString()
        ])
        return envelope

    def publish_event(self, event_type: str, data: bytes):
        """发布事件型消息"""
        envelope = self.create_envelope(proto.MessageType.EVENT, "*")
        envelope.body.command = event_type
        envelope.body.payload = data
        self.event_socket.send(envelope.SerializeToString())

    def register_route(self, target: str, address: str):
        """注册路由"""
        if target in self.routing_table:
            raise ValueError(f"Route for {target} already exists")
        self.routing_table[target] = address
        logging.info(f"Registered route: {target} -> {address}")

    def register_handler(self, target: str, handler):
        """注册消息处理器"""
        if target in self.message_handlers:
            logging.warning(f"Overwriting existing handler for {target}")
        self.message_handlers[target] = handler
        logging.info(f"Registered handler for {target}")

    def unregister_handler(self, target: str):
        """注销消息处理器"""
        if target in self.message_handlers:
            del self.message_handlers[target]
            logging.info(f"Unregistered handler for {target}")
        else:
            logging.warning(f"No handler found for {target} to unregister")

    def unregister_route(self, target: str):
        """注销路由"""
        if target not in self.routing_table:
            return
        del self.routing_table[target]
        logging.info(f"Unregistered route: {target}")

    def get_route(self, target: str) -> str:
        """获取路由地址"""
        return self.routing_table.get(target)

    def start_heartbeat(self, interval: int = 3):
        """启动心跳检测服务"""
        def _heartbeat_server():
            while True:
                msg = self.heartbeat_socket.recv_string()
                self.heartbeat_socket.send_string("ALIVE")

        import threading
        thread = threading.Thread(target=_heartbeat_server, daemon=True)
        thread.start()

    def start_message_loop(self):
        """启动消息处理循环"""
        import threading
        import zmq
        
        self._message_loop_running = True
        
        def _message_loop():
            poller = zmq.Poller()
            poller.register(self.cmd_socket, zmq.POLLIN)
            poller.register(self.route_socket, zmq.POLLIN)
            
            while self._message_loop_running:
                try:
                    socks = dict(poller.poll(timeout=1000))
                    
                    if self.cmd_socket in socks:
                        msg = self.cmd_socket.recv_multipart()
                        # 处理命令消息
                        self._process_command(msg)
                        
                    if self.route_socket in socks:
                        msg = self.route_socket.recv_multipart()
                        # 处理路由消息
                        self._process_route(msg)
                        
                except zmq.ZMQError as e:
                    logging.error(f"Message loop error: {e}")
                    break

        self._message_loop_thread = threading.Thread(target=_message_loop, daemon=True)
        self._message_loop_thread.start()

    def stop_message_loop(self):
        """停止消息处理循环"""
        if hasattr(self, '_message_loop_thread'):
            self._message_loop_running = False
            self._message_loop_thread.join(timeout=1)
            
        # 关闭所有socket
        self.cmd_socket.close()
        self.route_socket.close()
        self.event_socket.close()
        self.heartbeat_socket.close()

    def _process_command(self, msg):
        """处理命令消息"""
        try:
            # ROUTER socket消息格式：[identity, empty, message]
            if len(msg) != 3:
                logging.error(f"Invalid message format: {msg}")
                return
                
            client_identity = msg[0]
            empty = msg[1]
            message = msg[2]
            envelope = proto.Envelope()
            envelope.ParseFromString(message)
            
            # 保存客户端标识符
            self.client_identities[envelope.header.msg_id] = client_identity
            
            # 根据目标地址转发消息
            target = envelope.header.route[0]
            
            # 如果有注册的handler，直接调用
            if target in self.message_handlers:
                handler = self.message_handlers[target]
                try:
                    response = handler(envelope)
                    if response:
                        # 将响应返回给原始客户端
                        self.cmd_socket.send_multipart([
                            client_identity,
                            b"",  # 空帧
                            response.SerializeToString()
                        ])
                        return  # 直接返回，不再继续路由
                    else:
                        # 如果没有返回响应，返回默认确认
                        ack = self.create_envelope(proto.MessageType.ACK, envelope.header.source)
                        self.cmd_socket.send_multipart([
                            client_identity,
                            b"",
                            ack.SerializeToString()
                        ])
                        return
                except Exception as e:
                    logging.error(f"Handler error for {target}: {e}")
                    # 返回错误响应
                    err = self.create_envelope(proto.MessageType.ERROR, envelope.header.source)
                    err.body.command = "handler_error"
                    err.body.payload = str(e).encode()
                    self.cmd_socket.send_multipart([
                        client_identity,
                        b"",
                        err.SerializeToString()
                    ])
                    return
            elif target in self.routing_table:
                # 将客户端标识符添加到消息头部
                envelope.header.route.append(client_identity.decode())
                self.route_socket.send_multipart([
                    target.encode(),
                    envelope.SerializeToString()
                ])
            else:
                logging.error(f"No route or handler found for target: {target}")
                
        except Exception as e:
            logging.error(f"Command processing error: {e}")

    def _process_route(self, msg):
        """处理路由消息"""
        try:
            # DEALER socket消息格式：[模块标识符, message]
            module_identity = msg[0]
            message = msg[1]
            envelope = proto.Envelope()
            envelope.ParseFromString(message)
            
            # 从消息头部获取客户端标识符
            client_identity = envelope.header.route[-1].encode()
            
            # 移除客户端标识符以避免循环
            envelope.header.route.pop()
            
            # 通过cmd_socket发送响应，包含原始客户端标识符
            self.cmd_socket.send_multipart([
                client_identity,
                b"",  # 空帧
                envelope.SerializeToString()
            ])
        except Exception as e:
            logging.error(f"Route processing error: {e}")
