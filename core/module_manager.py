import logging
import asyncio
from typing import Dict
from enum import Enum, auto
from core.module_meta import ModuleMeta
from core.message_bus import MessageBus


class ModuleState(Enum):
    """模块状态"""

    LOADING = auto()
    RUNNING = auto()
    STOPPING = auto()
    ERROR = auto()


class ModuleManager:
    def __init__(self, message_bus: MessageBus):
        self.modules: Dict[str, object] = {}  # 已加载模块
        self.module_states = {}  # 模块状态记录
        self.message_bus = message_bus
        self.lock = asyncio.Lock()  # ✅ 改为 asyncio.Lock 以支持异步环境

    @property
    def loaded_modules(self) -> Dict[str, object]:
        """获取已加载模块的只读视图"""
        return self.modules.copy()

    async def _set_module_state(self, module_name: str, state: ModuleState):
        """设置模块状态"""
        logging.info(f"🚀 `_set_module_state()` 开始: {module_name} -> {state.name}")

        # ✅ **检查 `self.lock` 是否被占用**
        if self.lock.locked():
            logging.error(f"❌ `_set_module_state()` 发现 `self.lock` 已被占用，尝试等待释放")
            await asyncio.sleep(1)  # ✅ **避免立即失败，等待锁释放**
            return

        async with self.lock:
            logging.info(f"✅ `_set_module_state()` 获取到锁: {module_name}")
            self.module_states[module_name] = state

        logging.info(f"📢 `_set_module_state()` 发布事件: MODULE_STATE_CHANGED")
        await self.message_bus.publish_event("MODULE_STATE_CHANGED", f"{module_name}:{state.name}".encode())

        logging.info(f"✅ `_set_module_state()` 结束: {module_name} -> {state.name}")




    async def get_module_state(self, module_name: str) -> ModuleState:
        """获取模块状态"""
        async with self.lock:
            return self.module_states.get(module_name, ModuleState.ERROR)

    async def load_module(self, meta: ModuleMeta, config: dict = None):
        """异步加载模块"""
        logging.info(f"🚀 `load_module()` 开始加载模块 `{meta.name}`")
        async with self.lock:
            logging.info(f"✅ `load_module()` 获取到锁 `{meta.name}`")

            if meta.name in self.modules:
                logging.warning(f"[ModuleManager]⚠️ 模块 {meta.name} 已加载，跳过")
                return  # ✅ 避免重复加载
            
            await self._set_module_state(meta.name, ModuleState.LOADING)
            config = config or {}
            logging.warning(f"[ModuleManager]✅ 模块 {meta.name} 开始加载")

            # 解析并加载依赖
            dependencies = meta.dependencies or []
            for dep_name in dependencies:
                if dep_name not in self.modules:
                    dep_meta = ModuleMeta.from_yaml(f"modules/{dep_name}/manifest.yaml")
                    await self.load_module(dep_meta)

            logging.info(f"[ModuleManager]🔄 加载模块: {meta.name}")

            # 加载模块入口类
            entry_class = meta.load_entry_class()
            instance = entry_class(self.message_bus)

            logging.info(f"✅ {meta.name} 实例化成功")
            
            if hasattr(instance, "set_config"):
                instance.set_config(config)

            logging.info(f"[ModuleManager]🔄 初始化模块: {meta.name}")

            # ✅ **异步注册 `handle_message()`**
            if hasattr(instance, "handle_message"):
                handler = instance.handle_message
                # 从配置获取模块名称，默认使用meta.name
                config_name = config.get("name", meta.name)
                module_name = f"{config_name}_socket"
                if module_name not in self.message_bus.message_handlers:
                    logging.info(f"[ModuleManager]🚀 注册处理器: {module_name}")
                    if asyncio.iscoroutinefunction(handler):
                        logging.info(f"[ModuleManager]🚀 注册异步处理器: {module_name}")
                        self.message_bus.register_handler(
                            module_name, lambda env: asyncio.create_task(handler(env))
                        )
                    else:
                        logging.info(f"[ModuleManager]🚀 注册同步处理器: {module_name}")
                        self.message_bus.register_handler(module_name, handler)

            self.modules[meta.name] = instance
            logging.info(f"✅ 模块 {meta.name} 加载成功")

            # 注册 ZeroMQ 路由（使用配置名称）
            module_address = f"ipc:///tmp/{config_name}_socket"
            route_name = config_name
            if self.message_bus.get_route(route_name) is None:
                self.message_bus.register_route(route_name, module_address)
                logging.info(f"🔄 注册路由: {module_name} -> {module_address}")

            await self._set_module_state(meta.name, ModuleState.RUNNING)

            # 发送系统事件
            await self.message_bus.publish_event("MODULE_LOADED", meta.name.encode())

    async def unload_module(self, module_name: str):
        """异步卸载模块"""
        async with self.lock:
            if module_name not in self.modules:
                return

            await self._set_module_state(module_name, ModuleState.STOPPING)

            instance = self.modules[module_name]
            if hasattr(instance, "pre_unload"):
                await instance.pre_unload()

            # 清理模块路由和处理器
            self.message_bus.unregister_handler(f"{module_name}_socket")
            self.message_bus.unregister_route(module_name)

            if hasattr(instance, "post_unload"):
                await instance.post_unload()

            del self.modules[module_name]
            del self.module_states[module_name]

            logging.info(f"✅ 模块 {module_name} 已卸载")
            self.message_bus.publish_event("MODULE_UNLOADED", module_name.encode())

    def get_module(self, name: str) -> object:
        """获取已加载模块实例"""
        return self.modules.get(
            name.replace("_socket", "")
        )  # ✅ **修复获取模块时的名称问题**

    async def start_heartbeat(self, interval: int = 3):
        """启动异步心跳检测"""
        while True:
            async with self.lock:
                for name, instance in self.modules.items():
                    try:
                        if hasattr(instance, "heartbeat"):
                            await instance.heartbeat()
                    except Exception as e:
                        logging.error(f"❌ 模块 {name} 心跳失败: {str(e)}")
                        await self.unload_module(name)
            await asyncio.sleep(interval)
