'''
Author: @ydzat
Date: 2025-01-31 22:55:30
LastEditors: @ydzat
LastEditTime: 2025-01-31 23:11:12
Description: 
'''
import sys
import logging
from pathlib import Path
from core.message_bus import MessageBus
from core.module_manager import ModuleManager
from core.module_meta import ModuleMeta
from core.resource_scheduler import ResourceScheduler
from core.config_center import ConfigCenter

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 确保模块目录可被发现
MODULES_DIR = PROJECT_ROOT / "modules"
sys.path.insert(0, str(MODULES_DIR))


def main():
    logging.basicConfig(level=logging.INFO)
    
    # 初始化核心组件
    bus = MessageBus()
    config = ConfigCenter()
    scheduler = ResourceScheduler(config)
    manager = ModuleManager(bus, scheduler)
    
    # 加载基础模块
    try:
        echo_meta = ModuleMeta.from_yaml("modules/echo_module/manifest.yaml")
        if not scheduler.check_resources(echo_meta):
            logging.error("Insufficient resources to load module")
            return
            
        manager.load_module(echo_meta)
        config.register_module(echo_meta.name)
    except Exception as e:
        logging.error(f"Failed to load module: {e}")
        return
    
    # 启动心跳检测
    bus.start_heartbeat()
    
    # 日志
    logging.info("核心系统启动完成，等待消息...")  

    # 主循环
    while True:
        try:
            # 监听命令通道
            logging.debug("监听消息通道...") 
            raw_msg = bus.cmd_socket.recv()
            envelope = proto.Envelope()
            envelope.ParseFromString(raw_msg)
            
            # 路由消息
            target = envelope.header.route[0]
            if module := manager.get_module(target):
                response = module.handle_message(envelope)
                bus.cmd_socket.send(response.SerializeToString())
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.error(f"Error processing message: {e}")

if __name__ == "__main__":
    main()
