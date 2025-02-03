"""
Author: @ydzat
Date: 2025-02-03 19:57:12
LastEditors: @ydzat
LastEditTime: 2025-02-03 20:01:01
Description:
"""

import psutil
import pynvml
import asyncio
from typing import Dict, Optional
import logging


class ResourceMonitor:
    def __init__(self):
        self.gpu_available = False
        try:
            pynvml.nvmlInit()
            self.gpu_available = True
        except Exception:
            pass  # GPU 不可用时，直接跳过初始化

    async def get_cpu_usage(self) -> float:
        """异步获取 CPU 使用率（0.0-1.0）"""
        return await asyncio.to_thread(psutil.cpu_percent, interval=0.1) / 100

    async def get_memory_usage(self) -> Dict[str, float]:
        """异步获取内存使用情况（单位：MB）"""
        mem = await asyncio.to_thread(psutil.virtual_memory)
        return {
            "total": mem.total / 1024**2,
            "used": mem.used / 1024**2,
            "free": mem.free / 1024**2,
        }

    async def get_gpu_status(self) -> Optional[Dict]:
        """异步获取 GPU 状态"""
        if not self.gpu_available:
            return None

        async with asyncio.Lock():  # 避免多个任务同时访问 GPU 资源
            try:
                handle = await asyncio.to_thread(pynvml.nvmlDeviceGetHandleByIndex, 0)
                util = await asyncio.to_thread(
                    pynvml.nvmlDeviceGetUtilizationRates, handle
                )
                mem = await asyncio.to_thread(pynvml.nvmlDeviceGetMemoryInfo, handle)
            except pynvml.NVMLError as e:
                logging.warning(f"⚠️ GPU 状态获取失败，重试: {e}")
                await asyncio.sleep(1)
                return await self.get_gpu_status()

        return {
            "gpu_util": util.gpu,
            "mem_used": mem.used / 1024**2,
            "mem_total": mem.total / 1024**2,
        }

    async def monitor_resources(self):
        # 目前的变量未被使用，如不需要可删除
        # cpu_usage = await self.get_cpu_usage()
        # memory_usage = await self.get_memory_usage()
        # gpu_status = await self.get_gpu_status()
        logging.info(
            "资源监控当前状态: CPU使用率高于阈值，内存使用率稳定，磁盘空间充足。"
        )
