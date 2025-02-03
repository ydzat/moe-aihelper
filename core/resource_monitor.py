import psutil
import pynvml
import asyncio
from typing import Dict, Optional


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
            handle = await asyncio.to_thread(pynvml.nvmlDeviceGetHandleByIndex, 0)
            util = await asyncio.to_thread(pynvml.nvmlDeviceGetUtilizationRates, handle)
            mem = await asyncio.to_thread(pynvml.nvmlDeviceGetMemoryInfo, handle)

        return {
            "gpu_util": util.gpu,
            "mem_used": mem.used / 1024**2,
            "mem_total": mem.total / 1024**2,
        }
