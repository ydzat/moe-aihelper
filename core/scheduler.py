"""
Author: @ydzat
Date: 2025-02-02 12:17:07
LastEditors: @ydzat
LastEditTime: 2025-02-03 12:30:00
Description:
"""

import asyncio
from typing import Dict
from core.resource_monitor import ResourceMonitor
import logging
import socket  # 新增导入


class ResourceScheduler:
    def __init__(self):
        self.monitor = ResourceMonitor()
        self.allocations = {}  # 模块资源分配记录
        self.task_queue = []  # 任务队列
        self.running_tasks = {}  # 运行中的任务
        self.lock = asyncio.Lock()  # ✅ 采用 asyncio.Lock() 避免竞争条件

    async def allocate(self, module_name: str, request: Dict) -> bool:
        """异步分配资源"""

        # ✅ 先获取当前资源使用情况，避免 `asyncio.Lock` 死锁
        if self.lock.locked():
            logging.warning(
                "⚠️ allocate() 发现 self.lock 已被占用，等待释放 " + module_name
            )
            await asyncio.sleep(1)  # ✅ 避免立即失败，等待锁释放
            return False

        current_usage = await self._get_current_usage()
        logging.info(f"📊 当前资源使用情况: {current_usage}")

        async with self.lock:
            logging.info(
                f"🚀 `allocate()` 开始，为 `{module_name}` 分配资源: {request}"
            )

            try:
                # CPU检查
                cpu_request = request.get("cpu", 0)
                if current_usage["cpu"] + cpu_request > 0.9:
                    logging.warning(
                        f"⚠️ CPU 资源不足，无法为 `{module_name}` 分配 {cpu_request}"
                    )
                    return False

                # GPU内存检查
                gpu_request = request.get("gpu_mem", 0)
                if gpu_request > 0:
                    logging.info(f"🚀 查询 GPU 状态...")
                    gpu_status = await self.monitor.get_gpu_status()

                    if not gpu_status:
                        logging.warning(
                            f"⚠️ GPU 监控未返回状态，无法分配 `{module_name}`"
                        )
                        return False

                    logging.info(f"✅ 获取到 GPU 状态: {gpu_status}")

                # 记录分配
                self.allocations[module_name] = request
                logging.info(f"✅ 资源分配成功: `{module_name}` -> {request}")
                return True
            except socket.error as e:
                if e.errno == socket.EAGAIN:
                    logging.warning(f"⚠️ 资源暂时不可用，重试 `{module_name}`")
                    await asyncio.sleep(1)
                    return await self.allocate(module_name, request)
                else:
                    logging.error(f"❌ `allocate()` 失败: {e}")
                    return False
            finally:
                logging.info(
                    f"🔓 `allocate()` 释放 `self.lock`，完成 `{module_name}` 分配"
                )

    async def _get_current_usage(self) -> Dict:
        """计算当前资源使用"""
        logging.info("🔍 `_get_current_usage()` 开始查询...")

        total = {"cpu": 0.0, "gpu_mem": 0.0}

        # ✅ **如果 `self.lock.locked()` 为 `True`，说明死锁**
        if self.lock.locked():
            logging.error("❌ `_get_current_usage()` 遇到 `self.lock` 死锁！")
            return total

        async with self.lock:
            logging.info("🔍 `_get_current_usage()` 获取到 `self.lock`，计算中...")
            try:
                for req in self.allocations.values():
                    total["cpu"] += req.get("cpu", 0)
                    total["gpu_mem"] += req.get("gpu_mem", 0)
                logging.info(f"📊 计算的总资源使用情况: {total}")
                return total
            except Exception as e:
                logging.error(f"❌ `_get_current_usage()` 失败: {e}")
                return total

    async def add_task(self, task_id: str, task: Dict):
        """异步添加任务到队列"""
        async with self.lock:
            logging.info(f"📥 添加任务 `{task_id}` 到队列")
            self.task_queue.append((task_id, task))
            self.task_queue.sort(key=lambda x: x[1].get("priority", 0), reverse=True)

    async def _schedule_next(self):
        """异步调度下一个任务"""
        async with self.lock:
            if not self.task_queue:
                logging.info("📭 任务队列为空，调度终止")
                return None

            task_id, task = self.task_queue.pop(0)

            # 检查资源是否足够
            logging.info(
                "🚀 调度任务 {}，尝试分配资源: {}".format(
                    task_id, task.get("resources", {})
                )
            )
            if await self.allocate(task_id, task.get("resources", {})):
                self.running_tasks[task_id] = task
                logging.info("✅ 任务 `{}` 资源分配成功，开始执行".format(task_id))
                return task_id
            else:
                # 资源不足，放回队列
                logging.warning(f"⚠️ 资源不足，任务 `{task_id}` 放回队列")
                self.task_queue.insert(0, (task_id, task))
                return None

    async def task_completed(self, task_id: str):
        """异步任务完成回调"""
        async with self.lock:
            if task_id in self.running_tasks:
                self.running_tasks.pop(task_id)
                logging.info(f"✅ 任务 `{task_id}` 执行完成，释放资源")

                # 释放资源
                if task_id in self.allocations:
                    del self.allocations[task_id]
                await self._schedule_next()
