'''
Author: @ydzat
Date: 2025-01-31 22:53:49
LastEditors: @ydzat
LastEditTime: 2025-01-31 22:53:54
Description: 
'''
import psutil
import pynvml
from typing import Dict, Optional

class ResourceMonitor:
    def __init__(self):
        self.gpu_available = False
        try:
            pynvml.nvmlInit()
            self.gpu_available = True
        except:
            pass

    def get_cpu_usage(self) -> float:
        """获取CPU使用率（0.0-1.0）"""
        return psutil.cpu_percent(interval=0.1) / 100

    def get_memory_usage(self) -> Dict[str, float]:
        """获取内存使用情况（单位：MB）"""
        mem = psutil.virtual_memory()
        return {
            "total": mem.total / 1024**2,
            "used": mem.used / 1024**2,
            "free": mem.free / 1024**2
        }

    def get_gpu_status(self) -> Optional[Dict]:
        """获取GPU状态"""
        if not self.gpu_available:
            return None
            
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        
        return {
            "gpu_util": util.gpu,
            "mem_used": mem.used / 1024**2,
            "mem_total": mem.total / 1024**2
        }