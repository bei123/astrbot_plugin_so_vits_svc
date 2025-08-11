#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
抖音配置更新使用示例
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(__file__))

def example_usage():
    """使用示例"""
    print("=== 抖音配置更新使用示例 ===\n")
    
    # 1. 导入配置更新模块
    try:
        from update_douyin_config import (
            load_conf_schema,
            get_douyin_cookie_from_schema,
            load_config_yaml,
            update_config_yaml,
            save_config_yaml
        )
        print("✅ 成功导入配置更新模块")
    except ImportError as e:
        print(f"❌ 导入模块失败: {e}")
        return False
    
    # 2. 加载配置schema
    print("\n1. 加载配置schema...")
    schema = load_conf_schema()
    if not schema:
        print("❌ 加载配置schema失败")
        return False
    print("✅ 配置schema加载成功")
    
    # 3. 提取抖音cookie
    print("\n2. 提取抖音cookie...")
    douyin_cookie = get_douyin_cookie_from_schema(schema)
    if not douyin_cookie:
        print("❌ 没有找到抖音cookie配置")
        return False
    print(f"✅ 找到抖音cookie: {douyin_cookie[:50]}...")
    
    # 4. 加载config.yaml
    print("\n3. 加载config.yaml...")
    config = load_config_yaml()
    if not config:
        print("❌ 加载config.yaml失败")
        return False
    print("✅ config.yaml加载成功")
    
    # 5. 更新配置
    print("\n4. 更新配置...")
    if not update_config_yaml(config, douyin_cookie):
        print("❌ 更新配置失败")
        return False
    print("✅ 配置更新成功")
    
    # 6. 保存配置
    print("\n5. 保存配置...")
    if not save_config_yaml(config):
        print("❌ 保存配置失败")
        return False
    print("✅ 配置保存成功")
    
    print("\n🎉 抖音配置更新完成！")
    return True

def show_config_structure():
    """显示配置结构"""
    print("\n=== 配置结构说明 ===\n")
    
    print("1. _conf_schema.json 中的抖音cookie配置:")
    print("""
    {
        "base_setting": {
            "items": {
                "douyin_cookie": {
                    "description": "抖音Cookie",
                    "type": "string",
                    "hint": "用于访问抖音API的Cookie，提高下载成功率",
                    "default": "你的抖音cookie字符串"
                }
            }
        }
    }
    """)
    
    print("2. config.yaml 中的抖音配置:")
    print("""
    TokenManager:
      douyin:
        headers:
          Accept-Language: zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2
          User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36
          Referer: https://www.douyin.com/
          Cookie: 从_conf_schema.json读取的cookie
    """)

if __name__ == "__main__":
    print("抖音配置更新功能演示")
    print("=" * 50)
    
    # 显示配置结构
    show_config_structure()
    
    # 执行示例
    if example_usage():
        print("\n✅ 示例执行成功！")
    else:
        print("\n❌ 示例执行失败！")
    
    print("\n使用说明:")
    print("1. 在_conf_schema.json中配置抖音cookie")
    print("2. 插件启动时会自动更新配置")
    print("3. 也可以手动运行: python update_douyin_config.py")
    print("4. 测试配置: python test_config_update.py")
