# -*- coding: utf-8 -*-
"""AstrBot 插件侧适配：将 douyin_link_sdk 接到 main 所需的 get_video_info / download_from_url 接口。"""
from __future__ import annotations

import asyncio
import glob
import os
import re
import time
from typing import Any, Dict, List, Optional, Union, cast

import requests

_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if _PLUGIN_DIR not in __import__("sys").path:
    __import__("sys").path.insert(0, _PLUGIN_DIR)

from douyin_link_sdk import DouyinLinkDownloadAPI, normalize_media_url_list
from douyin_link_sdk.config import Config


def _sanitize_filename(name: str, max_length: int = 50) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]', "_", name or "")
    sanitized = " ".join(sanitized.split())
    return sanitized[:max_length]


def _pick_downloaded_mp4(
    user_path: str,
    video_desc: str,
    since: float,
    sanitize_fn,
) -> Optional[str]:
    if not os.path.isdir(user_path):
        return None
    base = sanitize_fn(video_desc)
    exact = os.path.join(user_path, f"{base}.mp4")
    if os.path.isfile(exact):
        return exact
    best: Optional[str] = None
    best_mtime = 0.0
    for fp in glob.glob(os.path.join(user_path, "*.mp4")):
        try:
            m = os.path.getmtime(fp)
        except OSError:
            continue
        if m < since - 5:
            continue
        name = os.path.basename(fp)
        if name.startswith(base) and m >= best_mtime:
            best_mtime = m
            best = fp
    if best:
        return best
    for fp in glob.glob(os.path.join(user_path, "*.mp4")):
        try:
            m = os.path.getmtime(fp)
        except OSError:
            continue
        if m >= since - 5 and m >= best_mtime:
            best_mtime = m
            best = fp
    return best


class DouyinAudioAPI:
    def __init__(
        self,
        output_dir: str = "data/downloads/douyin",
        timeout: int = 60,
        max_retries: int = 3,
        cookie: Optional[str] = None,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        ck = (cookie or "").replace("\n", "").replace("\r", "").strip()
        self._cookie = ck
        out = output_dir
        if not os.path.isabs(out):
            out = os.path.abspath(os.path.join(os.getcwd(), out))
        self._output_dir = out
        self._link_api = DouyinLinkDownloadAPI(
            cookie=ck if ck else None,
            base_dir=out,
            load_config=True,
        )

    async def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        raw = await self._link_api.user_manager.parse_share_link(url.strip())
        if not raw:
            return {"success": False, "error": "解析链接失败，请检查链接或 Cookie 是否有效"}
        if raw.get("_incomplete") and not raw.get("media_urls"):
            return {"success": False, "error": "无法获取作品详情（可能需登录或触发验证）"}

        author = raw.get("author") or {}
        if isinstance(author, dict):
            author_str = author.get("nickname") or author.get("unique_id") or "未知作者"
        else:
            author_str = str(author)

        stats = raw.get("statistics") or {
            "digg_count": raw.get("digg_count", 0),
            "comment_count": raw.get("comment_count", 0),
            "share_count": raw.get("share_count", 0),
            "collect_count": 0,
        }
        if "collect_count" not in stats:
            stats = {**stats, "collect_count": stats.get("collect_count", 0)}

        return {
            "success": True,
            "title": raw.get("desc") or "未知标题",
            "author": author_str,
            "duration": int(raw.get("duration") or 0),
            "statistics": stats,
            "cover_url": raw.get("cover_url") or "",
            "aweme_id": raw.get("aweme_id") or "",
            "create_time": raw.get("create_time") or 0,
        }

    async def download_from_url(
        self,
        url: str,
        custom_filename: Optional[str] = None,
        download_cover: bool = True,
    ) -> Dict[str, Any]:
        t0 = time.time()
        raw = await self._link_api.user_manager.parse_share_link(url.strip())
        if not raw:
            return {"success": False, "error": "解析链接失败"}
        if raw.get("_incomplete") and not raw.get("media_urls"):
            return {"success": False, "error": "无法获取作品媒体地址"}

        author = raw.get("author") or {}
        if isinstance(author, dict):
            author_name = author.get("nickname") or author.get("unique_id") or "未知作者"
        else:
            author_name = str(author)

        if custom_filename and str(custom_filename).strip():
            video_desc = _sanitize_filename(str(custom_filename).strip())
        else:
            video_desc = _sanitize_filename(raw.get("desc") or "作品")

        urls = normalize_media_url_list(raw.get("media_urls") or [])
        video_entries = cast(
            List[Union[str, Dict[str, Any]]],
            [u for u in urls if u.get("type") in ("video", "live_photo")],
        )
        if not video_entries:
            return {
                "success": False,
                "error": "未找到视频流（纯图集等暂无法抽取音频）",
            }

        loop = asyncio.get_event_loop()
        link = self._link_api

        def _do_download() -> bool:
            return link.download_single_sync(
                aweme_id=str(raw.get("aweme_id") or ""),
                media_urls=video_entries,
                author_name=author_name,
                video_desc=video_desc,
                save_record=True,
            )

        ok = await loop.run_in_executor(None, _do_download)
        if not ok:
            return {"success": False, "error": "下载失败"}

        dl = self._link_api.downloader
        user_part = dl._sanitize_filename(author_name)
        user_path = os.path.join(dl.download_dir, user_part)
        audio_file = _pick_downloaded_mp4(
            user_path, video_desc, t0, dl._sanitize_filename
        )

        if not audio_file or not os.path.isfile(audio_file):
            return {"success": False, "error": "下载完成但未找到视频文件"}

        cover_path: Optional[str] = None
        if download_cover and raw.get("cover_url"):
            cu = raw["cover_url"]
            cover_file = os.path.join(
                user_path, f"cover_{raw.get('aweme_id', 'x')}.jpg"
            )

            def _save_cover(path: str) -> None:
                h = Config.COMMON_HEADERS.copy()
                if self._cookie:
                    h["Cookie"] = self._cookie
                r = requests.get(cu, headers=h, timeout=min(self.timeout, 120))
                r.raise_for_status()
                with open(path, "wb") as f:
                    f.write(r.content)

            try:
                await loop.run_in_executor(None, _save_cover, cover_file)
                cover_path = cover_file
            except Exception:
                cover_path = None

        elapsed = time.time() - t0
        fsize = os.path.getsize(audio_file) if os.path.isfile(audio_file) else 0

        return {
            "success": True,
            "file_path": audio_file,
            "title": raw.get("desc") or "未知标题",
            "author": author_name,
            "file_size": fsize,
            "download_duration": elapsed,
            "cover_path": cover_path if cover_path and os.path.isfile(cover_path) else None,
        }
