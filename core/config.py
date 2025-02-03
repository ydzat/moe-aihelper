'''
Author: @ydzat
Date: 2025-01-31 23:30:00
LastEditors: @ydzat
LastEditTime: 2025-01-31 23:28:25
Description: Configuration center implementation
'''

class ConfigCenter:
    def __init__(self):
        self._config = {}
        
    def load_config(self, config_path: str):
        """Load configuration from file"""
        # TODO: Implement configuration loading
        pass
        
    def get(self, key: str, default=None):
        """Get configuration value"""
        return self._config.get(key, default)
        
    def set(self, key: str, value):
        """Set configuration value"""
        self._config[key] = value
