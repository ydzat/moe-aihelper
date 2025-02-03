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
        self.modules: Dict[str, object] = {}
        self.module_states = {}
        self.message_bus = message_bus  # 避免超长，拆分注释或换行
        self.lock = asyncio.Lock()
        self._dependency_stack = []  # 新增依赖加载栈用于循环依赖检测

    @property
    def loaded_modules(self) -> Dict[str, object]:
        return self.modules.copy()

    async def _set_module_state(self, module_name: str, state: ModuleState):
        """设置模块状态（需在锁保护下调用）"""
        logging.info(f"🚀 `_set_module_state()` 开始: {module_name} -> {state.name}")
        self.module_states[module_name] = state
        await self.message_bus.publish_event(
            "MODULE_STATE_CHANGED", f"{module_name}:{state.name}".encode()
        )
        logging.info(f"✅ `_set_module_state()` 结束: {module_name} -> {state.name}")

    async def get_module_state(self, module_name: str) -> ModuleState:
        async with self.lock:
            return self.module_states.get(module_name, ModuleState.ERROR)

    async def load_module(self, meta: ModuleMeta, config: dict = None):
        """改进后的模块加载方法，解决锁竞争问题"""
        logging.info(f"🚀 加载模块 `{meta.name}` 启动")

        # 第一阶段：初始检查和状态设置
        async with self.lock:
            if meta.name in self.modules:
                logging.warning("⚠️ 模块已加载，跳过重复加载")
                return

            # 循环依赖检测
            if meta.name in self._dependency_stack:
                logging.warning(
                    "⚠️ 循环依赖检测发现问题: " + str(self._dependency_stack)
                )
                raise RuntimeError("⚠️ 检测到循环依赖: " + str(self._dependency_stack))
            self._dependency_stack.append(meta.name)

            await self._set_module_state(meta.name, ModuleState.LOADING)
            config = config or {}
            dependencies = meta.dependencies or []
            deps_to_load = [dep for dep in dependencies if dep not in self.modules]

            logging.info("✅ 第一阶段加载完成")

        # 第二阶段：依赖加载（无锁状态）
        loaded_deps = []
        try:
            for dep_name in deps_to_load:
                dep_meta = ModuleMeta.from_yaml(f"modules/{dep_name}/config.yaml")
                await self.load_module(dep_meta)
                loaded_deps.append(dep_name)
            logging.info(
                "✅ 第二阶段加载完成，依赖模块: {}".format(",".join(loaded_deps))
            )
        except Exception as e:
            logging.error(f"❌ 依赖加载失败: {dep_name} -> {e}")
            # 回滚已加载依赖
            async with self.lock:
                for dep in loaded_deps:
                    await self._safe_unload_module(dep)
            raise
        finally:
            async with self.lock:
                if meta.name in self._dependency_stack:
                    self._dependency_stack.remove(meta.name)

        # 第三阶段：主模块加载
        async with self.lock:
            if meta.name in self.modules:  # 二次检查
                return

            try:
                # 模块实例化：若模块实现 from_config 则调用异步初始化
                entry_class = meta.load_entry_class()
                if hasattr(entry_class, "from_config"):
                    instance = await entry_class.from_config(config)
                else:
                    instance = entry_class(self.message_bus)

                # 消息处理器注册（如果未通过实例化过程注册则注册）
                if hasattr(instance, "handle_message"):
                    config_name = config.get("name", meta.name)
                    self._register_handler(instance.handle_message, config_name)

                # 路由注册
                config_name = config.get("name", meta.name)
                self._register_route(config_name)

                self.modules[meta.name] = instance
                await self._set_module_state(meta.name, ModuleState.RUNNING)
                await self.message_bus.publish_event(
                    "MODULE_LOADED", meta.name.encode()
                )

                logging.info("✅ 第三阶段加载完成")

            except Exception as e:
                logging.error(f"❌ 主模块加载失败: {e}")
                await self._set_module_state(meta.name, ModuleState.ERROR)
                raise

    def _register_handler(self, handler, config_name: str):
        """安全注册消息处理器"""
        module_name = config_name
        if module_name in self.message_bus.message_handlers:
            logging.warning(f"⚠️ 处理器 {module_name} 已存在，跳过注册")
            return  # 直接返回，不抛出异常

        if asyncio.iscoroutinefunction(handler):

            def wrapper(env, h=handler):
                return asyncio.create_task(h(env))

        else:
            wrapper = handler

        self.message_bus.register_handler(module_name, wrapper)
        logging.info(
            f"🆕 注册处理器: {module_name} ({'异步' if asyncio.iscoroutinefunction(handler) else '同步'})"
        )

    def _register_route(self, config_name: str):
        """安全注册路由"""
        route_name = config_name
        module_address = f"ipc:///tmp/{config_name}_socket"

        if self.message_bus.get_route(route_name):
            raise ValueError(f"路由 {route_name} 已存在")

        self.message_bus.register_route(route_name, module_address)
        logging.info(f"🆕 注册路由: {route_name} -> {module_address}")

    async def _safe_unload_module(self, module_name: str):
        """安全卸载模块（需在锁保护下调用）"""
        logging.info(f"🚀 开始卸载模块: {module_name}")
        if module_name not in self.modules:
            logging.warning(f"⚠️ 模块 {module_name} 未加载")
            return

        await self._set_module_state(module_name, ModuleState.STOPPING)
        instance = self.modules[module_name]

        try:
            if hasattr(instance, "pre_unload"):
                await instance.pre_unload()
        except Exception as e:
            logging.error(f"❌ 预卸载失败: {module_name} -> {e}")

        # 清理资源
        self.message_bus.unregister_handler(f"{module_name}_socket")
        self.message_bus.unregister_route(module_name)

        try:
            if hasattr(instance, "post_unload"):
                await instance.post_unload()
        except Exception as e:
            logging.error(f"❌ 后卸载失败: {module_name} -> {e}")

        del self.modules[module_name]
        del self.module_states[module_name]
        logging.info(f"✅ 模块 {module_name} 已卸载")
        await self.message_bus.publish_event("MODULE_UNLOADED", module_name.encode())

    async def unload_module(self, module_name: str):
        logging.info(f"🚀 开始卸载模块: {module_name}")
        async with self.lock:
            await self._safe_unload_module(module_name)
        logging.info(f"✅ 模块 {module_name} 卸载完成")

    def get_module(self, name: str) -> object:
        return self.modules.get(name.replace("_socket", ""))

    async def start_heartbeat(self, interval: int = 3):
        """优化后的心跳检测"""
        while True:
            # 快速获取模块快照
            async with self.lock:
                modules = list(self.modules.items())

            # 并行检测心跳
            tasks = [
                self._check_heartbeat(name, instance) for name, instance in modules
            ]
            await asyncio.gather(*tasks)

            await asyncio.sleep(interval)

    async def _check_heartbeat(self, name: str, instance: object):
        """带超时的心跳检测"""
        try:
            if hasattr(instance, "heartbeat"):
                await asyncio.wait_for(instance.heartbeat(), timeout=5)
        except asyncio.TimeoutError:
            logging.warning(f"⌛ 心跳超时: {name}")
            await self.unload_module(name)
        except asyncio.CancelledError:
            logging.warning(f"⚠️ 心跳检测被取消: {name}")
        except Exception as e:
            logging.error(f"❌ 心跳异常: {name} -> {e}")
            await self.unload_module(name)
