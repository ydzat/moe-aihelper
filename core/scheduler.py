'''
Author: @ydzat
Date: 2025-01-31 22:54:01
LastEditors: @ydzat
LastEditTime: 2025-01-31 23:43:17
Description: 
'''
from typing import Dict
from .resource_monitor import ResourceMonitor

class ResourceScheduler:
    def __init__(self):
        self.monitor = ResourceMonitor()
        self.allocations = {}  # 模块资源分配记录
        self.task_queue = []  # 任务队列
        self.running_tasks = {}  # 运行中的任务
        self.lock = threading.Lock()
    
    def allocate(self, module_name: str, request: Dict) -> bool:
        """分配资源"""
        current_usage = self._get_current_usage()
        
        # CPU检查
        cpu_request = request.get("cpu", 0)
        if current_usage["cpu"] + cpu_request > 0.9:  # 不超过90%
            return False
            
        # GPU内存检查
        gpu_request = request.get("gpu_mem", 0)
        if gpu_request > 0:
            gpu_status = self.monitor.get_gpu_status()
            if not gpu_status:
                return False
            
            # 动态分配策略
            total_mem = gpu_status["mem_total"]
            used_mem = gpu_status["mem_used"]
            reserved = min(1024, total_mem - used_mem)  # 预留1GB基础
            allocatable = (total_mem - used_mem - reserved) * 0.8
            
            if gpu_request > allocatable:
                return False
        
        # 记录分配
        self.allocations[module_name] = request
        return True

    def _get_current_usage(self) -> Dict:
        """计算当前资源使用"""
        total = {"cpu": 0.0, "gpu_mem": 0.0}
        for req in self.allocations.values():
            total["cpu"] += req.get("cpu", 0)
            total["gpu_mem"] += req.get("gpu_mem", 0)
        return total

    def add_task(self, task_id: str, task: Dict):
        """添加任务到队列"""
        with self.lock:
            self.task_queue.append((task_id, task))
            self.task_queue.sort(key=lambda x: x[1].get("priority", 0), reverse=True)

    def _schedule_next(self):
        """调度下一个任务"""
        with self.lock:
            if not self.task_queue:
                return None
            
            # 获取最高优先级任务
            task_id, task = self.task_queue.pop(0)
            
            # 检查资源是否足够
            if self.allocate(task_id, task.get("resources", {})):
                self.running_tasks[task_id] = task
                return task_id
            else:
                # 资源不足，放回队列
                self.task_queue.insert(0, (task_id, task))
                return None

    def task_completed(self, task_id: str):
        """任务完成回调"""
        with self.lock:
            if task_id in self.running_tasks:
                task = self.running_tasks.pop(task_id)
                # 释放资源
                if task_id in self.allocations:
                    del self.allocations[task_id]
                # 调度下一个任务
                self._schedule_next()
