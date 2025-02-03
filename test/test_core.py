'''
Author: @ydzat
Date: 2025-01-31 22:49:11
LastEditors: @ydzat
LastEditTime: 2025-01-31 22:49:21
Description: 
'''
# tests/test_core.py
def test_core_initialization():
    from core import message_bus
    assert message_bus.ZMQ_VERSION >= (4, 3, 4)