'''
Author: @ydzat
Date: 2025-02-01 01:16:59
LastEditors: @ydzat
LastEditTime: 2025-02-01 01:17:10
Description: 
'''
from core.module_meta import ModuleMeta
from core.generated import message_pb2 as proto

class BaseModule:
    def __init__(self, bus):
        self.bus = bus
        self.module_name = self.__class__.__name__.lower()
        
    def handle_message(self, envelope: proto.Envelope) -> proto.Envelope:
        """处理消息的抽象方法"""
        raise NotImplementedError()
        
    def pre_unload(self):
        """模块卸载前的清理工作"""
        pass
        
    @classmethod
    def pre_init(cls):
        """模块初始化前的准备工作"""
        pass
        
    @classmethod 
    def post_init(cls):
        """模块初始化后的收尾工作"""
        pass
        
    @classmethod
    def get_metadata(cls) -> ModuleMeta:
        """获取模块元数据"""
        raise NotImplementedError()
