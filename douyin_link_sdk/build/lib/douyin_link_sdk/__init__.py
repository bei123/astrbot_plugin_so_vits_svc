# -*- coding: utf-8 -*-
"""
独立抖音「分享链接解析 + 单作品下载」SDK，安装后可在任意项目中：

    pip install /path/to/DY_video_downloader/douyin_link_sdk

    from douyin_link_sdk import DouyinLinkDownloadAPI
    import asyncio

    api = DouyinLinkDownloadAPI(cookie="你的cookie")
    body, code = asyncio.run(api.build_parse_link_response("https://v.douyin.com/xxx"))
    api.download_single_sync(
        aweme_id=body["video"]["aweme_id"],
        media_urls=body["video"]["media_urls"],
        author_name=body["video"]["author"].get("nickname") or "作者",
        video_desc=body["video"].get("desc") or "作品",
    )

环境变量（可选）: DOUYIN_COOKIE, DOUYIN_BASE_DIR, DOUYIN_SDK_CONFIG
浏览器兜底需: pip install 'douyin-link-sdk[browser]' 并安装 playwright 浏览器。
"""
from .service import (
    DouyinLinkDownloadAPI,
    build_parse_link_response_for_manager,
    download_single_to_disk,
    normalize_media_url_list,
)

__all__ = [
    "DouyinLinkDownloadAPI",
    "build_parse_link_response_for_manager",
    "download_single_to_disk",
    "normalize_media_url_list",
]

__version__ = "0.1.0"
