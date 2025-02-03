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
import yaml
from pathlib import Path
import logging
from core.module_meta import ModuleMeta
from core.generated import message_pb2 as proto
from core.base_module import BaseModule
from core.config import ConfigCenter


class EchoModule(BaseModule):

    def __init__(self, bus):
        super().__init__(bus)

        # ✅ 从 `config.yaml` 读取模块名称
        config_center = ConfigCenter()
        module_config = config_center.get_module_config("echo_module")
        self.module_name = module_config.get("name", "echo_module")

        self.bus = bus

        # ✅ 确保消息处理器注册
        if self.module_name not in self.bus.message_handlers:
            self.register_handlers()

    @staticmethod
    async def from_config(config: dict = None):
        """从 `config.yaml` 文件加载模块配置"""
        module_config_path = Path(__file__).resolve().parent / "config.yaml"

        if module_config_path.exists():
            with open(module_config_path, "r") as f:
                config = yaml.safe_load(f)
            logging.info("✅ 加载 {} 的配置: {}".format(module_config_path, config))
        else:
            config = {"logging_level": "DEBUG", "response_delay": 0}
            with open(module_config_path, "w") as f:
                yaml.safe_dump(config, f, default_flow_style=False)
            logging.info(f"🔄 生成默认配置: {config}")

        bus = EchoModule.get_bus_instance()
        instance = EchoModule(bus)
        instance.set_config(config)
        return instance

    def set_config(self, config: dict):
        """设置模块配置"""
        self.config = config or {}
        logging.info(f"[DEBUG][{self.module_name}] 配置已应用: {self.config}")

    async def send_status_message(self, command: str):
        """异步发送状态消息"""
        if "kernel" not in self.bus.message_handlers:
            raise ValueError("❌ `kernel` 处理器未注册")
        # 使用 send_command 得到响应，不再直接调用 cmd_socket.recv_multipart
        envelope = await self.bus.send_command("kernel", command, b"echo_module")
        logging.info(f"[DEBUG][{self.module_name}] 已发送状态消息: {command}")
        logging.info(f"[DEBUG][{self.module_name}] 收到响应: {envelope}")

    @classmethod
    async def pre_init(cls):
        """模块初始化前执行"""
        logging.info(f"🔄 预初始化 {cls.__name__}")
        cls.instance = cls(bus=cls.get_bus_instance())

    @classmethod
    async def post_init(cls):
        """模块初始化后执行"""
        logging.info(f"✅ {cls.__name__} 初始化完成")
        if hasattr(cls, "instance"):
            cls.instance.register_handlers()

    def register_handlers(self):
        """注册消息处理器"""
        logging.info(f"🚀 正在注册 {self.module_name} 处理器...")
        if self.module_name not in self.bus.message_handlers:
            self.bus.register_handler(
                self.module_name, self.handle_message
            )  # ✅ **从 `config.yaml` 读取 `name`**
            logging.info(f"✅ {self.module_name} 已注册消息处理器，成功")
        else:
            logging.warning(f"⚠️ {self.module_name} 处理器已存在，跳过注册")

    @classmethod
    def get_metadata(cls) -> ModuleMeta:
        return ModuleMeta(
            name="echo_module",
            version="1.0.0",
            dependencies=[],
            capabilities=["echo"],
            entry_point="echo_module.core:EchoModule",
        )

    async def handle_message(self, envelope: proto.Envelope) -> proto.Envelope:
        logging.info(
            f"📩 EchoModule 收到消息, msg_id={envelope.header.msg_id}: {envelope}"
        )
        response = self.bus.create_envelope(
            proto.MessageType.RESPONSE, envelope.header.source
        )
        response.body.command = "echo_response"
        response.body.payload = envelope.body.payload
        # 确保响应保持相同的 msg_id
        response.header.msg_id = envelope.header.msg_id
        logging.info(
            f"📤 EchoModule 生成响应, msg_id={response.header.msg_id}: {response}"
        )
        return response
