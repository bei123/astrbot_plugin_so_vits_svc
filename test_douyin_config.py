#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试抖音配置更新功能
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(__file__))

def test_douyin_config():
    """测试抖音配置更新功能"""
    try:
        from update_douyin_config import (
            load_actual_config,
            get_douyin_cookie_from_config,
            load_config_yaml,
            update_config_yaml,
            save_config_yaml
        )
        
        print("=== 测试抖音配置更新功能 ===\n")
        
        # 1. 加载实际配置
        print("1. 加载实际配置文件...")
        config = load_actual_config()
        if not config:
            print("❌ 无法加载配置文件")
            return False
        print("✅ 配置文件加载成功")
        
        # 2. 提取抖音cookie
        print("\n2. 提取抖音cookie...")
        douyin_cookie = get_douyin_cookie_from_config(config)
        if not douyin_cookie:
            print("❌ 没有找到抖音cookie")
            return False
        print(f"✅ 找到抖音cookie: {douyin_cookie[:50]}...")
        
        # 3. 加载config.yaml
        print("\n3. 加载config.yaml...")
        yaml_config = load_config_yaml()
        if not yaml_config:
            print("❌ 无法加载config.yaml")
            return False
        print("✅ config.yaml加载成功")
        
        # 4. 更新配置
        print("\n4. 更新配置...")
        if not update_config_yaml(yaml_config, douyin_cookie):
            print("❌ 更新配置失败")
            return False
        print("✅ 配置更新成功")
        
        # 5. 保存配置
        print("\n5. 保存配置...")
        if not save_config_yaml(yaml_config):
            print("❌ 保存配置失败")
            return False
        print("✅ 配置保存成功")
        
        print("\n🎉 抖音配置更新测试完成！")
        return True
        
    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if test_douyin_config():
        print("\n✅ 测试成功！")
    else:
        print("\n❌ 测试失败！")
