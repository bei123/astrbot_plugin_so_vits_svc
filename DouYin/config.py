"""
抖音音频下载器配置文件
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional


class DownloaderConfig:
    """下载器配置类"""
    
    def __init__(self, config_file: str = "downloader_config.json"):
        """
        初始化配置
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = Path(config_file)
        self.config = self._load_default_config()
        self._load_config()
    
    def _load_default_config(self) -> Dict[str, Any]:
        """加载默认配置"""
        return {
            # 基本设置
            "output_dir": "downloads",
            "max_retries": 3,
            "timeout": 30,
            
            # 网络设置
            "proxies": None,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            
            # 下载设置
            "max_concurrent_downloads": 5,
            "chunk_size": 8192,  # 下载块大小
            "skip_existing": True,  # 跳过已存在的文件
            
            # 文件设置
            "file_extension": ".mp3",
            "max_filename_length": 100,
            "allowed_filename_chars": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_ ",
            
            # 日志设置
            "log_level": "INFO",
            "log_file": "downloader.log",
            "log_format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            
            # 性能设置
            "connection_pool_size": 100,
            "max_connections_per_host": 30,
            "keepalive_timeout": 30,
            
            # 重试设置
            "retry_delay": 1,  # 基础重试延迟（秒）
            "retry_backoff": 2,  # 重试延迟倍数
            "max_retry_delay": 60,  # 最大重试延迟（秒）
            
            # 缓存设置
            "enable_cache": True,
            "cache_dir": ".cache",
            "cache_expire": 3600,  # 缓存过期时间（秒）
            
            # 安全设置
            "verify_ssl": True,
            "max_redirects": 10,
            "allow_insecure": False,
        }
    
    def _load_config(self):
        """从文件加载配置"""
        if self.config_file.exists():
            try:
                import json
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
                self.config.update(file_config)
            except Exception as e:
                print(f"加载配置文件失败: {e}")
    
    def save_config(self):
        """保存配置到文件"""
        try:
            import json
            self.config_file.parent.mkdir(exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置文件失败: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """设置配置值"""
        self.config[key] = value
    
    def update(self, config_dict: Dict[str, Any]):
        """更新配置"""
        self.config.update(config_dict)
    
    def get_downloader_kwargs(self) -> Dict[str, Any]:
        """获取下载器初始化参数"""
        return {
            'output_dir': self.get('output_dir'),
            'proxies': self.get('proxies'),
            'max_retries': self.get('max_retries'),
            'timeout': self.get('timeout'),
        }
    
    def get_session_kwargs(self) -> Dict[str, Any]:
        """获取会话初始化参数"""
        return {
            'headers': {
                'User-Agent': self.get('user_agent'),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            'timeout': self.get('timeout'),
            'connector': {
                'limit': self.get('connection_pool_size'),
                'limit_per_host': self.get('max_connections_per_host'),
                'keepalive_timeout': self.get('keepalive_timeout'),
            },
            'verify_ssl': self.get('verify_ssl'),
            'max_redirects': self.get('max_redirects'),
        }


# 全局配置实例
config = DownloaderConfig()


def get_config() -> DownloaderConfig:
    """获取全局配置实例"""
    return config


def update_config(config_dict: Dict[str, Any]):
    """更新全局配置"""
    config.update(config_dict)


def save_global_config():
    """保存全局配置"""
    config.save_config()


# 环境变量配置
def load_from_env():
    """从环境变量加载配置"""
    env_mapping = {
        'DOUYIN_OUTPUT_DIR': 'output_dir',
        'DOUYIN_MAX_RETRIES': 'max_retries',
        'DOUYIN_TIMEOUT': 'timeout',
        'DOUYIN_LOG_LEVEL': 'log_level',
        'DOUYIN_PROXY_HTTP': 'proxies.http',
        'DOUYIN_PROXY_HTTPS': 'proxies.https',
    }
    
    for env_key, config_key in env_mapping.items():
        env_value = os.getenv(env_key)
        if env_value is not None:
            if config_key == 'max_retries':
                config.set(config_key, int(env_value))
            elif config_key == 'timeout':
                config.set(config_key, int(env_value))
            elif config_key.startswith('proxies.'):
                proxy_type = config_key.split('.')[1]
                if config.get('proxies') is None:
                    config.set('proxies', {})
                config.config['proxies'][proxy_type] = env_value
            else:
                config.set(config_key, env_value)


# 自动加载环境变量配置
load_from_env()


# 便捷函数
def get_output_dir() -> str:
    """获取输出目录"""
    return config.get('output_dir', 'downloads')


def get_proxies() -> Optional[Dict[str, str]]:
    """获取代理设置"""
    return config.get('proxies')


def get_timeout() -> int:
    """获取超时时间"""
    return config.get('timeout', 30)


def get_max_retries() -> int:
    """获取最大重试次数"""
    return config.get('max_retries', 3)


def get_log_level() -> str:
    """获取日志级别"""
    return config.get('log_level', 'INFO')


# 配置验证
def validate_config() -> bool:
    """验证配置有效性"""
    try:
        # 检查输出目录
        output_dir = config.get('output_dir')
        if not output_dir:
            print("错误: 输出目录不能为空")
            return False
        
        # 检查超时时间
        timeout = config.get('timeout')
        if timeout <= 0:
            print("错误: 超时时间必须大于0")
            return False
        
        # 检查重试次数
        max_retries = config.get('max_retries')
        if max_retries < 0:
            print("错误: 重试次数不能为负数")
            return False
        
        # 检查并发数
        max_concurrent = config.get('max_concurrent_downloads')
        if max_concurrent <= 0:
            print("错误: 并发下载数必须大于0")
            return False
        
        return True
        
    except Exception as e:
        print(f"配置验证失败: {e}")
        return False


# 初始化时验证配置
if not validate_config():
    print("警告: 配置验证失败，使用默认配置")
