# -*- coding: utf-8 -*-
"""独立配置：下载目录、Cookie、内置 douyin.js 路径。不依赖主项目。"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))

IS_FROZEN = getattr(sys, "frozen", False)


def douyin_js_path() -> str:
    """打包内置的签名脚本路径。"""
    return os.path.join(_PKG_DIR, "assets", "lib", "js", "douyin.js")


class Config:
    COOKIE = ""
    BASE_DIR = os.path.join(os.getcwd(), "douyin_download")
    DOWNLOAD_DIR = os.path.join(BASE_DIR, "douyin_download")
    CONFIG_FILE = os.environ.get(
        "DOUYIN_SDK_CONFIG",
        os.path.join(os.getcwd(), "douyin_sdk_config.json"),
    )
    CHUNK_SIZE = 8192
    MAX_FILENAME_LENGTH = 50
    COMMON_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
        "sec-ch-ua-platform": "Windows",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
        "referer": "https://www.douyin.com/?recommend=1",
        "priority": "u=1, i",
        "pragma": "no-cache",
        "cache-control": "no-cache",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "accept": "application/json, text/plain, */*",
        "dnt": "1",
    }

    @classmethod
    def load_config(cls) -> None:
        cls.COOKIE = os.environ.get("DOUYIN_COOKIE", cls.COOKIE)
        env_base = os.environ.get("DOUYIN_BASE_DIR")
        if env_base:
            cls.BASE_DIR = env_base
            cls.DOWNLOAD_DIR = os.path.join(cls.BASE_DIR, "douyin_download")
        if os.path.exists(cls.CONFIG_FILE):
            try:
                with open(cls.CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("cookie"):
                    cls.COOKIE = (
                        str(data["cookie"]).replace("\n", "").replace("\r", "").strip()
                    )
                if data.get("base_dir"):
                    cls.BASE_DIR = data["base_dir"]
                    cls.DOWNLOAD_DIR = os.path.join(cls.BASE_DIR, "douyin_download")
            except Exception:
                pass

    @classmethod
    def init(cls, cookie: Optional[str] = None, base_dir: Optional[str] = None) -> None:
        cls.load_config()
        if cookie is not None:
            cls.COOKIE = cookie.replace("\n", "").replace("\r", "").strip()
        if base_dir is not None:
            cls.BASE_DIR = base_dir
            cls.DOWNLOAD_DIR = os.path.join(cls.BASE_DIR, "douyin_download")
        os.makedirs(cls.DOWNLOAD_DIR, exist_ok=True)
