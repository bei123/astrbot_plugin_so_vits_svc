#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
将 AstrBot 插件里的 douyin_cookie 同步到 douyin_link_sdk 使用的 JSON 配置
（与 douyin_link_sdk.config.Config.CONFIG_FILE 一致，默认：运行目录下 douyin_sdk_config.json）。

历史版本曾写入 DouYin/douyin/web/config.yaml，已废弃。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def sdk_config_path() -> Path:
    """与 douyin_link_sdk.config.Config.CONFIG_FILE 规则一致。"""
    raw = os.environ.get("DOUYIN_SDK_CONFIG")
    if raw:
        return Path(raw)
    return Path(os.getcwd()) / "douyin_sdk_config.json"


def load_actual_config() -> Optional[dict]:
    """加载 AstrBot 侧插件配置（供命令行 main 使用）。"""
    try:
        config_path = Path(__file__).parent.parent.parent / "config" / "so-vits-svc-api_config.json"
        if not config_path.exists():
            config_path = Path(__file__).parent / "config.json"

        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        print(f"配置文件不存在: {config_path}")
        return None
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return None


def get_douyin_cookie_from_config(config: dict) -> Optional[str]:
    try:
        base_setting = config.get("base_setting", {})
        douyin_cookie = base_setting.get("douyin_cookie", "")
        if douyin_cookie:
            print(f"从配置文件中读取到抖音cookie: {douyin_cookie[:50]}...")
            return douyin_cookie
        print("在配置文件中没有找到抖音cookie配置")
        return None
    except Exception as e:
        print(f"提取抖音cookie失败: {e}")
        return None


def load_config_yaml() -> Optional[Dict[str, Any]]:
    """
    加载 SDK 用的 JSON（函数名保留以兼容 main.py）。
    文件不存在时返回空 dict；仅读取失败时返回 None。
    """
    path = sdk_config_path()
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"加载抖音 SDK 配置失败: {e}")
        return None


def update_config_yaml(config: dict, douyin_cookie: str) -> bool:
    """写入 cookie 字段到内存中的配置 dict。"""
    try:
        ck = (douyin_cookie or "").replace("\n", "").replace("\r", "").strip()
        config["cookie"] = ck
        return True
    except Exception as e:
        print(f"更新配置失败: {e}")
        return False


def save_config_yaml(config: dict) -> bool:
    """将配置写入 SDK JSON 文件。"""
    try:
        path = sdk_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"已保存抖音 SDK 配置: {path}")
        return True
    except Exception as e:
        print(f"保存抖音 SDK 配置失败: {e}")
        return False


def main() -> bool:
    print("开始更新抖音配置...")
    cfg = load_actual_config()
    if not cfg:
        print("无法加载配置文件，退出")
        return False
    douyin_cookie = get_douyin_cookie_from_config(cfg)
    if not douyin_cookie:
        print("没有找到抖音cookie，退出")
        return False
    sdk_cfg = load_config_yaml()
    if sdk_cfg is None:
        print("无法加载已有抖音 SDK 配置，退出")
        return False
    if not update_config_yaml(sdk_cfg, douyin_cookie):
        print("更新配置失败，退出")
        return False
    if not save_config_yaml(sdk_cfg):
        print("保存配置失败，退出")
        return False
    print("抖音配置更新完成！")
    return True


if __name__ == "__main__":
    main()
