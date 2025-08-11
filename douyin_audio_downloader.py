"""
抖音音频下载器 - 修复版本
支持从抖音视频URL或aweme_id下载音频文件
"""

import asyncio
import aiohttp
import aiofiles
import re
import os
import json
import logging
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import time
import sys

# 导入现有的抖音爬虫模块
try:
    # 添加DouYin模块路径到sys.path
    douyin_path = os.path.join(os.path.dirname(__file__), 'DouYin')
    if douyin_path not in sys.path:
        sys.path.insert(0, douyin_path)
    
    from .DouYin.douyin.web.web_crawler import DouyinWebCrawler
    from .DouYin.douyin.web.utils import AwemeIdFetcher
    from .DouYin.utils.utils import get_timestamp
    from .DouYin.utils.logger import logger
    CRAWLER_AVAILABLE = True
    logger.info("成功导入抖音爬虫模块")
except ImportError as e:
    logging.warning(f"无法导入现有爬虫模块: {e}")
    CRAWLER_AVAILABLE = False

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DouyinAudioDownloader:
    """抖音音频下载器 - 核心下载逻辑"""
    
    def __init__(self, output_dir: str = "downloads", proxies: dict = None, 
                 max_retries: int = 3, timeout: int = 30):
        """
        初始化下载器
        
        Args:
            output_dir: 下载文件保存目录
            proxies: 代理设置，格式: {"http": "http://proxy:port", "https": "https://proxy:port"}
            max_retries: 最大重试次数
            timeout: 请求超时时间（秒）
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.proxies = proxies
        self.max_retries = max_retries
        self.timeout = timeout
        
        # 初始化爬虫
        self.crawler = None
        self.session = None
        
        if CRAWLER_AVAILABLE:
            try:
                self.crawler = DouyinWebCrawler()
                logger.info("成功初始化抖音爬虫")
            except Exception as e:
                logger.warning(f"初始化爬虫失败: {e}")
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        if not self.crawler:
            connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    def extract_aweme_id_from_url(self, url: str) -> Optional[str]:
        """
        从抖音URL中提取aweme_id
        
        Args:
            url: 抖音视频URL
            
        Returns:
            aweme_id字符串，如果无法提取则返回None
        """
        # 支持多种URL格式
        patterns = [
            r'/video/(\d+)',  # 标准格式: https://www.douyin.com/video/1234567890
            r'aweme_id=(\d+)',  # 查询参数格式: https://www.douyin.com/xxx?aweme_id=1234567890
            r'/(\d{15,})',  # 长数字ID: https://www.douyin.com/xxx/123456789012345
            r'v\.douyin\.com/([a-zA-Z0-9]+)',  # 短链接格式
            r'iesdouyin\.com/share/video/(\d+)',  # 分享链接格式
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                aweme_id = match.group(1)
                # 如果是短链接，需要解析
                if len(aweme_id) < 15:
                    logger.info(f"检测到短链接: {aweme_id}")
                    # 这里可以添加短链接解析逻辑
                    continue
                return aweme_id
        
        logger.warning(f"无法从URL中提取aweme_id: {url}")
        return None
    
    async def resolve_short_url(self, short_url: str) -> Optional[str]:
        """
        解析短链接获取真实URL
        
        Args:
            short_url: 短链接
            
        Returns:
            真实URL，如果解析失败则返回None
        """
        try:
            if not self.session:
                async with aiohttp.ClientSession() as session:
                    async with session.get(short_url, allow_redirects=False) as response:
                        if response.status in [301, 302]:
                            return response.headers.get('Location')
            else:
                async with self.session.get(short_url, allow_redirects=False) as response:
                    if response.status in [301, 302]:
                        return response.headers.get('Location')
        except Exception as e:
            logger.error(f"解析短链接失败: {e}")
        
        return None
    
    async def get_video_info(self, aweme_id: str) -> Dict[str, Any]:
        """
        获取视频信息
        
        Args:
            aweme_id: 视频ID
            
        Returns:
            包含视频信息的字典
        """
        for attempt in range(self.max_retries):
            try:
                if self.crawler and CRAWLER_AVAILABLE:
                    # 使用现有的爬虫模块的fetch_one_video方法
                    logger.info(f"正在获取视频信息: {aweme_id}")
                    response = await self.crawler.fetch_one_video(aweme_id)
                    
                    # 调试：记录API响应
                    logger.debug(f"API响应: {response}")
                    
                    if response and 'aweme_detail' in response:
                        detail = response['aweme_detail']
                        return self._parse_video_detail(detail, aweme_id)
                    elif response and 'status_code' in response and response['status_code'] != 0:
                        error_msg = f"API返回错误: {response.get('status_msg', '未知错误')}"
                        logger.error(error_msg)
                        raise Exception(error_msg)
                    elif response:
                        # 如果响应存在但没有aweme_detail，尝试其他字段
                        error_msg = f"API响应格式异常: {list(response.keys()) if isinstance(response, dict) else type(response)}"
                        logger.error(error_msg)
                        raise Exception(error_msg)
                    else:
                        error_msg = "API返回空响应"
                        logger.error(error_msg)
                        raise Exception(error_msg)
                else:
                    error_msg = "爬虫模块不可用"
                    logger.error(error_msg)
                    raise Exception(error_msg)
                    
            except Exception as e:
                logger.warning(f"获取视频信息失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # 指数退避
                else:
                    logger.error(f"所有尝试都失败了: {e}")
                    raise Exception(f"获取视频信息失败: {e}")
        
        raise Exception("获取视频信息失败，已达到最大重试次数")
    
    def _parse_video_detail(self, detail: Dict[str, Any], aweme_id: str) -> Dict[str, Any]:
        """解析视频详情数据"""
        try:
            # 提取音频URL
            audio_url = None
            music_info = detail.get('music', {})
            
            # 尝试多种音频URL字段和路径
            audio_url_paths = [
                # 直接字段
                music_info.get('play_url', {}).get('uri'),
                music_info.get('uri'),
                music_info.get('url'),
                music_info.get('download_url'),
                # 嵌套字段
                music_info.get('play_url', {}).get('url_list', [None])[0] if music_info.get('play_url', {}).get('url_list') else None,
                music_info.get('url_list', [None])[0] if music_info.get('url_list') else None,
                # 视频中的音乐信息
                detail.get('video', {}).get('music', {}).get('play_url', {}).get('uri'),
                detail.get('video', {}).get('music', {}).get('uri'),
                # 其他可能的路径
                detail.get('music', {}).get('play_url', {}).get('uri'),
                detail.get('music', {}).get('uri'),
            ]
            
            # 找到第一个有效的音频URL
            for url in audio_url_paths:
                if url and isinstance(url, str) and url.startswith('http'):
                    audio_url = url
                    break
            
            # 如果还是没有找到，尝试从原始数据中搜索
            if not audio_url:
                import json
                raw_json = json.dumps(detail)
                # 搜索可能的音频URL模式
                import re
                url_patterns = [
                    r'"play_url":\s*{\s*"uri":\s*"([^"]+)"',
                    r'"uri":\s*"([^"]*\.mp3[^"]*)"',
                    r'"uri":\s*"([^"]*\.m4a[^"]*)"',
                    r'"url":\s*"([^"]*\.mp3[^"]*)"',
                    r'"url":\s*"([^"]*\.m4a[^"]*)"',
                ]
                
                for pattern in url_patterns:
                    matches = re.findall(pattern, raw_json)
                    if matches:
                        for match in matches:
                            if match.startswith('http'):
                                audio_url = match
                                break
                        if audio_url:
                            break
            
            logger.info(f"解析到的音频URL: {audio_url}")
            
            return {
                'aweme_id': aweme_id,
                'title': detail.get('desc', ''),
                'author': detail.get('author', {}).get('nickname', ''),
                'author_id': detail.get('author', {}).get('uid', ''),
                'duration': detail.get('video', {}).get('duration', 0),
                'audio_url': audio_url,
                'cover_url': detail.get('video', {}).get('cover', {}).get('url_list', [None])[0],
                'create_time': detail.get('create_time', 0),
                'statistics': detail.get('statistics', {}),
                'raw_data': detail
            }
        except Exception as e:
            logger.error(f"解析视频详情失败: {e}")
            return {
                'aweme_id': aweme_id,
                'title': '',
                'author': '',
                'duration': 0,
                'audio_url': None,
                'error': str(e)
            }
    

    
    async def download_audio(self, audio_url: str, filename: str) -> str:
        """
        下载音频文件
        
        Args:
            audio_url: 音频文件URL
            filename: 保存的文件名
            
        Returns:
            保存的文件路径
        """
        if not audio_url:
            raise Exception("音频URL为空")
        
        # 清理文件名
        safe_filename = self.sanitize_filename(filename)
        file_path = self.output_dir / f"{safe_filename}.mp3"
        
        # 检查文件是否已存在
        if file_path.exists():
            logger.info(f"文件已存在，跳过下载: {file_path}")
            return str(file_path)
        
        for attempt in range(self.max_retries):
            try:
                if self.session:
                    async with self.session.get(audio_url) as response:
                        if response.status == 200:
                            async with aiofiles.open(file_path, 'wb') as f:
                                await f.write(await response.read())
                            logger.info(f"下载成功: {file_path}")
                            return str(file_path)
                        else:
                            raise Exception(f"下载失败，状态码: {response.status}")
                else:
                    # 使用临时session下载
                    async with aiohttp.ClientSession() as session:
                        async with session.get(audio_url) as response:
                            if response.status == 200:
                                async with aiofiles.open(file_path, 'wb') as f:
                                    await f.write(await response.read())
                                logger.info(f"下载成功: {file_path}")
                                return str(file_path)
                            else:
                                raise Exception(f"下载失败，状态码: {response.status}")
                                
            except Exception as e:
                logger.warning(f"下载音频文件失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))  # 指数退避
                else:
                    raise Exception(f"下载音频文件失败: {e}")

    async def download_cover(self, cover_url: str, filename: str, format: str = "jpg") -> str:
        """
        下载视频封面
        
        Args:
            cover_url: 封面图片URL
            filename: 保存的文件名（不含扩展名）
            format: 图片格式，支持 jpg, png, webp
            
        Returns:
            保存的文件路径
        """
        if not cover_url:
            raise Exception("封面URL为空")
        
        # 清理文件名
        safe_filename = self.sanitize_filename(filename)
        file_path = self.output_dir / f"{safe_filename}_cover.{format}"
        
        # 检查文件是否已存在
        if file_path.exists():
            logger.info(f"封面文件已存在，跳过下载: {file_path}")
            return str(file_path)
        
        for attempt in range(self.max_retries):
            try:
                if self.session:
                    async with self.session.get(cover_url) as response:
                        if response.status == 200:
                            async with aiofiles.open(file_path, 'wb') as f:
                                await f.write(await response.read())
                            logger.info(f"封面下载成功: {file_path}")
                            return str(file_path)
                        else:
                            raise Exception(f"封面下载失败，状态码: {response.status}")
                else:
                    # 使用临时session下载
                    async with aiohttp.ClientSession() as session:
                        async with session.get(cover_url) as response:
                            if response.status == 200:
                                async with aiofiles.open(file_path, 'wb') as f:
                                    await f.write(await response.read())
                                logger.info(f"封面下载成功: {file_path}")
                                return str(file_path)
                            else:
                                raise Exception(f"封面下载失败，状态码: {response.status}")
                                
            except Exception as e:
                logger.warning(f"下载封面失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # 指数退避
                else:
                    raise Exception(f"下载封面失败: {e}")

    async def download_both_audio_and_cover(self, audio_url: str, cover_url: str, filename: str, cover_format: str = "jpg") -> Dict[str, str]:
        """
        同时下载音频和封面
        
        Args:
            audio_url: 音频文件URL
            cover_url: 封面图片URL
            filename: 保存的文件名（不含扩展名）
            cover_format: 封面图片格式
            
        Returns:
            包含音频和封面文件路径的字典
        """
        results = {}
        
        # 下载音频
        if audio_url:
            try:
                audio_path = await self.download_audio(audio_url, filename)
                results['audio_path'] = audio_path
            except Exception as e:
                logger.error(f"下载音频失败: {e}")
                results['audio_error'] = str(e)
        
        # 下载封面
        if cover_url:
            try:
                cover_path = await self.download_cover(cover_url, filename, cover_format)
                results['cover_path'] = cover_path
            except Exception as e:
                logger.error(f"下载封面失败: {e}")
                results['cover_error'] = str(e)
        
        return results
    
    def sanitize_filename(self, filename: str) -> str:
        """
        清理文件名，移除非法字符
        
        Args:
            filename: 原始文件名
            
        Returns:
            清理后的文件名
        """
        # 移除或替换非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        safe_name = re.sub(illegal_chars, '_', filename)
        
        # 移除多余的空格和点
        safe_name = re.sub(r'\s+', ' ', safe_name).strip()
        safe_name = re.sub(r'\.+', '.', safe_name)
        
        # 限制长度
        if len(safe_name) > 100:
            safe_name = safe_name[:100]
        
        # 确保文件名不为空
        if not safe_name:
            safe_name = "unknown"
        
        return safe_name
    
    async def download_audio_from_url(self, url: str, custom_filename: str = None, 
                                    download_cover: bool = False, cover_format: str = "jpg") -> Dict[str, Any]:
        """
        从URL下载音频
        
        Args:
            url: 抖音视频URL
            custom_filename: 自定义文件名（可选）
            download_cover: 是否同时下载封面
            cover_format: 封面图片格式
            
        Returns:
            下载结果信息
        """
        start_time = time.time()
        
        try:
            # 处理短链接
            if 'v.douyin.com' in url:
                real_url = await self.resolve_short_url(url)
                if real_url:
                    url = real_url
                    logger.info(f"解析短链接成功: {real_url}")
            
            # 提取aweme_id
            aweme_id = self.extract_aweme_id_from_url(url)
            if not aweme_id:
                raise Exception("无法从URL中提取视频ID")
            
            logger.info(f"提取到aweme_id: {aweme_id}")
            
            return await self.download_audio_from_aweme_id(aweme_id, custom_filename, download_cover, cover_format)
            
        except Exception as e:
            logger.error(f"从URL下载音频失败: {e}")
            return {
                'success': False,
                'url': url,
                'error': str(e),
                'duration': time.time() - start_time
            }
    
    async def download_audio_from_aweme_id(self, aweme_id: str, custom_filename: str = None, 
                                         download_cover: bool = False, cover_format: str = "jpg") -> Dict[str, Any]:
        """
        从aweme_id下载音频
        
        Args:
            aweme_id: 视频ID
            custom_filename: 自定义文件名（可选）
            download_cover: 是否同时下载封面
            cover_format: 封面图片格式
            
        Returns:
            下载结果信息
        """
        start_time = time.time()
        
        try:
            # 获取视频信息
            video_info = await self.get_video_info(aweme_id)
            
            if not video_info:
                raise Exception("无法获取视频信息")
            
            # 检查是否有音频URL
            audio_url = video_info.get('audio_url')
            if not audio_url:
                raise Exception("该视频没有可下载的音频")
            
            # 获取封面URL
            cover_url = video_info.get('cover_url')
            
            # 确定文件名
            if custom_filename:
                filename = custom_filename
            else:
                title = video_info.get('title', '')
                author = video_info.get('author', '')
                if title and author:
                    filename = f"{author}_{title}"
                else:
                    filename = f"douyin_{aweme_id}"
            
            # 下载音频和封面
            if download_cover and cover_url:
                download_results = await self.download_both_audio_and_cover(audio_url, cover_url, filename, cover_format)
                audio_path = download_results.get('audio_path')
                cover_path = download_results.get('cover_path')
                cover_error = download_results.get('cover_error')
            else:
                # 只下载音频
                audio_path = await self.download_audio(audio_url, filename)
                cover_path = None
                cover_error = None
            
            duration = time.time() - start_time
            
            result = {
                'success': True,
                'aweme_id': aweme_id,
                'title': video_info.get('title', ''),
                'author': video_info.get('author', ''),
                'author_id': video_info.get('author_id', ''),
                'duration': video_info.get('duration', 0),
                'file_path': audio_path,
                'file_size': os.path.getsize(audio_path) if os.path.exists(audio_path) else 0,
                'download_duration': duration,
                'audio_url': audio_url,
                'cover_url': cover_url,
                'create_time': video_info.get('create_time', 0),
                'statistics': video_info.get('statistics', {})
            }
            
            # 添加封面相关信息
            if download_cover:
                result['cover_path'] = cover_path
                if cover_error:
                    result['cover_error'] = cover_error
                if cover_path:
                    result['cover_size'] = os.path.getsize(cover_path) if os.path.exists(cover_path) else 0
            
            return result
            
        except Exception as e:
            logger.error(f"从aweme_id下载音频失败: {e}")
            return {
                'success': False,
                'aweme_id': aweme_id,
                'error': str(e),
                'duration': time.time() - start_time
            }
    
    async def batch_download_audio(self, urls: List[str], output_dir: str = None, 
                                 download_cover: bool = False, cover_format: str = "jpg") -> List[Dict[str, Any]]:
        """
        批量下载音频
        
        Args:
            urls: 抖音视频URL列表
            output_dir: 输出目录（可选，会覆盖默认目录）
            download_cover: 是否同时下载封面
            cover_format: 封面图片格式
            
        Returns:
            下载结果列表
        """
        if output_dir:
            self.output_dir = Path(output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        total_start_time = time.time()
        
        logger.info(f"开始批量下载，共 {len(urls)} 个文件")
        if download_cover:
            logger.info(f"将同时下载封面，格式: {cover_format}")
        
        for i, url in enumerate(urls, 1):
            try:
                logger.info(f"正在下载第 {i}/{len(urls)} 个视频: {url}")
                result = await self.download_audio_from_url(url, download_cover=download_cover, cover_format=cover_format)
                results.append(result)
                
                if result['success']:
                    logger.info(f"✅ 下载成功: {result['file_path']}")
                    if download_cover and result.get('cover_path'):
                        logger.info(f"✅ 封面下载成功: {result['cover_path']}")
                else:
                    logger.error(f"❌ 下载失败: {result['error']}")
                    
            except Exception as e:
                error_result = {
                    'success': False,
                    'url': url,
                    'error': str(e)
                }
                results.append(error_result)
                logger.error(f"❌ 下载失败: {e}")
        
        total_duration = time.time() - total_start_time
        success_count = sum(1 for r in results if r['success'])
        
        logger.info(f"批量下载完成，成功: {success_count}/{len(urls)}，总耗时: {total_duration:.2f}秒")
        
        return results
    
    async def get_video_info_from_url(self, url: str) -> Dict[str, Any]:
        """
        从URL获取视频信息（不下载）
        
        Args:
            url: 抖音视频URL
            
        Returns:
            视频信息
        """
        try:
            # 处理短链接
            if 'v.douyin.com' in url:
                real_url = await self.resolve_short_url(url)
                if real_url:
                    url = real_url
            
            # 提取aweme_id
            aweme_id = self.extract_aweme_id_from_url(url)
            if not aweme_id:
                raise Exception("无法从URL中提取视频ID")
            
            return await self.get_video_info(aweme_id)
            
        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            return {
                'success': False,
                'url': url,
                'error': str(e)
            }


class DouyinAudioAPI:
    """抖音音频API - 高级接口"""
    
    def __init__(self, output_dir: str = "downloads", proxies: dict = None, 
                 max_retries: int = 3, timeout: int = 30):
        """
        初始化API
        
        Args:
            output_dir: 下载文件保存目录
            proxies: 代理设置
            max_retries: 最大重试次数
            timeout: 请求超时时间
        """
        self.downloader = DouyinAudioDownloader(output_dir, proxies, max_retries, timeout)
    
    async def download_from_url(self, url: str, filename: str = None, 
                              download_cover: bool = False, cover_format: str = "jpg") -> Dict[str, Any]:
        """
        从URL下载音频
        
        Args:
            url: 抖音视频URL
            filename: 自定义文件名（可选）
            download_cover: 是否同时下载封面
            cover_format: 封面图片格式
            
        Returns:
            下载结果
        """
        async with self.downloader:
            return await self.downloader.download_audio_from_url(url, filename, download_cover, cover_format)
    
    async def download_from_id(self, aweme_id: str, filename: str = None, 
                             download_cover: bool = False, cover_format: str = "jpg") -> Dict[str, Any]:
        """
        从ID下载音频
        
        Args:
            aweme_id: 视频ID
            filename: 自定义文件名（可选）
            download_cover: 是否同时下载封面
            cover_format: 封面图片格式
            
        Returns:
            下载结果
        """
        async with self.downloader:
            return await self.downloader.download_audio_from_aweme_id(aweme_id, filename, download_cover, cover_format)
    
    async def get_video_info(self, url_or_id: str) -> Dict[str, Any]:
        """
        获取视频信息
        
        Args:
            url_or_id: 抖音URL或视频ID
            
        Returns:
            视频信息
        """
        async with self.downloader:
            if url_or_id.startswith('http'):
                return await self.downloader.get_video_info_from_url(url_or_id)
            else:
                return await self.downloader.get_video_info(url_or_id)
    
    async def batch_download(self, urls: List[str], output_dir: str = None, 
                           download_cover: bool = False, cover_format: str = "jpg") -> List[Dict[str, Any]]:
        """
        批量下载
        
        Args:
            urls: URL列表
            output_dir: 输出目录（可选）
            download_cover: 是否同时下载封面
            cover_format: 封面图片格式
            
        Returns:
            下载结果列表
        """
        async with self.downloader:
            return await self.downloader.batch_download_audio(urls, output_dir, download_cover, cover_format)
    
    async def extract_aweme_id(self, url: str) -> Optional[str]:
        """
        从URL提取aweme_id
        
        Args:
            url: 抖音视频URL
            
        Returns:
            aweme_id
        """
        async with self.downloader:
            return self.downloader.extract_aweme_id_from_url(url)


# 便捷函数
async def download_douyin_audio(url: str, output_dir: str = "downloads", 
                               filename: str = None, proxies: dict = None,
                               download_cover: bool = False, cover_format: str = "jpg") -> Dict[str, Any]:
    """
    便捷函数：下载抖音音频
    
    Args:
        url: 抖音视频URL
        output_dir: 输出目录
        filename: 自定义文件名（可选）
        proxies: 代理设置（可选）
        download_cover: 是否同时下载封面
        cover_format: 封面图片格式
        
    Returns:
        下载结果
    """
    api = DouyinAudioAPI(output_dir, proxies)
    return await api.download_from_url(url, filename, download_cover, cover_format)


async def get_douyin_video_info(url: str, proxies: dict = None) -> Dict[str, Any]:
    """
    便捷函数：获取抖音视频信息
    
    Args:
        url: 抖音视频URL
        proxies: 代理设置（可选）
        
    Returns:
        视频信息
    """
    api = DouyinAudioAPI(proxies=proxies)
    return await api.get_video_info(url)


async def batch_download_douyin_audio(urls: List[str], output_dir: str = "downloads", 
                                    proxies: dict = None, download_cover: bool = False, 
                                    cover_format: str = "jpg") -> List[Dict[str, Any]]:
    """
    便捷函数：批量下载抖音音频
    
    Args:
        urls: 抖音视频URL列表
        output_dir: 输出目录
        proxies: 代理设置（可选）
        download_cover: 是否同时下载封面
        cover_format: 封面图片格式
        
    Returns:
        下载结果列表
    """
    api = DouyinAudioAPI(output_dir, proxies)
    return await api.batch_download(urls, download_cover=download_cover, cover_format=cover_format)


# 使用示例
if __name__ == "__main__":
    async def main():
        # 示例1: 下载单个视频音频（包含封面）
        try:
            result = await download_douyin_audio(
                "https://www.douyin.com/video/7534721921339723065",
                output_dir="my_downloads",
                download_cover=True,  # 同时下载封面
                cover_format="jpg"    # 封面格式
            )
            print(f"下载成功: {result}")
            if result.get('cover_path'):
                print(f"封面下载成功: {result['cover_path']}")
        except Exception as e:
            print(f"下载失败: {e}")
        
        # 示例2: 获取视频信息
        try:
            info = await get_douyin_video_info("https://www.douyin.com/video/7534721921339723065")
            print(f"视频信息: {info}")
        except Exception as e:
            print(f"获取信息失败: {e}")
        
        # 示例3: 批量下载（包含封面）
        urls = [
            "https://www.douyin.com/video/7534721921339723065",
            # 添加更多URL进行测试
        ]
        
        api = DouyinAudioAPI(output_dir="batch_downloads")
        results = await api.batch_download(urls, download_cover=True, cover_format="jpg")
        for result in results:
            if result['success']:
                print(f"✅ 音频: {result['file_path']}")
                if result.get('cover_path'):
                    print(f"✅ 封面: {result['cover_path']}")
            else:
                print(f"❌ {result['error']}")
    
    # 运行示例
    asyncio.run(main())
