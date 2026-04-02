#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""在 douyin_link_sdk 目录下执行: pip install ."""
from setuptools import setup

setup(
    name="douyin-link-sdk",
    version="0.1.0",
    description="Standalone Douyin share-link parse and single-item download SDK",
    author="",
    python_requires=">=3.8",
    packages=["douyin_link_sdk"],
    package_dir={"douyin_link_sdk": "."},
    package_data={"douyin_link_sdk": ["assets/lib/js/*.js"]},
    include_package_data=True,
    install_requires=[
        "requests",
        "aiohttp",
        "PyExecJS",
        "urllib3",
    ],
    extras_require={
        "browser": [
            "playwright",
            "playwright-stealth",
        ],
    },
)
