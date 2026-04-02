# -*- coding: utf-8 -*-
"""链接解析与单作品下载（与主项目 src 无关，仅供本包使用）。"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple, Union

from douyin_link_sdk.config import Config
from douyin_link_sdk.api import DouyinAPI
from douyin_link_sdk.downloader import DouyinDownloader
from douyin_link_sdk.user_manager import DouyinUserManager


async def build_parse_link_response_for_manager(
    user_manager: DouyinUserManager, link: str
) -> Tuple[dict, int]:
    """解析分享文案/链接；供已持有 `DouyinUserManager` 的异步环境复用。"""
    link = (link or "").strip()
    if not link:
        return {"success": False, "message": "链接不能为空"}, 400

    video_info = await user_manager.parse_share_link(link)
    if not video_info:
        return {"success": False, "message": "解析链接失败，请检查链接是否有效"}, 404

    author_sec_uid = video_info.get("author", {}).get("sec_uid", "")
    user_detail = None
    if author_sec_uid:
        ud = await user_manager.get_user_detail(author_sec_uid)
        if ud:
            user_detail = {
                "nickname": ud.get("nickname", ""),
                "unique_id": ud.get("unique_id", ""),
                "follower_count": ud.get("follower_count", 0),
                "following_count": ud.get("following_count", 0),
                "total_favorited": ud.get("total_favorited", 0),
                "aweme_count": ud.get("aweme_count", 0),
                "signature": ud.get("signature", ""),
                "sec_uid": ud.get("sec_uid", ""),
                "avatar_thumb": ud.get("avatar_thumb", {}).get("url_list", [""])[0]
                if ud.get("avatar_thumb")
                else "",
                "avatar_larger": ud.get("avatar_larger", {}).get("url_list", [""])[0]
                if ud.get("avatar_larger")
                else "",
            }

    formatted_video = {
        "author": video_info.get("author", {}),
        "aweme_id": video_info.get("aweme_id", ""),
        "comment_count": video_info.get("comment_count", 0),
        "cover_url": video_info.get("cover_url", ""),
        "create_time": video_info.get("create_time", 0),
        "desc": video_info.get("desc", ""),
        "digg_count": video_info.get("digg_count", 0),
        "media_type": video_info.get("media_type", ""),
        "media_urls": video_info.get("media_urls", []),
        "share_count": video_info.get("share_count", 0),
    }
    body: Dict[str, Any] = {
        "success": True,
        "type": "link_parse",
        "video": formatted_video,
        "videos": [formatted_video],
    }
    if user_detail:
        body["user"] = user_detail
    return body, 200


def normalize_media_url_list(
    media_urls: Optional[List[Union[str, Dict[str, Any]]]] = None,
) -> List[Dict[str, str]]:
    """将 media_urls 转为 download_media_group 所需格式。"""
    if not media_urls:
        return []
    out: List[Dict[str, str]] = []
    for item in media_urls:
        if isinstance(item, str):
            out.append({"url": item, "type": "video"})
            continue
        if isinstance(item, dict):
            url = item.get("url") or item.get("URL")
            if not url:
                continue
            t = item.get("type") or "video"
            out.append({"url": str(url), "type": str(t)})
    return out


def download_single_to_disk(
    downloader: DouyinDownloader,
    *,
    aweme_id: str,
    media_urls: List[Union[str, Dict[str, Any]]],
    author_name: str = "未知作者",
    video_desc: str = "未知作品",
    save_record: bool = True,
) -> bool:
    """同步下载单个作品到 Config.DOWNLOAD_DIR（无 WebSocket）。"""
    urls = normalize_media_url_list(media_urls)
    if not urls:
        return False
    file_path = f"{author_name}/{video_desc}"
    ok = downloader.download_media_group(
        urls, file_path, aweme_id, socketio=None, task_id=None
    )
    if ok and save_record and aweme_id:
        downloader._save_download_record(author_name, aweme_id)
    return ok


class DouyinLinkDownloadAPI:
    """解析分享链接 + 下载到本地。"""

    def __init__(
        self,
        cookie: Optional[str] = None,
        base_dir: Optional[str] = None,
        *,
        load_config: bool = True,
    ):
        if load_config:
            Config.init()
        if base_dir is not None:
            Config.BASE_DIR = base_dir
            Config.DOWNLOAD_DIR = os.path.join(Config.BASE_DIR, "douyin_download")
            os.makedirs(Config.DOWNLOAD_DIR, exist_ok=True)

        c = Config.COOKIE if cookie is None else cookie.replace("\n", "").replace("\r", "").strip()
        self.api = DouyinAPI(c)
        self.downloader = DouyinDownloader(self.api, socketio=None)
        self.user_manager = DouyinUserManager(
            self.api, self.downloader, socketio=None, cookie=c
        )

    async def build_parse_link_response(self, link: str) -> Tuple[dict, int]:
        return await build_parse_link_response_for_manager(self.user_manager, link)

    def download_single_sync(
        self,
        *,
        aweme_id: str,
        media_urls: List[Union[str, Dict[str, Any]]],
        author_name: str = "未知作者",
        video_desc: str = "未知作品",
        save_record: bool = True,
    ) -> bool:
        return download_single_to_disk(
            self.downloader,
            aweme_id=aweme_id,
            media_urls=media_urls,
            author_name=author_name,
            video_desc=video_desc,
            save_record=save_record,
        )
