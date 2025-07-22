#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
QQ音乐API模块
提供搜索和下载QQ音乐的功能
"""

import os
import json
import asyncio
import httpx
import anyio
import base64
import shutil
import time
from typing import Dict, Optional, List
from astrbot.core import logger
from .QQapi.qqmusic_api import search, song
from .QQapi.qqmusic_api.login import get_qrcode, check_qrcode, QRLoginType, QRCodeLoginEvents
from .QQapi.qqmusic_api.utils.credential import Credential
from .QQapi.qqmusic_api.login import check_expired, refresh_cookies
from quart import Quart, Response
from aiohttp import web
import aiofiles

# 全局凭证文件锁，防止多进程/多线程并发写入
_credential_file_lock = asyncio.Lock()


class QQMusicRoute:
    def __init__(self, app: Quart):
        self.app = app
        self.app.add_url_rule("/qqmusic/qr", view_func=self.get_qr, methods=["GET"])

    async def get_qr(self):
        """获取QQ音乐登录二维码"""
        try:
            qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "QQapi", "login_qr.png")
            if not os.path.exists(qr_path):
                return Response("二维码不存在", status=404)

            with open(qr_path, "rb") as f:
                return Response(f.read(), mimetype="image/png")
        except Exception as e:
            logger.error(f"获取二维码失败: {str(e)}")
            return Response("获取二维码失败", status=500)


class QQMusicAPI:
    """QQ音乐API类"""

    def __init__(self, config: Dict = None):
        """初始化API

        Args:
            config: 插件配置字典
        """
        self.config = config or {}
        self.credential_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "QQapi",
            "qqmusic_credential.json"
        )
        self.credential = None
        self.credential_lock = asyncio.Lock()
        self.qr_server = None
        self.qr_server_port = 8081  # 使用8081端口避免与主服务器冲突

    async def start_qr_server(self):
        """启动二维码服务器"""
        app = web.Application()
        app.router.add_get("/qr", self.handle_qr)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "localhost", self.qr_server_port)
        await site.start()
        self.qr_server = runner
        logger.info(f"二维码服务器已启动: http://localhost:{self.qr_server_port}/qr")

    async def stop_qr_server(self):
        """停止二维码服务器"""
        if self.qr_server:
            await self.qr_server.cleanup()
            self.qr_server = None

    async def handle_qr(self, request):
        """处理二维码请求"""
        try:
            qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "QQapi", "login_qr.png")
            if not os.path.exists(qr_path):
                return web.Response(text="二维码不存在", status=404)

            with open(qr_path, "rb") as f:
                return web.Response(body=f.read(), content_type="image/png")
        except Exception as e:
            logger.error(f"获取二维码失败: {str(e)}")
            return web.Response(text="获取二维码失败", status=500)

    def _cleanup_qr_path(self, qr_path: str) -> bool:
        """清理二维码路径
        Args:
            qr_path: 二维码文件路径
        Returns:
            bool: 是否清理成功
        """
        try:
            if os.path.exists(qr_path):
                if os.path.isdir(qr_path):
                    logger.info(f"正在删除目录: {qr_path}")
                    shutil.rmtree(qr_path)
                else:
                    logger.info(f"正在删除文件: {qr_path}")
                    os.remove(qr_path)
                # 等待一小段时间确保文件系统操作完成
                time.sleep(0.1)
                return True
            return True
        except Exception as e:
            logger.error(f"清理二维码路径失败: {str(e)}")
            return False

    def _get_latest_qr_file(self, qr_dir: str) -> str:
        """获取目录中最新的二维码文件
        Args:
            qr_dir: 二维码目录路径
        Returns:
            str: 最新二维码文件的完整路径
        """
        try:
            # 获取目录中所有的png文件
            qr_files = [f for f in os.listdir(qr_dir) if f.endswith(".png")]
            if not qr_files:
                return None

            # 按修改时间排序，获取最新的文件
            latest_file = max(qr_files, key=lambda f: os.path.getmtime(os.path.join(qr_dir, f)))
            return os.path.join(qr_dir, latest_file)
        except Exception as e:
            logger.error(f"获取最新二维码文件失败: {str(e)}")
            return None

    def _clear_credential(self):
        """清除本地凭证文件和内存凭证"""
        self.credential = None
        if os.path.exists(self.credential_file):
            try:
                os.remove(self.credential_file)
            except Exception as e:
                logger.error(f"删除凭证文件失败: {str(e)}")

    async def _is_credential_valid(self) -> bool:
        """检测当前凭证是否有效，直接调用check_expired"""
        if not self.credential:
            return False
        try:
            expired = await check_expired(self.credential)
            return not expired
        except Exception as e:
            logger.warning(f"凭证有效性检测失败: {str(e)}")
            return False

    async def _refresh_credential(self) -> bool:
        """尝试刷新凭证，返回是否成功，详细日志"""
        if not self.credential:
            logger.info("无凭证，无法刷新")
            return False
        # 检查refresh_key/refresh_token
        if not hasattr(self.credential, "refresh_key") or not hasattr(self.credential, "refresh_token") or not self.credential.refresh_key or not self.credential.refresh_token:
            logger.warning("凭证缺少refresh_key/refresh_token，无法刷新，只能扫码登录")
            return False
        try:
            refreshed = await refresh_cookies(self.credential)
            if refreshed:
                logger.info("凭证刷新成功")
                return True
            else:
                logger.warning("凭证刷新失败，refresh_cookies返回False")
                return False
        except Exception as e:
            logger.error(f"凭证刷新异常: {str(e)}")
            return False

    async def force_relogin(self):
        """强制重新登录，清理凭证并扫码"""
        async with self.credential_lock:
            self._clear_credential()
            self.credential = None
            logger.info("已强制清理凭证，准备扫码登录")
            await self.ensure_login()

    async def ensure_login(self) -> bool:
        """确保已登录QQ音乐

        Returns:
            是否登录成功
        """
        async with self.credential_lock:
            if self.credential:
                # 检查凭证有效性
                if await self._is_credential_valid():
                    return True
                else:
                    logger.info("检测到QQ音乐凭证已过期，尝试刷新凭证...")
                    refreshed = await self._refresh_credential()
                    if refreshed:
                        return True
                    else:
                        logger.info("凭证刷新失败或无法刷新，清理本地凭证，准备重新登录")
                        self._clear_credential()
                        self.credential = None

            # 尝试加载已保存的凭证
            self.credential = await self._load_credential()
            if self.credential:
                logger.info("已加载保存的QQ音乐登录凭证，检测有效性...")
                if await self._is_credential_valid():
                    return True
                else:
                    logger.info("检测到本地凭证已过期，尝试刷新凭证...")
                    refreshed = await self._refresh_credential()
                    if refreshed:
                        return True
                    else:
                        logger.info("凭证刷新失败或无法刷新，清理本地凭证，准备重新登录")
                        self._clear_credential()
                        self.credential = None

            # 需要重新登录
            logger.info("正在获取QQ音乐登录二维码...")
            try:
                # 获取QQ登录二维码
                qr = await get_qrcode(QRLoginType.QQ)

                # 保存二维码到QQapi目录
                current_dir = os.path.dirname(os.path.abspath(__file__))
                qr_dir = os.path.join(current_dir, "QQapi")

                # 确保目录存在
                if not os.path.exists(qr_dir):
                    os.makedirs(qr_dir)

                # 保存新二维码
                try:
                    qr_path = qr.save(qr_dir)  # 使用QR对象自带的save方法，它会返回保存的文件路径
                    logger.info(f"二维码已保存到: {qr_path}")
                except Exception as e:
                    logger.error(f"保存二维码失败: {str(e)}")
                    return False

                # 读取二维码文件并转换为base64
                try:
                    if not os.path.isfile(qr_path):
                        logger.error(f"二维码文件不存在或不是文件: {qr_path}")
                        return False

                    with open(qr_path, "rb") as f:
                        qr_base64 = base64.b64encode(f.read()).decode()
                        base64_url = f"data:image/png;base64,{qr_base64}"
                        logger.info("请复制以下链接到浏览器打开二维码:")
                        logger.info(base64_url)
                        # 同时输出到控制台，方便复制
                        print("\n请复制以下链接到浏览器打开二维码:")
                        print(base64_url)
                        print()  # 添加空行使输出更清晰
                except Exception as e:
                    logger.error(f"读取二维码文件失败: {str(e)}")
                    return False

                logger.info("请使用QQ音乐APP扫描二维码")

                # 等待扫码
                while True:
                    event, credential = await check_qrcode(qr)
                    if event == QRCodeLoginEvents.DONE and credential:
                        logger.info("QQ音乐登录成功！")
                        # 保存凭证
                        await self._save_credential(credential)
                        self.credential = credential
                        return True
                    elif event == QRCodeLoginEvents.SCAN:
                        logger.info("等待扫码...")
                    elif event == QRCodeLoginEvents.CONF:
                        logger.info("已扫码，等待确认...")
                    elif event == QRCodeLoginEvents.TIMEOUT:
                        logger.error("二维码已过期，请重新登录")
                        return False
                    elif event == QRCodeLoginEvents.REFUSE:
                        logger.error("已拒绝登录")
                        return False
                    await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"QQ音乐登录出错: {str(e)}")
                return False

    async def _save_credential(self, credential: Credential):
        """异步保存登录凭证到文件"""
        data = {
            "musicid": getattr(credential, "musicid", None),
            "musickey": getattr(credential, "musickey", None),
            "refresh_key": getattr(credential, "refresh_key", None),
            "refresh_token": getattr(credential, "refresh_token", None)
        }
        try:
            async with _credential_file_lock:
                async with aiofiles.open(self.credential_file, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(data))
        except Exception as e:
            logger.error(f"保存QQ音乐凭证出错: {str(e)}，数据: {data}")

    async def _load_credential(self) -> Optional[Credential]:
        """异步从文件加载登录凭证，兼容字段缺失"""
        if not os.path.exists(self.credential_file):
            return None
        try:
            async with _credential_file_lock:
                async with aiofiles.open(self.credential_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    data = json.loads(content)
            # 字段兼容性检查
            musicid = data.get("musicid")
            musickey = data.get("musickey")
            refresh_key = data.get("refresh_key")
            refresh_token = data.get("refresh_token")
            if not musicid or not musickey:
                logger.error(f"凭证文件缺少必要字段: {data}")
                return None
            cred = Credential(musicid=musicid, musickey=musickey)
            # 动态加refresh_key/refresh_token
            if refresh_key:
                setattr(cred, "refresh_key", refresh_key)
            if refresh_token:
                setattr(cred, "refresh_token", refresh_token)
            return cred
        except Exception as e:
            logger.error(f"加载QQ音乐凭证出错: {str(e)}，文件内容可能损坏或权限不足")
            return None

    async def search(self, keyword: str, limit: int = 5) -> List[Dict]:
        """搜索歌曲

        Args:
            keyword: 搜索关键词
            limit: 返回结果数量

        Returns:
            搜索结果列表
        """
        if not await self.ensure_login():
            logger.error("QQ音乐未登录，无法搜索")
            return []

        try:
            search_result = await search.search_by_type(keyword=keyword, num=limit)
            return search_result or []
        except Exception as e:
            # 检查是否凭证失效
            err_msg = str(e)
            if any(x in err_msg for x in ["未登录", "musickey", "凭证", "登录失效", "登录过期"]):
                logger.warning("检测到凭证失效，自动清理并重试登录")
                self._clear_credential()
                if await self.ensure_login():
                    try:
                        search_result = await search.search_by_type(keyword=keyword, num=limit)
                        return search_result or []
                    except Exception as e2:
                        logger.error(f"QQ音乐搜索重试仍失败: {str(e2)}")
                        return []
                else:
                    logger.error("QQ音乐重新登录失败")
                    return []
            logger.error(f"QQ音乐搜索出错: {str(e)}")
            return []

    async def get_song_url(self, song_mid: str, file_type=None) -> Optional[str]:
        """获取歌曲下载链接

        Args:
            song_mid: 歌曲ID
            file_type: 音质类型，默认为None，将尝试获取最高音质

        Returns:
            下载链接，失败返回None
        """
        if not await self.ensure_login():
            logger.error("QQ音乐未登录，无法获取下载链接")
            return None

        try:
            # 如果未指定音质类型，则尝试不同音质
            if file_type is None:
                file_types = [
                    song.SongFileType.FLAC,      # 无损
                    song.SongFileType.OGG_640,   # 640kbps
                    song.SongFileType.OGG_320,   # 320kbps
                    song.SongFileType.MP3_320,   # 320kbps
                    song.SongFileType.ACC_192,   # 192kbps
                    song.SongFileType.MP3_128,   # 128kbps
                    song.SongFileType.ACC_96,    # 96kbps
                    song.SongFileType.ACC_48     # 48kbps
                ]

                for ft in file_types:
                    try:
                        urls = await song.get_song_urls(
                            mid=[song_mid],
                            credential=self.credential,
                            file_type=ft
                        )
                        if urls and urls.get(song_mid):
                            return urls[song_mid]
                    except Exception:
                        continue

                return None
            else:
                # 使用指定的音质类型
                urls = await song.get_song_urls(
                    mid=[song_mid],
                    credential=self.credential,
                    file_type=file_type
                )
                return urls.get(song_mid) if urls else None

        except Exception as e:
            # 检查是否凭证失效
            err_msg = str(e)
            if any(x in err_msg for x in ["未登录", "musickey", "凭证", "登录失效", "登录过期"]):
                logger.warning("检测到凭证失效，自动清理并重试登录")
                self._clear_credential()
                if await self.ensure_login():
                    try:
                        # 如果未指定音质类型，则尝试不同音质
                        if file_type is None:
                            file_types = [
                                song.SongFileType.FLAC,      # 无损
                                song.SongFileType.OGG_640,   # 640kbps
                                song.SongFileType.OGG_320,   # 320kbps
                                song.SongFileType.MP3_320,   # 320kbps
                                song.SongFileType.ACC_192,   # 192kbps
                                song.SongFileType.MP3_128,   # 128kbps
                                song.SongFileType.ACC_96,    # 96kbps
                                song.SongFileType.ACC_48     # 48kbps
                            ]

                            for ft in file_types:
                                try:
                                    urls = await song.get_song_urls(
                                        mid=[song_mid],
                                        credential=self.credential,
                                        file_type=ft
                                    )
                                    if urls and urls.get(song_mid):
                                        return urls[song_mid]
                                except Exception:
                                    continue

                            return None
                        else:
                            urls = await song.get_song_urls(
                                mid=[song_mid],
                                credential=self.credential,
                                file_type=file_type
                            )
                            return urls.get(song_mid) if urls else None
                    except Exception as e2:
                        logger.error(f"QQ音乐下载链接重试仍失败: {str(e2)}")
                        return None
                else:
                    logger.error("QQ音乐重新登录失败")
                    return None
            logger.error(f"获取QQ音乐下载链接出错: {str(e)}")
            return None

    def get_quality_name(self, file_type) -> str:
        """获取音质名称

        Args:
            file_type: 音质类型

        Returns:
            音质名称
        """
        quality_map = {
            song.SongFileType.FLAC: "无损",
            song.SongFileType.OGG_640: "640kbps",
            song.SongFileType.OGG_320: "320kbps",
            song.SongFileType.MP3_320: "320kbps",
            song.SongFileType.ACC_192: "192kbps",
            song.SongFileType.MP3_128: "128kbps",
            song.SongFileType.ACC_96: "96kbps",
            song.SongFileType.ACC_48: "48kbps"
        }
        return quality_map.get(file_type, "未知音质")

    def get_file_extension(self, file_type) -> str:
        """获取文件扩展名

        Args:
            file_type: 音质类型

        Returns:
            文件扩展名
        """
        extension_map = {
            song.SongFileType.FLAC: ".flac",
            song.SongFileType.OGG_640: ".ogg",
            song.SongFileType.OGG_320: ".ogg",
            song.SongFileType.MP3_320: ".mp3",
            song.SongFileType.ACC_192: ".m4a",
            song.SongFileType.MP3_128: ".mp3",
            song.SongFileType.ACC_96: ".m4a",
            song.SongFileType.ACC_48: ".m4a"
        }
        return extension_map.get(file_type, ".mp3")

    async def get_song_with_highest_quality(self, keyword: str) -> Optional[Dict]:
        """获取最高音质的歌曲信息

        Args:
            keyword: 搜索关键词

        Returns:
            歌曲信息字典，失败返回None
        """
        search_results = await self.search(keyword, limit=1)
        if not search_results:
            return None

        song_info = search_results[0]
        song_mid = song_info["mid"]
        song_name = song_info["name"]
        singer_name = song_info.get("singer", [{}])[0].get("name", "未知歌手")

        # 尝试获取下载链接
        url = await self.get_song_url(song_mid)
        if not url:
            return None

        # 获取音质信息
        file_types = [
            song.SongFileType.FLAC,
            song.SongFileType.OGG_640,
            song.SongFileType.OGG_320,
            song.SongFileType.MP3_320,
            song.SongFileType.ACC_192,
            song.SongFileType.MP3_128,
            song.SongFileType.ACC_96,
            song.SongFileType.ACC_48
        ]

        used_type = None
        for file_type in file_types:
            try:
                urls = await song.get_song_urls(
                    mid=[song_mid],
                    credential=self.credential,
                    file_type=file_type
                )
                if urls and urls.get(song_mid):
                    used_type = file_type
                    break
            except Exception:
                continue

        if not used_type:
            return None

        # 构建返回信息
        return {
            "name": song_name,
            "ar_name": singer_name,
            "mid": song_mid,
            "url": url,
            "level": self.get_quality_name(used_type),
            "extension": self.get_file_extension(used_type),
            "file_type": used_type
        }

    async def download_song(self, song_info: Dict, save_path: Optional[str] = None) -> Optional[str]:
        """下载歌曲

        Args:
            song_info: 歌曲信息字典
            save_path: 保存路径，默认为None，将使用临时目录

        Returns:
            下载的文件路径，失败返回None
        """
        if not song_info or not song_info.get("url"):
            return None

        if not save_path:
            save_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
            os.makedirs(save_path, exist_ok=True)

        try:
            song_name = song_info.get("name", "未知歌曲")
            extension = song_info.get("extension", ".mp3")
            file_path = os.path.join(save_path, f"{song_name}{extension}")

            async with httpx.AsyncClient() as client:
                async with client.stream("GET", song_info["url"]) as response:
                    response.raise_for_status()
                    async with await anyio.open_file(file_path, "wb") as f:
                        async for chunk in response.aiter_bytes(1024 * 5):
                            if chunk:
                                await f.write(chunk)

            return file_path
        except Exception as e:
            logger.error(f"下载QQ音乐歌曲出错: {str(e)}")
            return None
