"""
Author: @ydzat
Date: 2025-01-31 23:30:00
LastEditors: @ydzat
LastEditTime: 2025-01-31 23:28:25
Description: Configuration center implementation
"""

import yaml
from pathlib import Path


class ConfigCenter:
    def __init__(self):
        self.core_config_path = (
            Path(__file__).resolve().parent / "core_config.yaml"
        )  # 核心配置文件路径
        self._config = {}  # 初始化 _config 变量

    def get_core_config(self) -> dict:
        """获取核心配置"""
        if not self.core_config_path.exists():
            # 配置文件不存在时生成默认配置
            default_config = {"logging_level": "INFO", "max_retries": 3, "timeout": 30}
            with open(self.core_config_path, "w") as f:
                yaml.safe_dump(default_config, f)
            return default_config

        with open(self.core_config_path) as f:
            return yaml.safe_load(f)

    def get_module_config(self, module_name: str) -> dict:
        """获取指定模块的配置"""
        module_config_path = (
            Path(__file__).resolve().parent.parent
            / "modules"
            / module_name
            / "config.yaml"
        )
        if not module_config_path.exists():
            raise FileNotFoundError(
                f"Module config file not found: {module_config_path}"
            )

        with open(module_config_path) as f:
            return yaml.safe_load(f)

    def load_config(self, config_path: str):
        """Load configuration from file"""
        # TODO: Implement configuration loading
        pass

    def get(self, key: str, default=None):
        """Get configuration value"""
        return self._config.get(key, default)

    def set(self, key: str, value):
        """Set configuration value"""
        self._config[key] = value
