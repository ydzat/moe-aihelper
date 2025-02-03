'''
Author: @ydzat
Date: 2025-01-31 22:54:47
LastEditors: @ydzat
LastEditTime: 2025-02-01 03:37:59
Description: 
'''
import zmq
from core.module_meta import ModuleMeta
from core.generated import message_pb2 as proto
from core.base_module import BaseModule

class EchoModule(BaseModule):
    def __init__(self, bus):
        super().__init__(bus)
        self.module_name = "echo_module"
        self.bus = bus
        self.bus.register_route(self.module_name, f"inproc://{self.module_name}")
        # 注册消息处理函数
        self.bus.register_handler(self.module_name, self.handle_message)
        
    @classmethod
    def pre_init(cls):
        print(f"Initializing {cls.__name__}")
        
    @classmethod
    def post_init(cls):
        print(f"Post initialization for {cls.__name__}")
        
    @classmethod
    def get_metadata(cls) -> ModuleMeta:
        return ModuleMeta(
            name="echo_module",
            version="1.0.0",
            dependencies=[],
            capabilities=["echo"],
            entry_point="echo_module.core:EchoModule"
        )
        
    def handle_message(self, envelope: proto.Envelope) -> proto.Envelope:
        """处理ECHO命令"""
        try:
            response = proto.Envelope()
            response.header.CopyFrom(envelope.header)
            
            if envelope.body.type != proto.MessageType.COMMAND:
                response.body.type = proto.MessageType.ERROR
                response.body.command = "invalid_message_type"
                response.body.payload = b"Expected COMMAND message type"
                return response
                
            if envelope.body.command != "ECHO":
                response.body.type = proto.MessageType.ERROR
                response.body.command = "unsupported_command"
                response.body.payload = b"Unsupported command, only ECHO is supported"
                return response
                
            # 处理ECHO命令
            response.body.type = proto.MessageType.DATA_STREAM
            response.body.command = "echo_response"
            response.body.payload = envelope.body.payload
            
            return response
            
        except Exception as e:
            # 返回错误响应
            response = proto.Envelope()
            response.header.CopyFrom(envelope.header)
            response.body.type = proto.MessageType.ERROR
            response.body.command = "handler_error"
            response.body.payload = str(e).encode()
            return response
        
    def pre_unload(self):
        print(f"Unloading {self.module_name}")
