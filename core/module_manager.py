'''
Author: @ydzat
Date: 2025-01-31 22:53:34
LastEditors: @ydzat
LastEditTime: 2025-02-01 01:24:27
Description: 
'''
import logging
import threading
import time
from typing import Dict
from enum import Enum, auto
from .module_meta import ModuleMeta
from .message_bus import MessageBus

class ModuleState(Enum):
    """模块状态"""
    LOADING = auto()
    RUNNING = auto()
    STOPPING = auto()
    ERROR = auto()

class ModuleManager:
    def __init__(self, message_bus: MessageBus):
        self.modules: Dict[str, object] = {}  # 加载的模块实例
        self.module_states = {}  # 模块状态记录
        self.message_bus = message_bus
        self.lock = threading.RLock()  # 使用可重入锁
        
    @property
    def loaded_modules(self) -> Dict[str, object]:
        """获取已加载模块的只读视图"""
        return self.modules.copy()
        
    def _set_module_state(self, module_name: str, state: ModuleState):
        """设置模块状态"""
        try:
            if self.lock.acquire(timeout=5):  # 设置5秒超时
                try:
                    self.module_states[module_name] = state
                    self.message_bus.publish_event(
                        "MODULE_STATE_CHANGED",
                        f"{module_name}:{state.name}".encode()
                    )
                finally:
                    self.lock.release()
            else:
                raise RuntimeError(f"Failed to acquire lock for {module_name}")
        except Exception as e:
            logging.error(f"Failed to set module state: {str(e)}")
            raise

    def get_module_state(self, module_name: str) -> ModuleState:
        """获取模块状态"""
        with self.lock:
            return self.module_states.get(module_name, ModuleState.ERROR)

    def _resolve_dependencies(self, meta: ModuleMeta) -> list:
        """解析模块依赖关系"""
        from collections import deque
        
        # 使用广度优先搜索解析依赖
        dependencies = []
        queue = deque([meta])
        visited = set()
        
        while queue:
            current = queue.popleft()
            if current.name in visited:
                continue
                
            visited.add(current.name)
            
            # 获取依赖模块
            for dep_name in current.dependencies:
                try:
                    dep_meta = ModuleMeta.from_name(dep_name)
                    if dep_meta.name not in visited:
                        queue.append(dep_meta)
                        dependencies.append(dep_meta)
                except Exception as e:
                    raise RuntimeError(f"Failed to resolve dependency {dep_name}: {str(e)}")
                    
        return dependencies

    def _validate_config(self, meta: ModuleMeta, config: dict) -> dict:
        """验证模块配置"""
        if not meta.config_schema:
            return {}
            
        try:
            from jsonschema import validate
            validate(instance=config, schema=meta.config_schema)
            return config
        except Exception as e:
            raise ValueError(f"Invalid config for {meta.name}: {str(e)}")

    def load_module(self, meta: ModuleMeta, config: dict = None):
        """动态加载模块
        Args:
            meta: 模块元数据
            config: 模块配置字典
        """
        with self.lock:
            if meta.name in self.modules:
                raise ValueError(f"Module {meta.name} already loaded")
            
            self._set_module_state(meta.name, ModuleState.LOADING)
            
            # 验证并处理配置
            config = self._validate_config(meta, config or {})
            
            # 解析并加载依赖
            try:
                dependencies = self._resolve_dependencies(meta)
                for dep_meta in dependencies:
                    if dep_meta.name not in self.modules:
                        self.load_module(dep_meta)
            except RuntimeError as e:
                self._set_module_state(meta.name, ModuleState.ERROR)
                raise RuntimeError(f"Dependency resolution failed: {str(e)}")
            
            # 加载入口类并注入配置
            entry_class = meta.load_entry_class()
            try:
                if hasattr(entry_class, "from_config"):
                    instance = entry_class.from_config(config)
                else:
                    instance = entry_class(self.message_bus)
                    if hasattr(instance, "set_config"):
                        instance.set_config(config)
            except Exception as e:
                self._set_module_state(meta.name, ModuleState.ERROR)
                raise RuntimeError(f"Failed to initialize module {meta.name}: {str(e)}")
            
            # 执行初始化
            if hasattr(instance, "pre_init"):
                instance.pre_init()
                
            # 注册模块能力
            if hasattr(instance, "get_capabilities"):
                for capability in instance.get_capabilities():
                    self.message_bus.register_capability(meta.name, capability)
                    
            self.modules[meta.name] = instance
            logging.info(f"Module {meta.name} loaded successfully")
            
            # 执行后初始化
            if hasattr(instance, "post_init"):
                instance.post_init()
                
            # 更新状态
            self._set_module_state(meta.name, ModuleState.RUNNING)
            
            # 发送系统事件
            self.message_bus.publish_event("MODULE_LOADED", meta.name.encode())

    def unload_module(self, module_name: str):
        """卸载模块"""
        with self.lock:
            if module_name not in self.modules:
                return
            
            self._set_module_state(module_name, ModuleState.STOPPING)
            
            instance = self.modules[module_name]
            if hasattr(instance, "pre_unload"):
                instance.pre_unload()
                
            # 清理模块路由
            self.message_bus.unregister_route(module_name)
                
            # 执行后卸载
            if hasattr(instance, "post_unload"):
                instance.post_unload()
                
            del self.modules[module_name]
            logging.info(f"Module {module_name} unloaded")
            self.message_bus.publish_event("MODULE_UNLOADED", module_name.encode())

    def get_module(self, name: str) -> object:
        """获取已加载模块实例"""
        return self.modules.get(name)

    def start_heartbeat(self, interval: int = 3):
        """启动心跳检测"""
        def _heartbeat_loop():
            while True:
                with self.lock:
                    for name, instance in self.modules.items():
                        try:
                            if hasattr(instance, "heartbeat"):
                                instance.heartbeat()
                        except Exception as e:
                            logging.error(f"Heartbeat failed for {name}: {str(e)}")
                            self.unload_module(name)
                
                time.sleep(interval)

        import threading
        thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        thread.start()
