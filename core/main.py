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

import sys
import logging
import asyncio
from pathlib import Path
import zmq
from core.message_bus import MessageBus
from core.module_manager import ModuleManager
from core.module_meta import ModuleMeta
from core.scheduler import ResourceScheduler
from core.config import ConfigCenter
from core.generated import message_pb2 as proto

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 确保模块目录可被发现
MODULES_DIR = PROJECT_ROOT / "modules"
sys.path.insert(0, str(MODULES_DIR))

# 在导入之后添加AGPL合规检测函数
def check_agpl_compliance():
    # 在核心服务启动时检测AGPL合规
    print("""
    AGPL-3.0 合规提示：
    您正在以网络服务形式运行本程序，根据协议第13条要求，必须向用户提供源代码获取方式，包括：
    - 在服务界面显著位置提供源码下载链接
    - 对注册用户发送包含源码仓库地址的邮件
          
    AGPL-3.0 Compliance Notice:
    You are running this program as a network service. According to Section 13 of the license, you must provide users with a way to obtain the source code, including:
    - Providing a prominent source code download link on the service interface.
    - Sending an email containing the source code repository address to registered users.
    """)


async def main():
    logging.basicConfig(level=logging.DEBUG)
    check_agpl_compliance()  # 调用合规检测函数

    # 初始化核心组件
    bus = MessageBus()
    config = ConfigCenter()
    scheduler = ResourceScheduler()
    manager = ModuleManager(bus)

    logging.info("开始启动核心系统...")

    # 启动消息总线的异步事件循环
    asyncio.create_task(bus.start_message_loop())

    # 等待消息循环完全启动
    await asyncio.sleep(1)

    # 加载模块前确保消息总线就绪
    for _ in range(10):  # 最多等待1秒
        if bus._message_loop_running:
            break
        await asyncio.sleep(0.1)

    if not bus._message_loop_running:
        logging.error("❌ 消息总线启动失败")
        return

    logging.info("🔄 加载模块")
    # 加载基础模块
    try:
        echo_meta = ModuleMeta.from_yaml("modules/echo_module/config.yaml")
        if not await scheduler.allocate(
            echo_meta.name, {}
        ):  # ✅ 修改 allocate() 为异步方法
            logging.error("❌ 资源不足，无法加载模块")
            return

        await manager.load_module(echo_meta, config)

    except Exception as e:
        logging.error(f"❌ 模块加载失败: {e}")
        raise e

    logging.info("✅ 核心系统启动完成，等待消息...")

    last_log_time = 0  # 记录上次打印 "正在监听" 的时间
    quiet_mode = True  # 是否处于静默模式

    while True:
        try:
            current_time = asyncio.get_event_loop().time()

            try:
                raw_msg = await bus.cmd_socket.recv_multipart(flags=zmq.NOBLOCK)
                # 收到消息时，切换到非静默模式
                quiet_mode = False
                envelope = proto.Envelope()
                envelope.ParseFromString(raw_msg[2])
                logging.info(f"📩 监听到消息: {envelope}")

                # 路由消息
                target = envelope.header.route[0]
                module = manager.get_module(target)

                if module:
                    response = await module.handle_message(envelope)
                    if isinstance(response, proto.Envelope):
                        retry_count = 0
                        while retry_count < 3:
                            try:
                                await bus.cmd_socket.send_multipart(
                                    [raw_msg[0], b"", response.SerializeToString()],
                                    flags=zmq.NOBLOCK,
                                )
                                break
                            except zmq.Again:
                                retry_count += 1
                                await asyncio.sleep(0.1 * retry_count)
                        if retry_count == 3:
                            logging.error("发送响应失败，达到最大重试次数")

            except zmq.Again:
                # 没有消息时，使用静默模式的日志
                if quiet_mode and current_time - last_log_time >= 1:
                    logging.info("🎧 正在监听消息通道...")
                    last_log_time = current_time
                await asyncio.sleep(0.01)
                quiet_mode = True  # 重置为静默模式
            except asyncio.TimeoutError:
                quiet_mode = True  # 超时时也重置为静默模式
                await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.error(f"❌ 处理消息时出错: {e}")
            await asyncio.sleep(1)  # ✅ 避免日志过多


if __name__ == "__main__":
    asyncio.run(main())
