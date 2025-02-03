'''
Author: @ydzat
Date: 2025-02-03 19:57:12
LastEditors: @ydzat
LastEditTime: 2025-02-03 22:39:23
Description: 
'''

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


import logging
from core.module_meta import ModuleMeta
from core.generated import message_pb2 as proto


class BaseModule:
    def __init__(self, bus):
        self.bus = bus
        self.module_name = self.__class__.__name__.lower()

        # 注册处理器（如果未注册）
        if self.module_name not in self.bus.message_handlers:
            self.register_handlers()

    async def handle_message(self, envelope: proto.Envelope) -> proto.Envelope:
        """异步处理消息，子类必须实现"""
        raise NotImplementedError(
            "❌ `handle_message()` 必须被子类实现，并返回 `proto.Envelope`"
        )

    async def pre_unload(self):
        """异步模块卸载前的清理工作"""
        pass

    @classmethod
    async def pre_init(cls):
        """模块初始化前执行"""
        logging.info(f"🔄 预初始化 {cls.__name__}")

    @classmethod
    async def post_init(cls):
        """模块初始化后执行"""
        logging.info(f"✅ {cls.__name__} 初始化完成")
        # 如果需要额外的异步操作，可在此处理，不再实例化新对象

    def register_handlers(self):
        """注册消息处理器"""
        if self.module_name not in self.bus.message_handlers:
            self.bus.register_handler(self.module_name, self.handle_message)
            logging.info(f"✅ 已注册消息处理器: {self.module_name}")

    @classmethod
    def get_metadata(cls) -> ModuleMeta:
        """获取模块元数据，子类必须实现"""
        raise NotImplementedError()

    @staticmethod
    def get_bus_instance():
        """获取消息总线实例"""
        from core.message_bus import MessageBus

        return MessageBus()
