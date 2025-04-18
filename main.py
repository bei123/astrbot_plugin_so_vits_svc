#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
So-Vits-SVC API 插件
提供语音转换、MSST音频处理和网易云音乐下载功能
"""

from typing import Optional, Dict, List, AsyncGenerator, Any
import os
import time
import uuid
import requests
import json
import aiohttp
import hashlib
import shutil
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star import Star, Context
from astrbot.api.event.filter import command, permission_type
from astrbot.api.star import register
from astrbot.core.config import AstrBotConfig
from astrbot.core import logger
from astrbot.core.message.components import Record
from astrbot.core.star.filter.permission import PermissionType
from astrbot.api.event import filter
from astrbot.core.star.filter.command import Command
from .netease_api import NeteaseMusicAPI
from .bilibili_api import BilibiliAPI
import asyncio
from concurrent.futures import ThreadPoolExecutor
from astrbot.api.event import filter

class MSSTProcessor:
    """MSST 音频处理器"""

    def __init__(self, api_url: str = "http://localhost:9000"):
        """初始化 MSST 处理器

        Args:
            api_url: MSST-WebUI API 地址
        """
        self.api_url = api_url
        self.session = requests.Session()
        self.available_presets = self.get_presets()

    def get_presets(self) -> List[str]:
        """获取可用的预设列表

        Returns:
            预设文件列表
        """
        try:
            response = self.session.get(f"{self.api_url}/presets")
            if response.status_code == 200:
                result = response.json()
                if result.get("status") == "success":
                    return result.get("presets", [])
            logger.error(f"获取预设列表失败: {response.text}")
            return []
        except Exception as e:
            logger.error(f"获取预设列表出错: {str(e)}")
            return []

    def find_available_preset(self, preferred_preset: str = "wav.json") -> str:
        """查找可用的预设文件

        Args:
            preferred_preset: 首选的预设文件名

        Returns:
            可用的预设文件名
        """
        if preferred_preset in self.available_presets:
            return os.path.join("presets", preferred_preset)

        for preset in self.available_presets:
            if preset.endswith(".json"):
                return os.path.join("presets", preset)

        return os.path.join("presets", preferred_preset)

    def process_audio(
        self, input_file: str, preset_name: str = "wav.json"
    ) -> Optional[str]:
        """处理音频文件

        Args:
            input_file: 输入音频文件路径
            preset_name: 预设文件名

        Returns:
            处理后的音频文件路径，失败返回 None
        """
        try:
            available_preset = self.find_available_preset(preset_name)
            logger.info(f"使用预设文件: {available_preset}")

            with open(input_file, "rb") as f:
                audio_data = f.read()

            files = {"input_file": ("input.wav", audio_data, "audio/wav")}
            data = {
                "preset_path": available_preset,
                "output_format": "wav",
                "extra_output_dir": "false",
            }

            response = self.session.post(
                f"{self.api_url}/infer/local", files=files, data=data
            )

            if response.status_code == 200:
                result = response.json()
                if result["status"] == "success":
                    output_files = self.session.get(
                        f"{self.api_url}/list_outputs"
                    ).json()
                    if output_files and output_files["files"]:
                        output_file = output_files["files"][0]
                        download_url = f"{self.api_url}/download/{output_file['name']}"
                        download_response = self.session.get(download_url)

                        if download_response.status_code == 200:
                            output_path = os.path.join(
                                os.path.dirname(input_file),
                                f"processed_{os.path.basename(input_file)}",
                            )
                            with open(output_path, "wb") as f:
                                f.write(download_response.content)
                            return output_path

            logger.error(f"MSST 处理失败: {response.text}")
            return None

        except Exception as e:
            logger.error(f"MSST 处理出错: {str(e)}")
            return None


class VoiceConverter:
    """语音转换器"""

    def __init__(self, config: Dict = None):
        """初始化语音转换器

        Args:
            config: 插件配置字典
        """
        self.config = config or {}
        self.base_setting = self.config.get("base_setting", {})
        self.voice_config = self.config.get("voice_config", {})
        self.cache_config = self.config.get("cache_config", {})
        self.executor = ThreadPoolExecutor(max_workers=1)  # 限制同时只能处理一个转换任务
        self.current_task = None  # 当前正在执行的任务
        self.task_lock = asyncio.Lock()  # 任务锁

        # API 设置
        self.api_url = self.base_setting.get("base_url", "http://localhost:1145")
        self.msst_url = self.base_setting.get("msst_url", "http://localhost:9000")
        self.msst_preset = self.base_setting.get("msst_preset", "wav.json")
        self.timeout = self.base_setting.get("timeout", 300)

        # 语音转换设置
        self.max_queue_size = self.voice_config.get("max_queue_size", 100)
        self.default_speaker = self.voice_config.get("default_speaker", "0")
        self.default_pitch = self.voice_config.get("default_pitch", 0)
        self.default_k_step = self.voice_config.get("default_k_step", 100)
        self.default_shallow_diffusion = self.voice_config.get("default_shallow_diffusion", True)
        self.default_only_diffusion = self.voice_config.get("default_only_diffusion", False)
        self.default_cluster_infer_ratio = self.voice_config.get("default_cluster_infer_ratio", 0)
        self.default_auto_predict_f0 = self.voice_config.get("default_auto_predict_f0", False)
        self.default_noice_scale = self.voice_config.get("default_noice_scale", 0.4)
        self.default_f0_filter = self.voice_config.get("default_f0_filter", False)
        self.default_f0_predictor = self.voice_config.get("default_f0_predictor", "fcpe")
        self.default_enhancer_adaptive_key = self.voice_config.get("default_enhancer_adaptive_key", 0)
        self.default_cr_threshold = self.voice_config.get("default_cr_threshold", 0.05)

        # 缓存设置
        self.cache_enabled = self.cache_config.get("enabled", True)
        self.cache_expire_days = self.cache_config.get("expire_days", 7)
        self.cache_dir = self.cache_config.get("cache_dir", "data/cache/so-vits-svc")
        if self.cache_enabled:
            os.makedirs(self.cache_dir, exist_ok=True)
            self._clean_expired_cache()

        # 初始化组件
        self.session = requests.Session()
        self.msst_processor = MSSTProcessor(self.msst_url)
        self.netease_api = NeteaseMusicAPI(self.config)
        self.bilibili_api = BilibiliAPI(self.config)

    def check_health(self) -> Optional[Dict]:
        """检查服务健康状态

        Returns:
            健康状态信息字典，失败返回 None
        """
        try:
            response = self.session.get(f"{self.api_url}/health")
            return response.json()
        except Exception as e:
            logger.error(f"健康检查失败: {str(e)}")
            return None

    def _generate_cache_key(self, input_file: str, speaker_id: str, pitch_adjust: int, **kwargs) -> str:
        """生成缓存键

        Args:
            input_file: 输入文件路径
            speaker_id: 说话人ID
            pitch_adjust: 音高调整值
            **kwargs: 其他参数

        Returns:
            str: 缓存键
        """
        # 读取文件内容的MD5
        with open(input_file, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        # 组合参数
        params = {
            "file_hash": file_hash,
            "speaker_id": speaker_id,
            "pitch_adjust": pitch_adjust,
            **kwargs
        }

        # 生成参数字符串的MD5
        params_str = json.dumps(params, sort_keys=True)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()

        return f"{file_hash}_{params_hash}"

    def _get_cache_path(self, cache_key: str) -> str:
        """获取缓存文件路径

        Args:
            cache_key: 缓存键

        Returns:
            str: 缓存文件路径
        """
        return os.path.join(self.cache_dir, f"{cache_key}.wav")

    def _get_from_cache(self, cache_key: str) -> Optional[str]:
        """从缓存中获取文件

        Args:
            cache_key: 缓存键

        Returns:
            Optional[str]: 缓存文件路径，不存在返回None
        """
        if not self.cache_enabled:
            return None

        cache_path = self._get_cache_path(cache_key)
        if os.path.exists(cache_path):
            # 检查文件是否过期
            mtime = os.path.getmtime(cache_path)
            if time.time() - mtime < self.cache_expire_days * 24 * 3600:
                return cache_path
            else:
                # 删除过期文件
                try:
                    os.remove(cache_path)
                except Exception as e:
                    logger.error(f"删除过期缓存文件失败: {e}")
        return None

    def _save_to_cache(self, cache_key: str, file_path: str) -> None:
        """保存文件到缓存

        Args:
            cache_key: 缓存键
            file_path: 文件路径
        """
        if not self.cache_enabled:
            return

        try:
            cache_path = self._get_cache_path(cache_key)
            shutil.copy2(file_path, cache_path)
            logger.info(f"已保存到缓存: {cache_path}")
        except Exception as e:
            logger.error(f"保存到缓存失败: {e}")

    def _clean_expired_cache(self) -> None:
        """清理过期的缓存文件"""
        if not self.cache_enabled:
            return

        try:
            current_time = time.time()
            expire_time = current_time - self.cache_expire_days * 24 * 3600

            for filename in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, filename)
                if os.path.getmtime(file_path) < expire_time:
                    try:
                        os.remove(file_path)
                        logger.info(f"已删除过期缓存文件: {file_path}")
                    except Exception as e:
                        logger.error(f"删除过期缓存文件失败: {e}")
        except Exception as e:
            logger.error(f"清理过期缓存失败: {e}")

    async def convert_voice_async(
        self,
        input_wav: str,
        output_wav: str,
        speaker_id: str,
        pitch_adjust: int = 0,
        f0_method: str = "crepe",
        index_rate: float = 0.5,
        filter_radius: int = 3,
        resample_rate: int = 48000,
        **kwargs
    ) -> bool:
        """异步转换语音

        Args:
            input_wav: 输入音频文件路径
            output_wav: 输出音频文件路径
            speaker_id: 说话人ID
            pitch_adjust: 音高调整值
            f0_method: 音高提取方法
            index_rate: 索引率
            filter_radius: 滤波半径
            resample_rate: 重采样率
            **kwargs: 其他参数

        Returns:
            bool: 是否转换成功
        """
        try:
            # 检查服务是否健康
            if not self.check_health():
                logger.error("服务不健康，无法进行转换")
                return False

            # 检查输入文件是否存在
            if not os.path.exists(input_wav):
                logger.error(f"输入文件不存在: {input_wav}")
                return False

            # 生成缓存键
            cache_key = self._generate_cache_key(
                input_wav,
                speaker_id,
                pitch_adjust,
                f0_method=f0_method,
                index_rate=index_rate,
                filter_radius=filter_radius,
                resample_rate=resample_rate,
                **kwargs
            )

            # 检查缓存
            if self.cache_enabled:
                cached_file = self._get_from_cache(cache_key)
                if cached_file:
                    logger.info(f"使用缓存文件: {cached_file}")
                    shutil.copy2(cached_file, output_wav)
                    return True

            # 准备请求参数
            params = {
                "speaker_id": speaker_id,
                "pitch_adjust": pitch_adjust,
                "f0_method": f0_method,
                "index_rate": index_rate,
                "filter_radius": filter_radius,
                "resample_rate": resample_rate,
                **kwargs
            }

            # 记录转换参数
            logger.info(f"开始异步转换语音，参数: {params}")

            # 发送异步请求
            async with aiohttp.ClientSession() as session:
                with open(input_wav, "rb") as f:
                    data = aiohttp.FormData()
                    data.add_field("audio", f)
                    for key, value in params.items():
                        data.add_field(key, str(value))

                    async with session.post(
                        f"{self.api_url}/convert",
                        data=data,
                        timeout=self.timeout
                    ) as response:
                        if response.status != 200:
                            logger.error(f"转换失败，状态码: {response.status}")
                            return False

                        # 保存结果
                        content = await response.read()
                        with open(output_wav, "wb") as f:
                            f.write(content)

            # 缓存结果
            if self.cache_enabled:
                self._save_to_cache(cache_key, output_wav)

            logger.info(f"异步转换成功，输出文件: {output_wav}")
            return True

        except Exception as e:
            logger.error(f"异步转换失败: {e}")
            logger.error(f"转换失败: {e}")
            return False


@register(
    name="so-vits-svc-api",
    author="Soulter",
    desc="So-Vits-SVC API 语音转换插件",
    version="1.2.1",
)
class SoVitsSvcPlugin(Star):
    """So-Vits-SVC API 插件主类"""

    def __init__(self, context: Context, config: AstrBotConfig):
        """初始化插件

        Args:
            context: 插件上下文
            config: 插件配置
        """
        super().__init__(context)
        self.config = config
        self._init_config()
        self.conversion_tasks = {}  # 存储正在进行的转换任务
        
        # 从配置中读取缓存设置
        cache_config = self.config.get("so_vits_svc_api", {}).get("cache_config", {})
        self.cache_enabled = cache_config.get("cache_enabled", True)  # 默认启用缓存
        self.cache_expire_days = cache_config.get("cache_expire_days", 7)  # 默认缓存7天
        self.cache_dir = cache_config.get("cache_dir", "data/cache/so-vits-svc")  # 默认缓存目录

    @staticmethod
    def config(config: AstrBotConfig) -> Dict:
        """定义插件配置结构

        Args:
            config: AstrBot配置对象

        Returns:
            Dict: 配置结构定义
        """
        return {
            "so_vits_svc_api": {
                "description": "So-Vits-SVC API 插件配置",
                "type": "object",
                "items": {
                    "base_setting": {
                        "description": "基础设置",
                        "type": "object",
                        "items": {
                            "base_url": {
                                "description": "API服务器地址",
                                "type": "string",
                                "hint": "如果是本地部署，可以使用 http://127.0.0.1:1145",
                                "default": "http://localhost:1145",
                            },
                            "timeout": {
                                "description": "请求超时时间(秒)",
                                "type": "integer",
                                "hint": "转换请求的超时时间",
                                "default": 300,
                            },
                            "msst_url": {
                                "description": "MSST-WebUI API地址",
                                "type": "string",
                                "hint": "MSST-WebUI 的 API 地址",
                                "default": "http://localhost:9000",
                            },
                            "msst_preset": {
                                "description": "MSST预设文件路径",
                                "type": "string",
                                "hint": "MSST 处理使用的预设文件路径",
                                "default": "wav.json",
                            },
                            "netease_cookie": {
                                "description": "网易云音乐Cookie",
                                "type": "string",
                                "hint": "用于访问网易云音乐API的Cookie",
                                "default": "",
                            },
                            "bbdown_path": {
                                "description": "BBDown可执行文件路径",
                                "type": "string",
                                "hint": "BBDown可执行文件的路径，如果已添加到PATH中，可以直接使用BBDown",
                                "default": "BBDown",
                            },
                            "bbdown_cookie": {
                                "description": "哔哩哔哩Cookie",
                                "type": "string",
                                "hint": "用于访问哔哩哔哩API的Cookie，格式为SESSDATA=xxx;bili_jct=xxx;DedeUserID=xxx",
                                "default": "",
                            },
                        },
                    },
                    "voice_config": {
                        "description": "语音转换设置",
                        "type": "object",
                        "hint": "语音转换的相关参数设置",
                        "items": {
                            "max_queue_size": {
                                "description": "最大队列大小",
                                "type": "integer",
                                "hint": "超过此队列大小将拒绝新的转换请求",
                                "default": 100,
                            },
                            "default_speaker": {
                                "description": "默认说话人ID",
                                "type": "string",
                                "hint": "默认使用的说话人ID",
                                "default": "0",
                            },
                            "default_pitch": {
                                "description": "默认音调调整",
                                "type": "integer",
                                "hint": "默认的音调调整值，范围-12到12",
                                "default": 0,
                            },
                            "default_k_step": {
                                "description": "默认扩散步数",
                                "type": "integer",
                                "hint": "默认的扩散步数",
                                "default": 100,
                            },
                            "default_shallow_diffusion": {
                                "description": "默认使用浅扩散",
                                "type": "boolean",
                                "hint": "是否默认使用浅扩散",
                                "default": True,
                            },
                            "default_only_diffusion": {
                                "description": "默认使用纯扩散",
                                "type": "boolean",
                                "hint": "是否默认使用纯扩散",
                                "default": False,
                            },
                            "default_cluster_infer_ratio": {
                                "description": "默认聚类推理比例",
                                "type": "float",
                                "hint": "默认的聚类推理比例",
                                "default": 0,
                            },
                            "default_auto_predict_f0": {
                                "description": "默认自动预测音高",
                                "type": "boolean",
                                "hint": "是否默认自动预测音高",
                                "default": False,
                            },
                            "default_noice_scale": {
                                "description": "默认噪声比例",
                                "type": "float",
                                "hint": "默认的噪声比例",
                                "default": 0.4,
                            },
                            "default_f0_filter": {
                                "description": "默认过滤F0",
                                "type": "boolean",
                                "hint": "是否默认过滤F0",
                                "default": False,
                            },
                            "default_f0_predictor": {
                                "description": "默认F0预测器",
                                "type": "string",
                                "hint": "默认使用的F0预测器",
                                "default": "fcpe",
                            },
                            "default_enhancer_adaptive_key": {
                                "description": "默认增强器自适应键",
                                "type": "integer",
                                "hint": "默认的增强器自适应键值",
                                "default": 0,
                            },
                            "default_cr_threshold": {
                                "description": "默认交叉参考阈值",
                                "type": "float",
                                "hint": "默认的交叉参考阈值",
                                "default": 0.05,
                            },
                        },
                    },
                    "cache_config": {
                        "description": "缓存配置",
                        "type": "object",
                        "items": {
                            "cache_enabled": {
                                "description": "是否启用缓存",
                                "type": "boolean",
                                "hint": "是否启用转换结果缓存",
                                "default": True,
                            },
                            "cache_expire_days": {
                                "description": "缓存过期天数",
                                "type": "integer",
                                "hint": "缓存文件保留的天数，超过此天数将自动删除",
                                "default": 7,
                            },
                            "cache_dir": {
                                "description": "缓存目录",
                                "type": "string",
                                "hint": "缓存文件存储的目录",
                                "default": "data/cache/so-vits-svc",
                            },
                        },
                    },
                },
            }
        }

    def _init_config(self) -> None:
        """初始化配置"""
        self.converter = VoiceConverter(self.config)
        self.temp_dir = "data/temp/so-vits-svc"
        
        # 从配置中读取缓存目录
        cache_config = self.config.get("so_vits_svc_api", {}).get("cache_config", {})
        self.cache_dir = cache_config.get("cache_dir", "data/cache/so-vits-svc")
        
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 清理过期缓存
        self._clean_expired_cache()

    def _generate_cache_key(self, input_wav: str, speaker_id: int, pitch_adjust: float = 0.0) -> str:
        """生成缓存键

        Args:
            input_wav: 输入音频文件路径
            speaker_id: 说话人ID
            pitch_adjust: 音高调整值

        Returns:
            str: 缓存键
        """
        # 使用文件内容的哈希值作为缓存键的一部分
        with open(input_wav, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        
        # 组合参数生成缓存键
        cache_key = f"{file_hash}_{speaker_id}_{pitch_adjust}"
        return cache_key

    def _get_cached_file(self, cache_key: str) -> Optional[str]:
        """获取缓存的文件

        Args:
            cache_key: 缓存键

        Returns:
            Optional[str]: 缓存文件路径，如果不存在则返回None
        """
        if not self.cache_enabled:
            return None
            
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.wav")
        if os.path.exists(cache_file):
            # 检查文件是否过期
            file_time = os.path.getmtime(cache_file)
            if time.time() - file_time < self.cache_expire_days * 24 * 3600:
                return cache_file
            else:
                # 删除过期文件
                os.remove(cache_file)
        return None

    def _save_to_cache(self, cache_key: str, file_path: str) -> None:
        """保存文件到缓存

        Args:
            cache_key: 缓存键
            file_path: 要缓存的文件路径
        """
        if not self.cache_enabled:
            return
            
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.wav")
        shutil.copy2(file_path, cache_file)

    def _clean_expired_cache(self) -> None:
        """清理过期的缓存文件"""
        if not os.path.exists(self.cache_dir):
            return
            
        current_time = time.time()
        for filename in os.listdir(self.cache_dir):
            file_path = os.path.join(self.cache_dir, filename)
            if os.path.isfile(file_path):
                if current_time - os.path.getmtime(file_path) > self.cache_expire_days * 86400:
                    os.remove(file_path)

    @command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """测试插件是否正常工作"""
        yield event.plain_result("So-Vits-SVC 插件已加载！")

    @permission_type(PermissionType.ADMIN)
    @command("svc_status")
    async def check_status(self, event: AstrMessageEvent):
        """检查服务状态"""
        health = self.converter.check_health()
        if not health:
            yield event.plain_result(
                "服务未就绪，请检查 So-Vits-SVC API 服务是否已启动。"
            )
            return

        status = "✅ 服务正常运行\n"
        status += (
            f"模型加载状态: {'已加载' if health.get('model_loaded') else '未加载'}\n"
        )
        status += f"当前队列大小: {health.get('queue_size', 0)}\n"
        status += f"So-Vits-SVC API 地址: {self.converter.api_url}\n"
        status += f"MSST-WebUI API 地址: {self.converter.msst_url}\n"
        status += f"MSST 预设: {self.converter.msst_preset}\n"
        status += f"默认说话人ID: {self.converter.default_speaker}\n"
        status += f"默认音调调整: {self.converter.default_pitch}"

        yield event.plain_result(status)

    @filter.command("唱", alias={"牢剑唱", "转换"})
    async def handle_convert_voice(self, event: AstrMessageEvent):
        """转换语音

        用法：
            1. /convert_voice [说话人ID] [音调调整] - 上传音频文件进行转换
            2. /convert_voice [说话人ID] [音调调整] [歌曲名] - 搜索并转换网易云音乐
            3. /convert_voice [说话人ID] [音调调整] bilibili [BV号或链接] - 转换哔哩哔哩视频
        """
        # 解析参数
        message = event.message_str.strip()
        args = message.split()[1:] if message else []
        speaker_id = None
        pitch_adjust = None
        song_name = None
        source_type = "file"  # 默认为文件上传

        if len(args) >= 2:
            speaker_id = args[0]
            try:
                pitch_adjust = int(args[1])
                if not -12 <= pitch_adjust <= 12:
                    raise ValueError("音调调整必须在-12到12之间")
            except ValueError as e:
                yield event.plain_result(f"参数错误：{str(e)}")
                return

            if len(args) > 2:
                # 检查是否指定了来源类型
                if args[2].lower() == "bilibili":
                    source_type = "bilibili"
                    if len(args) > 3:
                        song_name = " ".join(args[3:])
                else:
                    song_name = " ".join(args[2:])

        # 生成临时文件路径
        input_file = os.path.join(self.temp_dir, f"input_{uuid.uuid4()}.wav")
        output_file = os.path.join(self.temp_dir, f"output_{uuid.uuid4()}.wav")

        try:
            # 根据来源类型处理音频
            if source_type == "bilibili" and song_name:
                try:
                    yield event.plain_result(f"正在处理哔哩哔哩视频：{song_name}...")
                    
                    # 检查BBDown配置
                    if not self.converter.bilibili_api.bbdown_path:
                        yield event.plain_result("错误：未配置BBDown路径，请在插件配置中设置bbdown_path")
                        return
                        
                    # 检查BBDown是否存在
                    if not os.path.exists(self.converter.bilibili_api.bbdown_path):
                        yield event.plain_result(f"错误：BBDown可执行文件不存在: {self.converter.bilibili_api.bbdown_path}\n请确保BBDown已正确安装并配置")
                        return
                        
                    # 检查BBDown是否有执行权限
                    if not os.access(self.converter.bilibili_api.bbdown_path, os.X_OK):
                        yield event.plain_result(f"错误：BBDown可执行文件没有执行权限: {self.converter.bilibili_api.bbdown_path}\n请在服务器上执行: chmod +x {self.converter.bilibili_api.bbdown_path}")
                        return
                    
                    video_info = self.converter.bilibili_api.process_video(song_name)

                    if not video_info:
                        yield event.plain_result(f"处理视频失败：{song_name}")
                        return

                    yield event.plain_result(
                        f"找到视频：{video_info.get('title', '未知视频')} - {video_info.get('uploader', '未知UP主')}\n"
                        f"正在下载音频..."
                    )

                    downloaded_file = video_info.get("audio_file")
                    if not downloaded_file or not os.path.exists(downloaded_file):
                        yield event.plain_result("下载音频失败！")
                        return

                    # 将下载的音频文件复制到输入文件路径
                    shutil.copy2(downloaded_file, input_file)

                except Exception as e:
                    logger.error(f"处理哔哩哔哩视频时出错: {str(e)}")
                    yield event.plain_result(f"处理/下载视频时出错：{str(e)}")
                    return
            elif song_name:
                try:
                    yield event.plain_result(f"正在搜索歌曲：{song_name}...")
                    song_info = self.converter.netease_api.get_song_with_highest_quality(song_name)

                    if not song_info:
                        yield event.plain_result(f"未找到歌曲：{song_name}")
                        return

                    if not song_info.get("url"):
                        yield event.plain_result("无法获取歌曲下载链接，可能是版权限制。")
                        return

                    yield event.plain_result(
                        f"找到歌曲：{song_info.get('name', '未知歌曲')} - {song_info.get('ar_name', '未知歌手')}\n"
                        f"音质：{song_info.get('level', '未知音质')}\n"
                        f"大小：{song_info.get('size', '未知大小')}\n"
                        f"正在下载..."
                    )

                    downloaded_file = self.converter.netease_api.download_song(song_info, self.temp_dir)
                    if not downloaded_file:
                        yield event.plain_result("下载歌曲失败！")
                        return

                    if os.path.exists(downloaded_file):
                        os.rename(downloaded_file, input_file)
                    else:
                        yield event.plain_result("下载的文件不存在！")
                        return

                except Exception as e:
                    logger.error(f"处理网易云音乐时出错: {str(e)}")
                    yield event.plain_result(f"搜索/下载歌曲时出错：{str(e)}")
                    return

            # 否则检查是否有上传的音频文件
            else:
                if not hasattr(event.message_obj, "files") or not event.message_obj.files:
                    yield event.plain_result(
                        "请上传要转换的音频文件或指定歌曲名！\n"
                        "用法：\n"
                        "1. /convert_voice [说话人ID] [音调调整] - 上传音频文件\n"
                        "2. /convert_voice [说话人ID] [音调调整] [歌曲名] - 搜索网易云音乐\n"
                        "3. /convert_voice [说话人ID] [音调调整] bilibili [BV号或链接] - 转换哔哩哔哩视频"
                    )
                    return

                file = event.message_obj.files[0]
                filename = file.name if hasattr(file, "name") else str(file)
                if not filename.lower().endswith((".wav", ".mp3")):
                    yield event.plain_result("只支持 WAV 或 MP3 格式的音频文件！")
                    return

                yield event.plain_result("正在处理上传的音频文件...")
                if hasattr(file, "url"):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(file.url, timeout=self.converter.timeout) as response:
                            with open(input_file, "wb") as f:
                                f.write(await response.read())
                elif hasattr(file, "path"):
                    with open(file.path, "rb") as src, open(input_file, "wb") as dst:
                        dst.write(src.read())
                else:
                    yield event.plain_result("无法处理此类型的文件！")
                    return

            # 使用默认参数
            if speaker_id is None:
                speaker_id = self.converter.default_speaker
            if pitch_adjust is None:
                pitch_adjust = self.converter.default_pitch

            # 转换音频
            yield event.plain_result("正在转换音频，请稍候...")

            # 创建异步任务
            success = await self.converter.convert_voice_async(
                input_wav=input_file,
                output_wav=output_file,
                speaker_id=speaker_id,
                pitch_adjust=pitch_adjust
            )

            if success:
                yield event.plain_result("转换成功！正在发送文件...")
                chain = [Record.fromFileSystem(output_file)]
                yield event.chain_result(chain)
            else:
                yield event.plain_result("转换失败！请检查服务状态或参数是否正确。")

        except Exception as e:
            yield event.plain_result(f"转换过程中发生错误：{str(e)}")
        finally:
            # 清理临时文件
            try:
                if os.path.exists(input_file):
                    os.remove(input_file)
                if os.path.exists(output_file):
                    os.remove(output_file)
            except (OSError, IOError) as e:
                logger.error(f"清理临时文件失败: {str(e)}")

    @permission_type(PermissionType.ADMIN)
    @command("svc_speakers", alias=["说话人列表"])
    async def show_speakers(self, event: AstrMessageEvent):
        """展示当前可用的说话人列表，支持切换默认说话人

        用法：/svc_speakers [说话人ID]
        示例：/svc_speakers - 显示说话人列表
              /svc_speakers 1 - 设置默认说话人为1
        """
        message = event.message_str.strip()
        args = message.split()[1:] if message else []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.converter.api_url}/speakers",
                    timeout=self.converter.timeout
                ) as response:
                    if response.status != 200:
                        yield event.plain_result("获取说话人列表失败！")
                        return

                    speakers = await response.json()
                    if not speakers:
                        yield event.plain_result("当前没有可用的说话人")
                        return

                    if len(args) > 0:
                        speaker_id = args[0]
                        if speaker_id not in speakers:
                            yield event.plain_result(f"说话人 {speaker_id} 不存在！")
                            return

                        self.converter.default_speaker = speaker_id
                        self.config["voice_config"]["default_speaker"] = speaker_id
                        self.config.save_config()
                        yield event.plain_result(f"已将默认说话人设置为: {speaker_id}")
                        return

                    speaker_info = "下面列出了可用的说话人列表:\n"
                    for i, speaker in enumerate(speakers, 1):
                        speaker_info += f"{i}. {speaker}\n"

                    speaker_info += f"\n当前默认说话人: [{self.converter.default_speaker}]\n"
                    speaker_info += "Tips: 使用 /svc_speakers <说话人ID>，即可设置默认说话人"

                    yield event.plain_result(speaker_info)

        except Exception as e:
            yield event.plain_result(f"获取说话人列表失败：{str(e)}")

    @permission_type(PermissionType.ADMIN)
    @command("svc_presets", alias=["预设列表"])
    async def show_presets(self, event: AstrMessageEvent):
        """展示当前可用的预设列表"""
        try:
            presets = self.converter.msst_processor.get_presets()
            if not presets:
                yield event.plain_result(
                    "获取预设列表失败，请检查 MSST-WebUI 服务是否正常运行。"
                )
                return

            preset_info = "下面列出了可用的预设列表:\n"
            for i, preset in enumerate(presets, 1):
                preset_info += f"{i}. {preset}\n"

            preset_info += f"\n当前使用的预设: [{self.converter.msst_preset}]\n"
            preset_info += "Tips: 使用 /svc_presets 可以查看所有可用的预设"

            yield event.plain_result(preset_info)

        except Exception as e:
            yield event.plain_result(f"获取预设列表失败：{str(e)}")

    
    @command("bilibili_info")
    async def get_bilibili_info(self, event: AstrMessageEvent):
        """获取哔哩哔哩视频信息

        用法：/bilibili_info [BV号或链接]
        """
        message = event.message_str.strip()
        args = message.split()[1:] if message else []
        
        if not args:
            yield event.plain_result("请提供视频BV号或链接！\n用法：/bilibili_info [BV号或链接]")
            return
            
        url_or_bvid = args[0]
            
        try:
            yield event.plain_result(f"正在获取视频信息：{url_or_bvid}...")
            
            # 检查BBDown配置
            if not self.converter.bilibili_api.bbdown_path:
                yield event.plain_result("错误：未配置BBDown路径，请在插件配置中设置bbdown_path")
                return
                
            # 检查BBDown是否存在
            if not os.path.exists(self.converter.bilibili_api.bbdown_path):
                yield event.plain_result(f"错误：BBDown可执行文件不存在: {self.converter.bilibili_api.bbdown_path}\n请确保BBDown已正确安装并配置")
                return
                
            # 检查BBDown是否有执行权限
            if not os.access(self.converter.bilibili_api.bbdown_path, os.X_OK):
                yield event.plain_result(f"错误：BBDown可执行文件没有执行权限: {self.converter.bilibili_api.bbdown_path}\n请在服务器上执行: chmod +x {self.converter.bilibili_api.bbdown_path}")
                return
            
            video_info = self.converter.bilibili_api.get_video_info(url_or_bvid)
            
            if not video_info:
                yield event.plain_result(f"获取视频信息失败：{url_or_bvid}")
                return
                
            result = f"视频信息：\n"
            result += f"标题：{video_info['title']}\n"
            result += f"UP主：{video_info['uploader']}\n"
            result += f"分P数量：{len(video_info['parts'])}\n\n"
            
            if video_info['parts']:
                result += "分P列表：\n"
                for part in video_info['parts']:
                    result += f"{part['index']}. {part['title']} ({part['duration']})\n"
                    
            result += "\n使用方法：\n"
            result += f"/convert_voice [说话人ID] [音调调整] bilibili {url_or_bvid}"
            
            yield event.plain_result(result)
            
        except Exception as e:
            logger.error(f"获取哔哩哔哩视频信息出错: {str(e)}")
            yield event.plain_result(f"获取视频信息时出错：{str(e)}")

    @permission_type(PermissionType.ADMIN)
    @command("svc_cache_clear")
    async def clear_cache(self, event: AstrMessageEvent):
        """清理缓存"""
        try:
            if not os.path.exists(self.cache_dir):
                yield event.plain_result("缓存目录不存在，无需清理。")
                return
                
            count = 0
            for filename in os.listdir(self.cache_dir):
                if filename.endswith(".wav"):
                    file_path = os.path.join(self.cache_dir, filename)
                    try:
                        os.remove(file_path)
                        count += 1
                    except Exception as e:
                        logger.error(f"删除缓存文件失败: {str(e)}")
            
            yield event.plain_result(f"已清理 {count} 个缓存文件。")
        except Exception as e:
            logger.error(f"清理缓存失败: {str(e)}")
            yield event.plain_result(f"清理缓存失败: {str(e)}")
    
    @permission_type(PermissionType.ADMIN)
    @command("svc_cache_status")
    async def cache_status(self, event: AstrMessageEvent):
        """查看缓存状态"""
        try:
            if not os.path.exists(self.cache_dir):
                yield event.plain_result("缓存目录不存在。")
                return
                
            total_size = 0
            file_count = 0
            for filename in os.listdir(self.cache_dir):
                if filename.endswith(".wav"):
                    file_path = os.path.join(self.cache_dir, filename)
                    file_size = os.path.getsize(file_path)
                    total_size += file_size
                    file_count += 1
            
            # 格式化文件大小
            if total_size < 1024:
                size_str = f"{total_size} B"
            elif total_size < 1024 * 1024:
                size_str = f"{total_size / 1024:.2f} KB"
            elif total_size < 1024 * 1024 * 1024:
                size_str = f"{total_size / (1024 * 1024):.2f} MB"
            else:
                size_str = f"{total_size / (1024 * 1024 * 1024):.2f} GB"
            
            status = f"缓存状态:\n"
            status += f"缓存文件数量: {file_count}\n"
            status += f"缓存总大小: {size_str}\n"
            status += f"缓存过期天数: {self.cache_expire_days} 天\n"
            status += f"缓存状态: {'启用' if self.cache_enabled else '禁用'}"
            
            yield event.plain_result(status)
        except Exception as e:
            logger.error(f"获取缓存状态失败: {str(e)}")
            yield event.plain_result(f"获取缓存状态失败: {str(e)}")
    
    @permission_type(PermissionType.ADMIN)
    @command("svc_cache_toggle")
    async def toggle_cache(self, event: AstrMessageEvent):
        """切换缓存状态"""
        try:
            self.cache_enabled = not self.cache_enabled
            
            # 更新配置
            if "so_vits_svc_api" not in self.config:
                self.config["so_vits_svc_api"] = {}
            if "cache_config" not in self.config["so_vits_svc_api"]:
                self.config["so_vits_svc_api"]["cache_config"] = {}
            self.config["so_vits_svc_api"]["cache_config"]["cache_enabled"] = self.cache_enabled
            
            # 保存配置
            self.config.save_config()
            
            status = "启用" if self.cache_enabled else "禁用"
            yield event.plain_result(f"缓存已{status}。")
        except Exception as e:
            logger.error(f"切换缓存状态失败: {str(e)}")
            yield event.plain_result(f"切换缓存状态失败: {str(e)}")

    def _init_commands(self):
        """初始化命令"""
        self.commands.extend([
            Command(
                name="cache_status",
                description="查看缓存状态",
                usage="cache_status",
                handler=self._handle_cache_status
            ),
            Command(
                name="clear_cache",
                description="清理缓存",
                usage="clear_cache",
                handler=self._handle_clear_cache
            ),
            Command(
                name="toggle_cache",
                description="开启/关闭缓存",
                usage="toggle_cache [on/off]",
                handler=self._handle_toggle_cache
            )
        ])

    async def _handle_cache_status(self, event: AstrMessageEvent, args: List[str]) -> AsyncGenerator[Any, Any]:
        """处理缓存状态命令"""
        if not self.converter:
            yield event.plain_result("插件未初始化")
            return

        cache_dir = self.converter.cache_dir
        if not os.path.exists(cache_dir):
            yield event.plain_result("缓存目录不存在")
            return

        total_size = 0
        file_count = 0
        for root, _, files in os.walk(cache_dir):
            for file in files:
                file_path = os.path.join(root, file)
                total_size += os.path.getsize(file_path)
                file_count += 1

        status = (
            f"缓存状态:\n"
            f"启用状态: {'开启' if self.converter.cache_enabled else '关闭'}\n"
            f"缓存目录: {cache_dir}\n"
            f"文件数量: {file_count}\n"
            f"总大小: {total_size / 1024 / 1024:.2f} MB\n"
            f"过期时间: {self.converter.cache_expire_days} 天"
        )
        yield event.plain_result(status)

    async def _handle_clear_cache(self, event: AstrMessageEvent, args: List[str]) -> AsyncGenerator[Any, Any]:
        """处理清理缓存命令"""
        if not self.converter:
            yield event.plain_result("插件未初始化")
            return

        cache_dir = self.converter.cache_dir
        if not os.path.exists(cache_dir):
            yield event.plain_result("缓存目录不存在")
            return

        try:
            shutil.rmtree(cache_dir)
            os.makedirs(cache_dir, exist_ok=True)
            yield event.plain_result("缓存已清理")
        except Exception as e:
            yield event.plain_result(f"清理缓存失败: {str(e)}")

    async def _handle_toggle_cache(self, event: AstrMessageEvent, args: List[str]) -> AsyncGenerator[Any, Any]:
        """处理开启/关闭缓存命令"""
        if not self.converter:
            yield event.plain_result("插件未初始化")
            return

        if not args:
            # 切换状态
            self.converter.cache_enabled = not self.converter.cache_enabled
            yield event.plain_result(f"缓存已{'开启' if self.converter.cache_enabled else '关闭'}")
            return

        state = args[0].lower()
        if state in ["on", "true", "1"]:
            self.converter.cache_enabled = True
            yield event.plain_result("缓存已开启")
        elif state in ["off", "false", "0"]:
            self.converter.cache_enabled = False
            yield event.plain_result("缓存已关闭")
        else:
            yield event.plain_result("无效的参数，请使用 on/off")
