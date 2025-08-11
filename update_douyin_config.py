#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音配置更新脚本
从_conf_schema.json中读取抖音cookie并更新到config.yaml中
"""

import os
import json
import yaml
from pathlib import Path
from typing import Optional


def load_actual_config() -> Optional[dict]:
    """
    加载实际的配置文件
    
    Returns:
        配置字典，如果加载失败返回None
    """
    try:
        # 尝试从data/config目录加载配置文件
        config_path = Path(__file__).parent.parent.parent / "config" / "so-vits-svc-api_config.json"
        if not config_path.exists():
            # 如果不存在，尝试从插件目录加载
            config_path = Path(__file__).parent / "config.json"
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print(f"配置文件不存在: {config_path}")
            return None
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return None


def get_douyin_cookie_from_config(config: dict) -> Optional[str]:
    """
    从实际配置中提取抖音cookie
    
    Args:
        config: 实际配置字典
        
    Returns:
        抖音cookie字符串，如果没有找到返回None
    """
    try:
        # 从base_setting中获取douyin_cookie
        base_setting = config.get("base_setting", {})
        douyin_cookie = base_setting.get("douyin_cookie", "")
        
        if douyin_cookie:
            print(f"从配置文件中读取到抖音cookie: {douyin_cookie[:50]}...")
            return douyin_cookie
        else:
            print("在配置文件中没有找到抖音cookie配置")
            return None
            
    except Exception as e:
        print(f"提取抖音cookie失败: {e}")
        return None


def load_config_yaml() -> Optional[dict]:
    """
    加载config.yaml配置文件
    
    Returns:
        配置字典，如果加载失败返回None
    """
    try:
        config_path = Path(__file__).parent / "DouYin" / "douyin" / "web" / "config.yaml"
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"加载config.yaml失败: {e}")
        return None


def update_config_yaml(config: dict, douyin_cookie: str) -> bool:
    """
    更新config.yaml中的抖音cookie
    
    Args:
        config: 当前配置字典
        douyin_cookie: 新的抖音cookie
        
    Returns:
        更新是否成功
    """
    try:
        # 更新TokenManager.douyin.headers.Cookie
        if "TokenManager" in config and "douyin" in config["TokenManager"]:
            if "headers" not in config["TokenManager"]["douyin"]:
                config["TokenManager"]["douyin"]["headers"] = {}
            
            config["TokenManager"]["douyin"]["headers"]["Cookie"] = douyin_cookie
            print("成功更新config.yaml中的抖音cookie")
            return True
        else:
            print("config.yaml中缺少TokenManager.douyin配置结构")
            return False
            
    except Exception as e:
        print(f"更新config.yaml失败: {e}")
        return False


def save_config_yaml(config: dict) -> bool:
    """
    保存更新后的config.yaml文件
    
    Args:
        config: 要保存的配置字典
        
    Returns:
        保存是否成功
    """
    try:
        config_path = Path(__file__).parent / "DouYin" / "douyin" / "web" / "config.yaml"
        
        # 创建备份
        backup_path = config_path.with_suffix('.yaml.backup')
        if config_path.exists():
            import shutil
            shutil.copy2(config_path, backup_path)
            print(f"已创建备份文件: {backup_path}")
        
        # 保存新配置
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        print(f"成功保存更新后的config.yaml: {config_path}")
        return True
        
    except Exception as e:
        print(f"保存config.yaml失败: {e}")
        return False


def main():
    """
    主函数：执行配置更新流程
    """
    print("开始更新抖音配置...")
    
    # 1. 加载实际配置文件
    config = load_actual_config()
    if not config:
        print("无法加载配置文件，退出")
        return False
    
    # 2. 提取抖音cookie
    douyin_cookie = get_douyin_cookie_from_config(config)
    if not douyin_cookie:
        print("没有找到抖音cookie，退出")
        return False
    
    # 3. 加载config.yaml
    config = load_config_yaml()
    if not config:
        print("无法加载config.yaml，退出")
        return False
    
    # 4. 更新配置
    if not update_config_yaml(config, douyin_cookie):
        print("更新配置失败，退出")
        return False
    
    # 5. 保存配置
    if not save_config_yaml(config):
        print("保存配置失败，退出")
        return False
    
    print("抖音配置更新完成！")
    return True


if __name__ == "__main__":
    main()
