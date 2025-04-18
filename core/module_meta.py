'''
Author: @ydzat
Date: 2025-02-02 12:17:07
LastEditors: @ydzat
LastEditTime: 2025-02-03 22:40:41
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

from dataclasses import dataclass
from typing import Dict, List, Optional
import importlib
import sys
from pathlib import Path


@dataclass
class ModuleMeta:
    name: str  # 模块唯一标识
    version: str  # 语义版本号
    entry_point: str  # 入口类路径 (e.g. "my_module.core:MainClass")
    dependencies: List[str]  # 依赖模块列表
    capabilities: List[str] = None  # 模块能力列表
    required_resources: Dict[str, float] = (
        None  # 资源需求 {"cpu": 0.5, "gpu_mem": 1024}
    )
    config_schema: Dict = None  # 配置验证schema

    @classmethod
    def from_yaml(cls, path: str):
        """从YAML文件加载元数据"""
        import yaml
        from pathlib import Path

        # 转换为绝对路径
        full_path = Path(path).resolve()
        if not full_path.exists():
            raise FileNotFoundError(f"Manifest file not found: {full_path}")

        with open(full_path) as f:
            data = yaml.safe_load(f)
            return cls(**data)

    def load_entry_class(self):
        """动态加载入口类"""
        module_path, class_name = self.entry_point.split(":")

        # 添加模块根目录到sys.path
        module_root = str(Path(__file__).parent.parent.resolve())
        if module_root not in sys.path:
            sys.path.append(module_root)

        # 使用完整模块路径
        full_module_path = f"modules.{module_path}"
        module = importlib.import_module(full_module_path)

        # 获取模块中的类
        entry_class = getattr(module, class_name)

        return entry_class
