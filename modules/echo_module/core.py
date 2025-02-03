import asyncio
import yaml
from pathlib import Path
import uuid
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
            logging.info(f"✅ 加载 {module_config_path} 的配置: {config}")
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

        envelope = await self.bus.send_command("kernel", command, b"echo_module")
        logging.info(f"[DEBUG][{self.module_name}] 已发送状态消息: {command}")

        response = await self.bus.cmd_socket.recv_multipart()
        logging.info(f"[DEBUG][{self.module_name}] 收到响应: {response}")

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
        """返回模块元数据"""
        return ModuleMeta(
            name="echo_module",
            version="0.0.1",
            dependencies=[],
            capabilities=["echo"],
            entry_point="modules.echo_module.core:EchoModule",
        )

    async def handle_message(self, envelope: proto.Envelope) -> proto.Envelope:
        """异步处理 ECHO 命令，确保返回的是 `proto.Envelope`"""
        logging.debug(f"[DEBUG][{self.module_name}] 处理消息: {envelope}")

        response = proto.Envelope()
        response.header.route.append(envelope.header.source)
        response.header.source = self.module_name
        response.header.msg_id = str(uuid.uuid4())

        if envelope.body.type != proto.MessageType.COMMAND:
            response.body.type = proto.MessageType.ERROR
            response.body.command = "invalid_message_type"
            response.body.payload = b"Expected COMMAND message type"
            logging.error(
                f"❌ {self.module_name} 收到无效消息类型: {envelope.body.type}"
            )
            return response

        if envelope.body.command != "ECHO":
            response.body.type = proto.MessageType.ERROR
            response.body.command = "unsupported_command"
            response.body.payload = b"Unsupported command, only ECHO is supported"
            logging.error(
                f"❌ {self.module_name} 收到不支持的命令: {envelope.body.command}"
            )
            return response

        response.body.type = proto.MessageType.DATA_STREAM
        response.body.command = "echo_response"
        response.body.payload = envelope.body.payload

        logging.debug(f"[DEBUG][{self.module_name}] 发送响应: {response}")
        return response  # ✅ 确保返回 `proto.Envelope`
