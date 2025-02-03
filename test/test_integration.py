'''
Author: @ydzat
Date: 2025-01-31 22:55:05
LastEditors: @ydzat
LastEditTime: 2025-02-01 03:57:18
Description: 
'''
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
import time
import zmq
from core.message_bus import MessageBus
from core.module_manager import ModuleManager
from core.module_meta import ModuleMeta
from core.generated import message_pb2 as proto

@pytest.fixture
def system():
    bus = MessageBus()
    bus.start_message_loop()  # 启动消息循环
    bus.cmd_socket.setsockopt(zmq.RCVTIMEO, 1000)  # 设置1秒接收超时
    manager = ModuleManager(bus)
    
    # 预加载echo模块
    meta = ModuleMeta.from_yaml("modules/echo_module/manifest.yaml")
    manager.load_module(meta)
    
    yield bus, manager
    
    # 清理
    bus.stop_message_loop()
    bus.context.destroy()
    time.sleep(0.1)  # 等待资源释放

@pytest.mark.timeout(10)  # 设置10秒超时
def test_echo_workflow(system):
    bus, manager = system
    start_time = time.time()
    
    # 清理已加载模块
    if manager.get_module("echo_module"):
        manager.unload_module("echo_module")
        bus.unregister_handler("echo_module")

    print("\n[DEBUG] Starting test workflow")
    
    # 加载示例模块
    print("[DEBUG] Loading echo module")
    meta = ModuleMeta.from_yaml("modules/echo_module/manifest.yaml")
    manager.load_module(meta)
    
    # 检查模块加载状态
    print(f"[DEBUG] Module states: {manager.module_states}")
    
    # 等待模块初始化完成
    print("[DEBUG] Waiting for module initialization")
    time.sleep(0.5)
    
    # 发送测试消息
    print("[DEBUG] Sending test message")
    test_payload = b"Hello World"
    envelope = bus.send_command("echo_module", "ECHO", test_payload)
    print(f"[DEBUG] Sent message ID: {envelope.header.msg_id}")
    
    # 接收响应
    print("[DEBUG] Waiting for response")
    poller = zmq.Poller()
    poller.register(bus.cmd_socket, zmq.POLLIN)
    socks = dict(poller.poll(5000))  # 最多等待5秒
    if bus.cmd_socket in socks and socks[bus.cmd_socket] == zmq.POLLIN:
        # ROUTER socket返回多帧消息：[identity, empty, message]
        response = bus.cmd_socket.recv_multipart()
        if len(response) != 3:
            raise ValueError(f"Invalid response format: {response}")
        parsed = proto.Envelope()
        parsed.ParseFromString(response[2])
    else:
        raise TimeoutError("未收到来自 echo_module 的响应")
    
    # 将结果保存到本地/tmp目录
    print("[DEBUG] Saving result to /tmp/test_result.txt")
    with open("/tmp/test_result.txt", "wb") as f:
        f.write(parsed.body.payload)
    
    print("[DEBUG] Asserting results")
    assert parsed.body.payload == test_payload
    assert parsed.header.msg_id == envelope.header.msg_id
    
    print("[DEBUG] Test completed successfully")

def test_error_handling(system):
    """测试错误命令处理"""
    bus, manager = system
    
    # 发送不支持的命令
    with pytest.raises(ValueError):
        bus.send_command("echo_module", "INVALID_CMD", b"test")
    
    # 发送错误类型的消息
    envelope = proto.Envelope()
    envelope.body.type = proto.MessageType.DATA_STREAM
    with pytest.raises(ValueError):
        bus.send_envelope("echo_module", envelope)

def test_large_message(system):
    """测试大消息处理"""
    bus, manager = system
    
    # 生成1MB的测试数据
    large_payload = os.urandom(1024 * 1024)
    
    # 发送并验证
    envelope = bus.send_command("echo_module", "ECHO", large_payload)
    poller = zmq.Poller()
    poller.register(bus.cmd_socket, zmq.POLLIN)
    socks = dict(poller.poll(5000))
    
    if bus.cmd_socket in socks and socks[bus.cmd_socket] == zmq.POLLIN:
        response = bus.cmd_socket.recv_multipart()
        parsed = proto.Envelope()
        parsed.ParseFromString(response[2])
        assert parsed.body.payload == large_payload
    else:
        raise TimeoutError("未收到大消息响应")

def test_timeout_handling(system):
    """测试超时处理"""
    bus, manager = system
    
    # 设置超时时间为100ms
    bus.cmd_socket.setsockopt(zmq.RCVTIMEO, 100)
    
    # 发送命令但不等待响应
    bus.send_command("echo_module", "ECHO", b"test")
    
    # 验证超时
    with pytest.raises(zmq.error.Again):
        bus.cmd_socket.recv_multipart()

def test_module_reloading(system):
    """测试模块重载"""
    bus, manager = system
    
    # 初始加载
    meta = ModuleMeta.from_yaml("modules/echo_module/manifest.yaml")
    manager.load_module(meta)
    
    # 卸载模块
    manager.unload_module("echo_module")
    
    # 重新加载
    manager.load_module(meta)
    
    # 测试功能是否正常
    test_payload = b"Reload test"
    envelope = bus.send_command("echo_module", "ECHO", test_payload)
    
    poller = zmq.Poller()
    poller.register(bus.cmd_socket, zmq.POLLIN)
    socks = dict(poller.poll(5000))
    
    if bus.cmd_socket in socks and socks[bus.cmd_socket] == zmq.POLLIN:
        response = bus.cmd_socket.recv_multipart()
        parsed = proto.Envelope()
        parsed.ParseFromString(response[2])
        assert parsed.body.payload == test_payload
    else:
        raise TimeoutError("未收到重载模块的响应")

def test_concurrent_requests(system):
    """测试并发请求处理"""
    bus, manager = system
    
    # 发送5个并发请求
    test_payloads = [b"test1", b"test2", b"test3", b"test4", b"test5"]
    envelopes = [bus.send_command("echo_module", "ECHO", payload) for payload in test_payloads]
    
    # 接收所有响应
    responses = []
    for _ in range(5):
        poller = zmq.Poller()
        poller.register(bus.cmd_socket, zmq.POLLIN)
        socks = dict(poller.poll(5000))
        
        if bus.cmd_socket in socks and socks[bus.cmd_socket] == zmq.POLLIN:
            response = bus.cmd_socket.recv_multipart()
            parsed = proto.Envelope()
            parsed.ParseFromString(response[2])
            responses.append(parsed)
        else:
            raise TimeoutError("未收到并发请求的响应")
    
    # 验证响应
    received_payloads = [resp.body.payload for resp in responses]
    assert sorted(received_payloads) == sorted(test_payloads)
