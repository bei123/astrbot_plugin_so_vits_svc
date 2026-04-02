# -*- coding: utf-8 -*-
"""
独立抖音「分享链接解析 + 单作品下载」SDK。

上游参考实现：DY Video Downloader
https://github.com/anYuJia/DY_video_downloader
（其源码布局为 src/api、src/user、lib/js；本包内嵌为 douyin_link_sdk.*、assets/lib/js。）

相对上游的常见差异（AstrBot 插件侧补丁）：
- get_video_detail：在 execjs 签名可用时为详情请求生成 a_bogus（上游部分代码仍 skip_sign=True，易遇空 body）。
- 短链 v.douyin.com：浏览器式 UA/Cookie、全量重定向与 HTML 兜底提取 aweme_id。
- api.common_request：空 body 时对 Accept-Encoding 重试、可选 DOUYIN_SDK_NO_BROWSER、a_bogus 异常保护等。

安装后可在任意项目中：

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

环境变量（可选）:
  DOUYIN_COOKIE, DOUYIN_BASE_DIR, DOUYIN_SDK_CONFIG
  DOUYIN_SDK_NO_BROWSER=1 — 禁止在直连请求失败时启动 Playwright（Linux 无头服务器建议开启）

默认不会「每次」开浏览器：仅当 requests 返回非 200 或空 body 时才会尝试浏览器兜底。
无浏览器依赖时勿安装 [browser] extra；若禁用回退则无需安装 playwright。
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
