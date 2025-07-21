#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
So-Vits-SVC API 插件
提供语音转换、MSST音频处理和网易云音乐下载功能
"""

from typing import Optional, Dict, List, Tuple
import os
import time
import uuid
import aiohttp
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star import Star, Context
from astrbot.api.event.filter import command, permission_type
from astrbot.api.star import register
from astrbot.core.config import AstrBotConfig
from astrbot.core import logger
from astrbot.core.message.components import Record
from astrbot.core.star.filter.permission import PermissionType
from .netease_api import NeteaseMusicAPI
from .bilibili_api import BilibiliAPI
from .qqmusic_api import QQMusicAPI
from .cache_manager import CacheManager
import asyncio
from concurrent.futures import ThreadPoolExecutor
from astrbot.api.event import filter
from pedalboard import Pedalboard, Mix, Gain, HighpassFilter, PeakFilter, HighShelfFilter, Delay, Invert, Compressor, Reverb, Limiter
from pedalboard.io import AudioFile
import numpy as np
import psutil
import traceback
from pydub import AudioSegment
from .song import detect_chorus_api

class MSSTProcessor:
    """MSST 音频处理器"""

    def __init__(self, api_url: str = "http://localhost:9000"):
        """初始化 MSST 处理器

        Args:
            api_url: MSST-WebUI API 地址
        """
        self.api_url = api_url
        self.session = None
        self.available_presets = []
        self.batch_size = None  # 将由get_optimal_batch_size自动设置
        self.use_tta = False
        self.force_cpu = False

    async def initialize(self):
        """初始化处理器，获取预设列表"""
        self.available_presets = await self.get_presets()

    async def get_presets(self) -> List[str]:
        """获取可用的预设列表

        Returns:
            预设文件列表
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/presets") as response:
                    if response.status == 200:
                        result = await response.json()
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

    async def process_audio(
        self, input_file: str, preset_name: str = "wav.json"
    ) -> Optional[Dict]:
        """处理音频文件

        Args:
            input_file: 输入音频文件路径
            preset_name: 预设文件名

        Returns:
            处理结果字典，失败返回 None
        """
        max_retries = 3
        retry_delay = 5  # 秒

        for attempt in range(max_retries):
            try:
                logger.info(f"开始处理音频文件: {input_file}")
                logger.info(f"使用预设: {preset_name}")

                available_preset = self.find_available_preset(preset_name)
                logger.info(f"使用预设文件: {available_preset}")

                with open(input_file, "rb") as f:
                    audio_data = f.read()
                logger.info(f"读取音频文件成功，大小: {len(audio_data)} 字节")

                # 准备表单数据
                data = aiohttp.FormData()
                data.add_field("input_file",
                             audio_data,
                             filename="input.wav",
                             content_type="audio/wav")
                data.add_field("preset_path", available_preset)
                data.add_field("output_format", "wav")
                data.add_field("extra_output_dir", "false")
                data.add_field("use_tta", str(self.use_tta).lower())
                data.add_field("force_cpu", str(self.force_cpu).lower())

                # 发送请求
                try:
                    logger.info("发送MSST处理请求...")
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            f"{self.api_url}/infer/local",
                            data=data,
                            timeout=3000
                        ) as response:
                            if response.status == 200:
                                result = await response.json()
                                logger.info(f"MSST处理结果: {result}")
                                if result["status"] == "success":
                                    logger.info("MSST处理成功")
                                    return result
                                else:
                                    logger.error(f"MSST处理失败: {result.get('message', '未知错误')}")
                            else:
                                logger.error(f"MSST处理失败: {response.text}")

                except asyncio.TimeoutError:
                    logger.error("MSST处理请求超时")
                    if attempt < max_retries - 1:
                        logger.info(f"将在 {retry_delay} 秒后重试...")
                        await asyncio.sleep(retry_delay)
                        continue
                    return None
                except aiohttp.ClientError as e:
                    logger.error(f"MSST处理请求失败: {str(e)}")
                    if attempt < max_retries - 1:
                        logger.info(f"将在 {retry_delay} 秒后重试...")
                        await asyncio.sleep(retry_delay)
                        continue
                    return None

                return None

            except Exception as e:
                logger.error(f"MSST处理出错: {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"将在 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                    continue
                return None

    async def download_file(self, filename: str, output_path: str) -> bool:
        """下载处理后的文件

        Args:
            filename: 文件名
            output_path: 输出路径

        Returns:
            是否成功
        """
        try:
            logger.info(f"开始下载文件: {filename} -> {output_path}")

            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/download/{filename}", timeout=300) as response:
                    if response.status == 200:
                        with open(output_path, "wb") as f:
                            async for chunk in response.content.iter_chunked(8192):
                                if chunk:
                                    f.write(chunk)

                        # 验证文件
                        if os.path.exists(output_path):
                            file_size = os.path.getsize(output_path)
                            logger.info(f"文件下载成功: {output_path}, 大小: {file_size} 字节")
                            if file_size > 0:
                                return True
                            else:
                                logger.error(f"文件大小为0: {output_path}")
                                return False
                        else:
                            logger.error(f"文件不存在: {output_path}")
                            return False
                    else:
                        logger.error(f"下载文件失败: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"下载文件出错: {str(e)}")
            return False

    async def get_available_models(self) -> Optional[List[str]]:
        """获取可用的模型列表

        Returns:
            模型列表，失败返回 None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/models") as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("models", [])
                    return None
        except Exception as e:
            logger.error(f"获取模型列表失败: {str(e)}")
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
        self.mixing_config = self.config.get("mixing_config", {})
        self.executor = ThreadPoolExecutor(max_workers=1)  # 限制同时只能处理一个转换任务
        self.current_task = None  # 当前正在执行的任务
        self.task_lock = asyncio.Lock()  # 任务锁

        # 初始化临时目录
        self.temp_dir = os.path.join("data", "temp", "so-vits-svc")
        os.makedirs(self.temp_dir, exist_ok=True)
        logger.info(f"临时目录: {self.temp_dir}")

        # API 设置
        self.api_url = self.base_setting.get("base_url", "http://localhost:1145")
        self.msst_url = self.base_setting.get("msst_url", "http://localhost:9000")
        self.msst_preset = self.base_setting.get("msst_preset", "wav.json")
        self.model_dir = self.base_setting.get("model_dir", "default")  # 添加模型目录配置
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
        self.enable_mixing = self.voice_config.get("enable_mixing", True)

        # 混音设置
        self.sample_rate = self.mixing_config.get("sample_rate", 44100)
        self.headroom = self.mixing_config.get("headroom", -8)
        self.voc_input = self.mixing_config.get("voc_input", -4)
        self.revb_gain = self.mixing_config.get("revb_gain", 0)

        # 初始化组件
        self.msst_processor = MSSTProcessor(self.msst_url)
        self.netease_api = NeteaseMusicAPI(self.config)
        self.bilibili_api = BilibiliAPI(self.config)
        self.qqmusic_api = QQMusicAPI(self.config)

        # 初始化缓存管理器
        cache_config = self.config.get("cache_config", {})
        self.cache_manager = CacheManager(
            cache_dir=cache_config.get("cache_dir", "data/cache/so-vits-svc"),
            max_cache_size=cache_config.get("max_cache_size", 1024*1024*1024),  # 默认1GB
            max_cache_age=cache_config.get("max_cache_age", 7*24*60*60)  # 默认7天
        )

    async def get_available_models(self) -> Optional[List[str]]:
        """获取可用的模型列表

        Returns:
            模型列表，失败返回 None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/models") as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("models", [])
                    return None
        except Exception as e:
            logger.error(f"获取模型列表失败: {str(e)}")
            return None

    def _load_audio(self, path: str) -> np.ndarray:
        """加载音频文件

        Args:
            path: 音频文件路径

        Returns:
            音频数据
        """
        try:
            # 检查文件大小和内存
            file_size = os.path.getsize(path)
            is_safe, memory_warning = check_memory_safe(file_size)
            if not is_safe:
                raise MemoryError(memory_warning)

            with AudioFile(path).resampled_to(self.sample_rate) as audio:
                data = audio.read(audio.frames)

                # 检查加载后的数据大小
                data_size = data.nbytes
                is_safe, memory_warning = check_memory_safe(data_size)
                if not is_safe:
                    raise MemoryError(memory_warning)

                return data
        except Exception as e:
            logger.error(f"加载音频文件失败: {str(e)}\n{traceback.format_exc()}")
            raise

    def _process_vocal(self, audio: np.ndarray, release: int = 300, fb: int = 180) -> np.ndarray:
        """处理人声"""
        try:
            # 检查处理前的数据大小
            data_size = audio.nbytes
            is_safe, memory_warning = check_memory_safe(data_size)
            if not is_safe:
                raise MemoryError(memory_warning)

            vocal_board = Pedalboard([
                Gain(self.voc_input),
                HighpassFilter(230),
                PeakFilter(2700, -2, 1),
                HighShelfFilter(20000, -2, 1.8),
                Gain(1),
                PeakFilter(1400, 3, 1.15),
                PeakFilter(8500, 2.5, 1),
                Gain(-1),
                Mix([
                    Gain(0),
                    Pedalboard([
                        Invert(),
                        Compressor(-30, 3.2, 40, fb),
                        Gain(-40)
                    ])
                ]),
                Compressor(-18, 2.5, 19, release),
                Gain(0)
            ])

            processed = vocal_board(audio, self.sample_rate)

            # 检查处理后的数据大小
            processed_size = processed.nbytes
            is_safe, memory_warning = check_memory_safe(processed_size)
            if not is_safe:
                raise MemoryError(memory_warning)

            return processed
        except Exception as e:
            logger.error(f"处理人声失败: {str(e)}\n{traceback.format_exc()}")
            raise

    def _process_reverb(self, audio: np.ndarray, s: int = 5, m: int = 25, long_time: int = 50, d: int = 200) -> np.ndarray:
        """添加混响效果"""
        try:
            # 检查处理前的数据大小
            data_size = audio.nbytes
            is_safe, memory_warning = check_memory_safe(data_size)
            if not is_safe:
                raise MemoryError(memory_warning)

            delay = Pedalboard([
                Gain(-20),
                Delay(d/8, 0, 1),
                Gain(-12),
            ])

            short = Pedalboard([
                Gain(-20),
                Delay(s/1000, 0, 1),
                Reverb(0.2, 0.35, 1, 0, 1, 0),
                Gain(-12),
            ])

            medium = Pedalboard([
                Gain(-16),
                Delay(m/1000, 0.3, 1),
                Reverb(0.45, 0.55, 1, 0, 1, 0),
                Gain(-19),
            ])

            long = Pedalboard([
                Gain(-12),
                Delay(long_time/1000, 0.6, 1),
                Reverb(0.6, 0.7, 1, 0, 1, 0),
                Gain(-23)
            ])

            reverb_board = Pedalboard([
                Mix([short, medium, long, delay]),
                PeakFilter(1450, -4, 1.83),
                PeakFilter(2300, 5, 0.51),
                Gain(self.revb_gain),
            ])

            processed = reverb_board(audio, self.sample_rate)

            # 检查处理后的数据大小
            processed_size = processed.nbytes
            is_safe, memory_warning = check_memory_safe(processed_size)
            if not is_safe:
                raise MemoryError(memory_warning)

            return processed
        except Exception as e:
            logger.error(f"添加混响效果失败: {str(e)}\n{traceback.format_exc()}")
            raise

    def _process_instrument(self, audio: np.ndarray) -> np.ndarray:
        """处理伴奏

        Args:
            audio: 输入音频数据

        Returns:
            处理后的音频数据
        """
        inst_board = Pedalboard([Gain(self.headroom)])
        return inst_board(audio, self.sample_rate)

    def _process_master(self, audio: np.ndarray, comp_rel: int = 500, lim_rel: int = 400) -> np.ndarray:
        """母带处理

        Args:
            audio: 输入音频数据
            comp_rel: 压缩器释放时间
            lim_rel: 限制器释放时间

        Returns:
            处理后的音频数据
        """
        master_board = Pedalboard([
            Compressor(-10, 1.6, 10, comp_rel),
            Limiter(-3, lim_rel),
            Gain(-0.5)
        ])
        return master_board(audio, self.sample_rate)

    def mix_audio(self, vocal_path: str, inst_path: str, output_path: str) -> bool:
        """混合人声和伴奏"""
        try:
            # 检查输入文件大小
            vocal_size = os.path.getsize(vocal_path)
            inst_size = os.path.getsize(inst_path)

            # 检查总输入大小
            total_input_size = vocal_size + inst_size
            is_safe, memory_warning = check_memory_safe(total_input_size)
            if not is_safe:
                logger.error(f"混音内存不足: {memory_warning}")
                return False

            # 加载音频
            logger.info(f"加载人声音频: {vocal_path}")
            vocal = self._load_audio(vocal_path)
            logger.info(f"加载伴奏音频: {inst_path}")
            inst = self._load_audio(inst_path)

            # 处理人声
            logger.info("处理人声...")
            processed_vocal = self._process_vocal(vocal)
            stereo_vocal = np.tile(processed_vocal, (2, 1))

            # 添加混响
            logger.info("添加混响...")
            reverb_vocal = self._process_reverb(stereo_vocal)

            # 处理伴奏
            logger.info("处理伴奏...")
            processed_inst = self._process_instrument(inst)

            # 混合音频
            logger.info("混合音频...")
            min_length = min(processed_vocal.shape[1], processed_inst.shape[1])
            combined = processed_vocal[:, :min_length] + processed_inst[:, :min_length] + reverb_vocal[:, :min_length]

            # 检查混合后的数据大小
            combined_size = combined.nbytes
            is_safe, memory_warning = check_memory_safe(combined_size)
            if not is_safe:
                logger.error(f"混合音频内存不足: {memory_warning}")
                return False

            # 母带处理
            logger.info("母带处理...")
            final = self._process_master(combined)

            # 检查最终数据大小
            final_size = final.nbytes
            is_safe, memory_warning = check_memory_safe(final_size)
            if not is_safe:
                logger.error(f"母带处理内存不足: {memory_warning}")
                return False

            # 输出
            logger.info(f"保存混合后的音频: {output_path}")
            with AudioFile(
                output_path,
                "w",
                self.sample_rate,
                final.shape[0],
                bit_depth=16
            ) as output:
                output.write(final)

            # 清理内存
            del vocal, inst, processed_vocal, stereo_vocal, reverb_vocal, processed_inst, combined, final
            import gc
            gc.collect()

            logger.info("混音处理完成")
            return True

        except Exception as e:
            logger.error(f"混音处理失败: {str(e)}\n{traceback.format_exc()}")
            return False

    async def check_health(self) -> Optional[Dict]:
        """检查服务健康状态

        Returns:
            健康状态信息字典，失败返回 None
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/health") as response:
                    if response.status == 200:
                        result = await response.json()
                        return {
                            "status": result.get("status"),
                            "queue_size": result.get("queue_size", 0),
                            "active_tasks": result.get("active_tasks", 0),
                            "cached_models": result.get("cached_models", 0)
                        }
                    return None
        except Exception as e:
            logger.error(f"健康检查失败: {str(e)}")
            return None

    async def convert_voice_async(
        self,
        input_wav: str,
        output_wav: str,
        speaker_id: Optional[str] = None,
        pitch_adjust: Optional[int] = None,
        k_step: Optional[int] = None,
        shallow_diffusion: Optional[bool] = None,
        only_diffusion: Optional[bool] = None,
        cluster_infer_ratio: Optional[float] = None,
        auto_predict_f0: Optional[bool] = None,
        noice_scale: Optional[float] = None,
        f0_filter: Optional[bool] = None,
        f0_predictor: Optional[str] = None,
        enhancer_adaptive_key: Optional[int] = None,
        cr_threshold: Optional[float] = None,
        model_dir: Optional[str] = None,
    ) -> bool:
        """异步转换语音"""
        async with self.task_lock:  # 使用锁确保同一时间只有一个任务在执行
            if self.current_task is not None:
                logger.error("当前已有任务正在处理")
                return False

            try:
                self.current_task = asyncio.current_task()
                logger.info(f"开始异步语音转换任务，输入文件: {input_wav}")

                success = await self.convert_voice(
                    input_wav,
                    output_wav,
                    speaker_id,
                    pitch_adjust,
                    k_step,
                    shallow_diffusion,
                    only_diffusion,
                    cluster_infer_ratio,
                    auto_predict_f0,
                    noice_scale,
                    f0_filter,
                    f0_predictor,
                    enhancer_adaptive_key,
                    cr_threshold,
                    model_dir,
                )

                if not success:
                    logger.error("语音转换失败")
                    return False

                # 验证输出文件
                if not os.path.exists(output_wav):
                    logger.error(f"转换后的输出文件不存在: {output_wav}")
                    return False

                output_size = os.path.getsize(output_wav)
                if output_size == 0:
                    logger.error("转换后的输出文件大小为0")
                    return False

                logger.info(f"异步语音转换任务完成，输出文件: {output_wav}, 大小: {output_size} 字节")
                return True

            except Exception as e:
                logger.error(f"异步语音转换任务出错: {str(e)}")
                return False
            finally:
                self.current_task = None

    async def convert_voice(
        self,
        input_wav: str,
        output_wav: str,
        speaker_id: Optional[str] = None,
        pitch_adjust: Optional[int] = None,
        k_step: Optional[int] = None,
        shallow_diffusion: Optional[bool] = None,
        only_diffusion: Optional[bool] = None,
        cluster_infer_ratio: Optional[float] = None,
        auto_predict_f0: Optional[bool] = None,
        noice_scale: Optional[float] = None,
        f0_filter: Optional[bool] = None,
        f0_predictor: Optional[str] = None,
        enhancer_adaptive_key: Optional[int] = None,
        cr_threshold: Optional[float] = None,
        model_dir: Optional[str] = None,
    ) -> bool:
        """转换语音"""
        try:
            logger.info(f"开始语音转换流程，输入文件: {input_wav}, 输出文件: {output_wav}")

            # 检查输入文件大小
            input_size = os.path.getsize(input_wav)
            is_safe, memory_warning = check_memory_safe(input_size)
            if not is_safe:
                logger.error(f"转换语音内存不足: {memory_warning}")
                return False

            # 确保临时目录存在
            output_dir = os.path.dirname(output_wav)
            try:
                os.makedirs(output_dir, exist_ok=True)
                logger.info(f"确保输出目录存在: {output_dir}")
            except Exception as e:
                logger.error(f"创建输出目录失败: {str(e)}")
                return False

            # 使用默认值
            speaker_id = speaker_id or self.default_speaker
            pitch_adjust = pitch_adjust if pitch_adjust is not None else self.default_pitch
            k_step = k_step or self.default_k_step
            shallow_diffusion = shallow_diffusion if shallow_diffusion is not None else self.default_shallow_diffusion
            only_diffusion = only_diffusion if only_diffusion is not None else self.default_only_diffusion
            cluster_infer_ratio = cluster_infer_ratio if cluster_infer_ratio is not None else self.default_cluster_infer_ratio
            auto_predict_f0 = auto_predict_f0 if auto_predict_f0 is not None else self.default_auto_predict_f0
            noice_scale = noice_scale if noice_scale is not None else self.default_noice_scale
            f0_filter = f0_filter if f0_filter is not None else self.default_f0_filter
            f0_predictor = f0_predictor or self.default_f0_predictor
            enhancer_adaptive_key = enhancer_adaptive_key if enhancer_adaptive_key is not None else self.default_enhancer_adaptive_key
            cr_threshold = cr_threshold if cr_threshold is not None else self.default_cr_threshold
            model_dir = model_dir or self.model_dir

            # 检查输入文件
            if not os.path.exists(input_wav):
                logger.error(f"输入文件不存在: {input_wav}")
                return False
            logger.info(f"输入文件存在，大小: {os.path.getsize(input_wav)} 字节")

            # 检查服务健康状态
            logger.info("检查服务健康状态...")
            health = await self.check_health()
            if not health:
                logger.error("服务未就绪")
                return False

            if health.get("queue_size", 0) >= self.max_queue_size:
                logger.error("服务器任务队列已满")
                return False
            logger.info("服务健康状态检查通过")

            # 读取音频文件
            try:
                with open(input_wav, "rb") as f:
                    audio_data = f.read()
                logger.info(f"成功读取音频文件，大小: {len(audio_data)} 字节")

                # 检查读取后的数据大小
                is_safe, memory_warning = check_memory_safe(len(audio_data))
                if not is_safe:
                    logger.error(f"读取音频文件内存不足: {memory_warning}")
                    return False

            except Exception as e:
                logger.error(f"读取音频文件失败: {str(e)}\n{traceback.format_exc()}")
                return False

            # 准备表单数据
            data = aiohttp.FormData()
            data.add_field("audio",
                         audio_data,
                         filename="input.wav",
                         content_type="audio/wav")
            data.add_field("model_dir", model_dir)
            data.add_field("tran", str(pitch_adjust))
            data.add_field("spk", str(speaker_id))
            data.add_field("wav_format", "wav")
            data.add_field("k_step", str(k_step))
            data.add_field("shallow_diffusion", str(shallow_diffusion).lower())
            data.add_field("only_diffusion", str(only_diffusion).lower())
            data.add_field("cluster_infer_ratio", str(cluster_infer_ratio))
            data.add_field("auto_predict_f0", str(auto_predict_f0).lower())
            data.add_field("noice_scale", str(noice_scale))
            data.add_field("f0_filter", str(f0_filter).lower())
            data.add_field("f0_predictor", f0_predictor)
            data.add_field("enhancer_adaptive_key", str(enhancer_adaptive_key))
            data.add_field("cr_threshold", str(cr_threshold))

            # 发送请求
            logger.info(f"开始转换音频: {input_wav}")
            logger.info(f"输出文件: {output_wav}")
            logger.info(f"使用说话人ID: {speaker_id}")
            logger.info(f"音调调整: {pitch_adjust}")
            logger.info(f"API地址: {self.api_url}/wav2wav")
            logger.info(f"超时时间: {self.timeout}秒")

            start_time = time.time()
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.api_url}/wav2wav",
                        data=data,
                        timeout=self.timeout
                    ) as response:
                        logger.info(f"收到响应，状态码: {response.status}")
                        if response.status == 200:
                            try:
                                # 确保输出目录存在
                                os.makedirs(os.path.dirname(output_wav), exist_ok=True)
                                logger.info(f"输出目录已创建: {os.path.dirname(output_wav)}")

                                # 保存转换后的音频
                                audio_content = await response.read()
                                logger.info(f"收到音频数据，大小: {len(audio_content)} 字节")

                                if len(audio_content) == 0:
                                    logger.error("收到的音频数据为空")
                                    return False

                                with open(output_wav, "wb") as f:
                                    f.write(audio_content)
                                logger.info(f"音频文件已保存: {output_wav}")

                                # 验证输出文件
                                if not os.path.exists(output_wav):
                                    logger.error(f"输出文件不存在: {output_wav}")
                                    return False

                                output_size = os.path.getsize(output_wav)
                                if output_size == 0:
                                    logger.error("输出文件大小为0")
                                    return False

                                logger.info(f"输出文件大小: {output_size} 字节")

                                process_time = time.time() - start_time
                                logger.info(f"转换成功！输出文件已保存为: {output_wav}")
                                logger.info(f"处理耗时: {process_time:.2f}秒")
                                return True
                            except Exception as e:
                                logger.error(f"保存输出文件时出错: {str(e)}")
                                return False
                        else:
                            error_msg = await response.text()
                            logger.error(f"转换失败！状态码: {response.status}")
                            logger.error(f"错误信息: {error_msg}")
                            return False
            except asyncio.TimeoutError:
                logger.error("转换请求超时")
                return False
            except Exception as e:
                logger.error(f"发送转换请求时出错: {str(e)}")
                return False

        except Exception as e:
            logger.error(f"转换过程中发生错误: {str(e)}\n{traceback.format_exc()}")
            return False

def get_memory_info() -> Tuple[float, float, float]:
    """获取内存使用情况

    Returns:
        Tuple[float, float, float]: (总内存GB, 已用内存GB, 可用内存GB)
    """
    mem = psutil.virtual_memory()
    return (
        mem.total / (1024 * 1024 * 1024),  # 总内存(GB)
        mem.used / (1024 * 1024 * 1024),   # 已用内存(GB)
        mem.available / (1024 * 1024 * 1024)  # 可用内存(GB)
    )

def check_memory_safe(file_size: int) -> Tuple[bool, str]:
    """检查内存是否足够处理文件

    Args:
        file_size: 文件大小(字节)

    Returns:
        Tuple[bool, str]: (是否安全, 错误信息)
    """
    total, used, available = get_memory_info()
    estimated_memory = file_size * 2 / (1024 * 1024 * 1024)  # 预估所需内存(GB)

    if available < estimated_memory * 1.5:  # 预留1.5倍空间
        return False, (
            f"内存不足！\n"
            f"系统总内存: {total:.1f}GB\n"
            f"已用内存: {used:.1f}GB\n"
            f"可用内存: {available:.1f}GB\n"
            f"预估需要: {estimated_memory:.1f}GB\n"
            f"建议：\n"
            f"1. 等待其他任务完成\n"
            f"2. 缩短音频长度\n"
            f"3. 降低音频质量"
        )
    return True, ""

@register(
    name="so-vits-svc-api",
    author="Soulter",
    desc="So-Vits-SVC API 语音转换插件",
    version="1.3.3",
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
        self.converter = VoiceConverter(self.config)  # 立即初始化 converter
        self.conversion_tasks = {}  # 存储正在进行的转换任务
        self.msst_processor = None  # 延迟初始化 MSST 处理器
        self.temp_dir = "data/temp/so-vits-svc"
        os.makedirs(self.temp_dir, exist_ok=True)

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
                            "model_dir": {
                                "description": "默认模型目录",
                                "type": "string",
                                "hint": "默认使用的模型目录名称",
                                "default": "default",
                            },
                            "netease_cookie": {
                                "description": "网易云音乐Cookie",
                                "type": "string",
                                "hint": "用于访问网易云音乐API的Cookie",
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
                        },
                    },
                    "mixing_config": {
                        "description": "混音设置",
                        "type": "object",
                        "hint": "混音处理的相关参数设置",
                        "items": {
                            "sample_rate": {
                                "description": "采样率",
                                "type": "integer",
                                "hint": "音频处理的采样率",
                                "default": 44100,
                            },
                            "headroom": {
                                "description": "伴奏增益",
                                "type": "number",
                                "hint": "伴奏的音量增益，单位dB",
                                "default": -8,
                            },
                            "voc_input": {
                                "description": "人声输入增益",
                                "type": "number",
                                "hint": "人声的输入增益，单位dB",
                                "default": -4,
                            },
                            "revb_gain": {
                                "description": "混响增益",
                                "type": "number",
                                "hint": "混响效果的增益，单位dB",
                                "default": 0,
                            },
                        },
                    },
                    "cache_config": {
                        "description": "缓存设置",
                        "type": "object",
                        "hint": "缓存相关的配置参数",
                        "items": {
                            "cache_dir": {
                                "description": "缓存目录",
                                "type": "string",
                                "hint": "存储缓存文件的目录路径",
                                "default": "data/cache/so-vits-svc"
                            },
                            "max_cache_size": {
                                "description": "最大缓存大小(字节)",
                                "type": "integer",
                                "hint": "缓存的最大容量，默认1GB",
                                "default": 1073741824
                            },
                            "max_cache_age": {
                                "description": "最大缓存时间(秒)",
                                "type": "integer",
                                "hint": "缓存文件的最大保存时间，默认7天",
                                "default": 604800
                            }
                        }
                    }
                },
            }
        }

    async def _init_config(self) -> None:
        """初始化配置"""
        # 初始化 MSST 处理器
        self.msst_processor = MSSTProcessor(self.config.get("base_setting", {}).get("msst_url", "http://localhost:9000"))
        await self.msst_processor.initialize()

    @command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """测试插件是否正常工作"""
        yield event.plain_result("So-Vits-SVC 插件已加载！")

    @permission_type(PermissionType.ADMIN)
    @command("svc_status")
    async def check_status(self, event: AstrMessageEvent):
        """检查服务状态"""
        health = await self.converter.check_health()
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
    async def convert_voice(self, event: AstrMessageEvent, *args, **kwargs):
        """转换语音"""
        try:
            # 解析参数
            message = event.message_str.strip()
            args = message.split()[1:] if message else []
            speaker_id = None
            pitch_adjust = None
            song_name = None
            source_type = "file"  # 默认为文件上传
            model_dir = None  # 默认使用配置中的模型目录

            only_chorus = False
            if "-c" in args:
                only_chorus = True
                args.remove("-c")

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
                            # 检查是否指定了模型目录
                            model_index = -1
                            for i, arg in enumerate(args):
                                if arg == "-m" and i + 1 < len(args):
                                    model_index = i
                                    break

                            if model_index != -1:
                                # 如果找到了-m参数，提取模型目录和BV号
                                model_dir = args[model_index + 1]
                                song_name = " ".join(args[3:model_index])
                            else:
                                # 如果没有找到-m参数，整个剩余部分都是BV号
                                song_name = " ".join(args[3:])
                    elif args[2].lower() == "qq":
                        source_type = "qqmusic"
                        if len(args) > 3:
                            # 检查是否指定了模型目录
                            model_index = -1
                            for i, arg in enumerate(args):
                                if arg == "-m" and i + 1 < len(args):
                                    model_index = i
                                    break

                            if model_index != -1:
                                # 如果找到了-m参数，提取模型目录和歌曲名
                                model_dir = args[model_index + 1]
                                song_name = " ".join(args[3:model_index])
                            else:
                                # 如果没有找到-m参数，整个剩余部分都是歌曲名
                                song_name = " ".join(args[3:])
                    else:
                        # 检查是否指定了模型目录
                        model_index = -1
                        for i, arg in enumerate(args):
                            if arg == "-m" and i + 1 < len(args):
                                model_index = i
                                break

                        if model_index != -1:
                            # 如果找到了-m参数，提取模型目录和歌曲名
                            model_dir = args[model_index + 1]
                            song_name = " ".join(args[2:model_index])
                        else:
                            # 如果没有找到-m参数，整个剩余部分都是歌曲名
                            song_name = " ".join(args[2:])

            # 生成临时文件路径
            input_file = os.path.join(self.temp_dir, f"input_{uuid.uuid4()}.wav")
            output_file = os.path.join(self.temp_dir, f"output_{uuid.uuid4()}.wav")
            mixed_file = os.path.join(self.temp_dir, f"mixed_{uuid.uuid4()}.wav")
            vocal_file = os.path.join(self.temp_dir, f"vocal_{uuid.uuid4()}.wav")
            inst_file = os.path.join(self.temp_dir, f"inst_{uuid.uuid4()}.wav")

            # 生成任务ID
            task_id = str(uuid.uuid4())

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
                    import shutil
                    shutil.copy(downloaded_file, input_file)

                except Exception as e:
                    logger.error(f"处理哔哩哔哩视频时出错: {str(e)}")
                    yield event.plain_result(f"处理/下载视频时出错：{str(e)}")
                    return
            elif source_type == "qqmusic" and song_name:
                try:
                    yield event.plain_result(f"正在搜索QQ音乐：{song_name}...")

                    # 确保QQ音乐已登录
                    if not await self.converter.qqmusic_api.ensure_login():
                        yield event.plain_result("QQ音乐登录失败，请检查配置或重新登录")
                        return

                    song_info = await self.converter.qqmusic_api.get_song_with_highest_quality(song_name)

                    if not song_info:
                        yield event.plain_result(f"未找到QQ音乐歌曲：{song_name}")
                        return

                    if not song_info.get("url"):
                        yield event.plain_result("无法获取QQ音乐下载链接，可能是版权限制")
                        return

                    yield event.plain_result(
                        f"找到QQ音乐歌曲：{song_info.get('name', '未知歌曲')} - {song_info.get('ar_name', '未知歌手')}\n"
                        f"音质：{song_info.get('level', '未知音质')}\n"
                        f"正在下载..."
                    )

                    downloaded_file = await self.converter.qqmusic_api.download_song(song_info, self.temp_dir)
                    if not downloaded_file:
                        yield event.plain_result("下载QQ音乐歌曲失败！")
                        return

                    if os.path.exists(downloaded_file):
                        os.rename(downloaded_file, input_file)
                    else:
                        yield event.plain_result("下载的QQ音乐文件不存在！")
                        return

                except Exception as e:
                    logger.error(f"处理QQ音乐时出错: {str(e)}")
                    yield event.plain_result(f"搜索/下载QQ音乐歌曲时出错：{str(e)}")
                    return
            elif song_name:
                try:
                    # 如果指定了模型目录，验证其是否存在
                    if model_dir:
                        models = await self.converter.get_available_models()
                        if not models:
                            yield event.plain_result("获取模型列表失败！")
                            return

                        if model_dir not in models:
                            yield event.plain_result(f"模型目录 {model_dir} 不存在！")
                            return

                    yield event.plain_result(f"正在搜索歌曲：{song_name}...")
                    song_info = await self.converter.netease_api.get_song_with_highest_quality(
                        song_name
                    )

                    if not song_info:
                        yield event.plain_result(f"未找到歌曲：{song_name}")
                        return

                    if not song_info.get("url"):
                        yield event.plain_result(
                            "无法获取歌曲下载链接，可能是版权限制。"
                        )
                        return

                    result_msg = (
                        f"找到歌曲：{song_info.get('name', '未知歌曲')} - {song_info.get('ar_name', '未知歌手')}\n"
                        f"音质：{song_info.get('level', '未知音质')}\n"
                        f"大小：{song_info.get('size', '未知大小')}\n"
                    )
                    if model_dir:
                        result_msg += f"使用模型目录：{model_dir}\n"
                    result_msg += "正在下载..."
                    yield event.plain_result(result_msg)

                    downloaded_file = await self.converter.netease_api.download_song(
                        song_info, self.temp_dir
                    )
                    if not downloaded_file:
                        yield event.plain_result("下载歌曲失败！")
                        return

                    if os.path.exists(downloaded_file):
                        os.rename(downloaded_file, input_file)
                    else:
                        yield event.plain_result("下载的文件不存在！")
                        return

                except Exception as e:
                    logger.error(f"处理歌曲时出错: {str(e)}")
                    yield event.plain_result(f"搜索/下载歌曲时出错：{str(e)}")
                    return
            else:
                if (
                    not hasattr(event.message_obj, "files")
                    or not event.message_obj.files
                ):
                    yield event.plain_result(
                        "请上传要转换的音频文件或指定歌曲名！\n"
                        "用法：\n"
                        "1. /convert_voice [说话人ID] [音调调整] - 上传音频文件\n"
                        "2. /convert_voice [说话人ID] [音调调整] [歌曲名] - 搜索网易云音乐\n"
                        "3. /convert_voice [说话人ID] [音调调整] bilibili [BV号或链接] - 转换哔哩哔哩视频\n"
                        "4. /convert_voice [说话人ID] [音调调整] qq [歌曲名] -m [模型目录] - 搜索QQ音乐（可选指定模型目录）\n"
                        "5. /convert_voice [说话人ID] [音调调整] [歌曲名] -m [模型目录] - 使用指定模型目录转换（可选）"
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

            # 检查缓存
            cache_params = {
                "k_step": self.converter.default_k_step,
                "shallow_diffusion": self.converter.default_shallow_diffusion,
                "only_diffusion": self.converter.default_only_diffusion,
                "cluster_infer_ratio": self.converter.default_cluster_infer_ratio,
                "auto_predict_f0": self.converter.default_auto_predict_f0,
                "noice_scale": self.converter.default_noice_scale,
                "f0_filter": self.converter.default_f0_filter,
                "f0_predictor": self.converter.default_f0_predictor,
                "enhancer_adaptive_key": self.converter.default_enhancer_adaptive_key,
                "cr_threshold": self.converter.default_cr_threshold,
                "enable_mixing": self.converter.enable_mixing  # 添加混音标志
            }

            # 获取缓存
            cached_file = self.converter.cache_manager.get_cache(
                input_file,  # 使用原始输入文件
                speaker_id,
                pitch_adjust,
                **cache_params
            )

            if cached_file:
                logger.info(f"使用缓存: {cached_file}")
                chain = [Record.fromFileSystem(cached_file)]
                yield event.chain_result(chain)
                return

            # 音频文件准备好后，推理前裁切副歌
            if only_chorus:
                yield event.plain_result("正在检测副歌区间并裁切...")
                try:
                    with open(input_file, "rb") as f:
                        audio_bytes = f.read()
                    volc_conf = self.config.get("volc_chorus", {})
                    print("volc_conf:", volc_conf)  # 调试打印
                    chorus_result = await detect_chorus_api(audio_bytes, volc_conf)
                    if chorus_result.get("msg") == "success":
                        start = int(chorus_result["chorus"]["start"] * 1000)  # ms
                        end = int(chorus_result["chorus"]["end"] * 1000)
                        audio = AudioSegment.from_file(input_file)
                        chorus_audio = audio[start:end]
                        chorus_path = input_file.replace(".wav", "_chorus.wav")
                        chorus_audio.export(chorus_path, format="wav")
                        input_file = chorus_path  # 后续流程用副歌片段
                        yield event.plain_result(f"副歌区间：{start//1000}s - {end//1000}s，已裁切。")
                    else:
                        yield event.plain_result("副歌检测失败：" + str(chorus_result))
                        return
                except Exception as e:
                    yield event.plain_result(f"副歌检测或裁切出错：{str(e)}\n{traceback.format_exc()}")
                    return

            # 开始处理流程
            yield event.plain_result("正在使用MSST分离人声和伴奏...")

            # 使用MSST分离人声和伴奏
            msst_result = await self.converter.msst_processor.process_audio(
                input_file,
                self.converter.msst_preset
            )

            if not msst_result or msst_result.get("status") != "success":
                yield event.plain_result(f"MSST处理失败：{msst_result.get('message', '未知错误') if msst_result else '处理失败'}")
                return

            # 下载分离后的文件
            try:
                vocal_download = await self.converter.msst_processor.download_file(
                    "input_vocals_noreverb.wav",
                    vocal_file
                )
                inst_download = await self.converter.msst_processor.download_file(
                    "input_instrumental.wav",
                    inst_file
                )

                if not vocal_download or not inst_download:
                    yield event.plain_result("下载分离后的音频文件失败！")
                    return

                if not os.path.exists(vocal_file) or not os.path.exists(inst_file):
                    yield event.plain_result("未能成功获取分离后的音频文件！")
                    return

            except Exception as e:
                logger.error(f"下载分离文件时出错: {str(e)}")
                yield event.plain_result(f"下载分离文件时出错：{str(e)}")
                return

            # 检查文件
            if not os.path.exists(vocal_file):
                logger.error(f"人声文件不存在: {vocal_file}")
                yield event.plain_result("人声文件不存在")
                return

            if not os.path.exists(inst_file):
                logger.error(f"伴奏文件不存在: {inst_file}")
                yield event.plain_result("伴奏文件不存在")
                return

            # 检查文件大小
            vocal_size = os.path.getsize(vocal_file)
            inst_size = os.path.getsize(inst_file)
            logger.info(f"人声文件大小: {vocal_size} 字节")
            logger.info(f"伴奏文件大小: {inst_size} 字节")

            if vocal_size == 0 or inst_size == 0:
                logger.error("文件大小为0")
                yield event.plain_result("文件大小为0")
                return

            # 转换人声
            yield event.plain_result("正在转换人声...")
            try:
                # 创建异步任务
                convert_task = asyncio.create_task(
                    self.converter.convert_voice_async(
                        input_wav=vocal_file,  # 使用分离后的人声
                        output_wav=output_file,
                        speaker_id=speaker_id,
                        pitch_adjust=pitch_adjust,
                        k_step=self.converter.default_k_step,
                        shallow_diffusion=self.converter.default_shallow_diffusion,
                        only_diffusion=self.converter.default_only_diffusion,
                        cluster_infer_ratio=self.converter.default_cluster_infer_ratio,
                        auto_predict_f0=self.converter.default_auto_predict_f0,
                        noice_scale=self.converter.default_noice_scale,
                        f0_filter=self.converter.default_f0_filter,
                        f0_predictor=self.converter.default_f0_predictor,
                        enhancer_adaptive_key=self.converter.default_enhancer_adaptive_key,
                        cr_threshold=self.converter.default_cr_threshold,
                        model_dir=model_dir,
                    )
                )

                # 等待转换完成
                convert_success = await convert_task

                if not convert_success:
                    yield event.plain_result("人声转换失败！")
                    return

            except Exception as e:
                logger.error(f"人声转换时出错: {str(e)}")
                yield event.plain_result(f"人声转换时出错：{str(e)}")
                return

            # 混音处理
            if self.converter.enable_mixing:
                yield event.plain_result("正在混音处理...")
                try:
                    mix_success = self.converter.mix_audio(
                        vocal_path=output_file,  # 使用转换后的人声
                        inst_path=inst_file,     # 使用分离后的伴奏
                        output_path=mixed_file
                    )

                    if not mix_success:
                        yield event.plain_result("混音处理失败！")
                        return

                except Exception as e:
                    logger.error(f"混音处理时出错: {str(e)}")
                    yield event.plain_result(f"混音处理时出错：{str(e)}")
                    return

                # 保存混音后的文件到缓存
                self.converter.cache_manager.save_cache(
                    input_file,  # 使用原始输入文件
                    mixed_file,  # 缓存混音后的文件
                    speaker_id,
                    pitch_adjust,
                    **cache_params
                )

                # 在发送结果之前添加内存检查
                if self.converter.enable_mixing:
                    final_file = mixed_file
                else:
                    final_file = output_file

                # 检查文件大小和内存使用情况
                try:
                    file_size = os.path.getsize(final_file)
                    if file_size == 0:
                        yield event.plain_result("错误：生成的文件大小为0，请检查转换过程")
                        return

                    is_safe, memory_warning = check_memory_safe(file_size)
                    if not is_safe:
                        yield event.plain_result(memory_warning)
                        return

                    # 使用异步方式读取文件
                    try:
                        with open(final_file, "rb") as f:
                            audio_data = f.read()

                        # 再次检查内存
                        is_safe, memory_warning = check_memory_safe(len(audio_data))
                        if not is_safe:
                            yield event.plain_result(memory_warning)
                            return

                        # 发送结果
                        yield event.plain_result("处理完成！正在发送文件...")
                        chain = [Record.fromFileSystem(final_file)]
                        yield event.chain_result(chain)

                        # 立即清理内存
                        del audio_data
                        import gc
                        gc.collect()

                    except MemoryError as e:
                        logger.error(f"内存不足: {str(e)}")
                        yield event.plain_result("内存不足，无法处理文件。请尝试缩短音频长度或降低音质。")
                        return
                    except IOError as e:
                        logger.error(f"文件读写错误: {str(e)}")
                        yield event.plain_result(f"文件读写错误: {str(e)}")
                        return
                    except Exception as e:
                        logger.error(f"发送音频文件时出错: {str(e)}\n{traceback.format_exc()}")
                        yield event.plain_result(f"发送音频文件时出错: {str(e)}")
                        return

                except Exception as e:
                    logger.error(f"检查文件时出错: {str(e)}\n{traceback.format_exc()}")
                    yield event.plain_result(f"检查文件时出错: {str(e)}")
                    return

            else:
                # 如果不混音，保存转换后的人声到缓存
                self.converter.cache_manager.save_cache(
                    input_file,  # 使用原始输入文件
                    output_file,  # 缓存转换后的人声文件
                    speaker_id,
                    pitch_adjust,
                    **cache_params
                )

                # 在发送结果之前添加内存检查
                if self.converter.enable_mixing:
                    final_file = mixed_file
                else:
                    final_file = output_file

                # 检查文件大小和内存使用情况
                try:
                    file_size = os.path.getsize(final_file)
                    if file_size == 0:
                        yield event.plain_result("错误：生成的文件大小为0，请检查转换过程")
                        return

                    is_safe, memory_warning = check_memory_safe(file_size)
                    if not is_safe:
                        yield event.plain_result(memory_warning)
                        return

                    # 使用异步方式读取文件
                    try:
                        with open(final_file, "rb") as f:
                            audio_data = f.read()

                        # 再次检查内存
                        is_safe, memory_warning = check_memory_safe(len(audio_data))
                        if not is_safe:
                            yield event.plain_result(memory_warning)
                            return

                        # 发送结果
                        yield event.plain_result("处理完成！正在发送文件...")
                        chain = [Record.fromFileSystem(final_file)]
                        yield event.chain_result(chain)

                        # 立即清理内存
                        del audio_data
                        import gc
                        gc.collect()

                    except MemoryError as e:
                        logger.error(f"内存不足: {str(e)}")
                        yield event.plain_result("内存不足，无法处理文件。请尝试缩短音频长度或降低音质。")
                        return
                    except IOError as e:
                        logger.error(f"文件读写错误: {str(e)}")
                        yield event.plain_result(f"文件读写错误: {str(e)}")
                        return
                    except Exception as e:
                        logger.error(f"发送音频文件时出错: {str(e)}\n{traceback.format_exc()}")
                        yield event.plain_result(f"发送音频文件时出错: {str(e)}")
                        return

                except Exception as e:
                    logger.error(f"检查文件时出错: {str(e)}\n{traceback.format_exc()}")
                    yield event.plain_result(f"检查文件时出错: {str(e)}")
                    return

        except Exception as e:
            logger.error(f"处理过程中发生错误: {str(e)}\n{traceback.format_exc()}")
            yield event.plain_result(f"处理过程中发生错误：{str(e)}")
        finally:
            # 清理任务
            if task_id in self.conversion_tasks:
                del self.conversion_tasks[task_id]
            # 清理临时文件
            try:
                for file_path in [input_file, output_file, mixed_file, vocal_file, inst_file]:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        # 强制释放文件句柄
                        import gc
                        gc.collect()
            except (OSError, IOError) as e:
                logger.error(f"清理临时文件失败: {str(e)}\n{traceback.format_exc()}")

    @permission_type(PermissionType.ADMIN)
    @command("cancel_convert")
    async def cancel_convert(self, event: AstrMessageEvent):
        """取消正在进行的转换任务"""
        if not self.conversion_tasks:
            yield event.plain_result("当前没有正在进行的转换任务")
            return

        for task_id, task_info in list(self.conversion_tasks.items()):
            task = task_info["task"]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                # 清理临时文件
                try:
                    if os.path.exists(task_info["input_file"]):
                        os.remove(task_info["input_file"])
                    if os.path.exists(task_info["output_file"]):
                        os.remove(task_info["output_file"])
                    if os.path.exists(task_info["mixed_file"]):
                        os.remove(task_info["mixed_file"])
                except (OSError, IOError) as e:
                    logger.error(f"清理临时文件失败: {str(e)}\n{traceback.format_exc()}")
                del self.conversion_tasks[task_id]
                yield event.plain_result("已取消转换任务")
                return

        yield event.plain_result("没有找到可取消的转换任务")

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
            # 获取可用模型列表
            models = await self.converter.get_available_models()
            if not models:
                yield event.plain_result("获取模型列表失败！")
                return

            if len(args) > 0:
                speaker_id = args[0]
                if speaker_id not in models:
                    yield event.plain_result(f"说话人 {speaker_id} 不存在！")
                    return

                self.converter.default_speaker = speaker_id
                self.config["voice_config"]["default_speaker"] = speaker_id
                self.config.save_config()
                yield event.plain_result(f"已将默认说话人设置为: {speaker_id}")
                return

            speaker_info = "下面列出了可用的说话人列表:\n"
            for i, speaker in enumerate(models, 1):
                speaker_info += f"{i}. {speaker}\n"

            speaker_info += f"\n当前默认说话人: [{self.converter.default_speaker}]\n"
            speaker_info += "Tips: 使用 /svc_speakers <说话人ID>，即可设置默认说话人"

            yield event.plain_result(speaker_info)

        except Exception as e:
            yield event.plain_result(f"获取说话人列表失败：{str(e)}\n{traceback.format_exc()}")

    @permission_type(PermissionType.ADMIN)
    @command("svc_presets", alias=["预设列表"])
    async def show_presets(self, event: AstrMessageEvent):
        """展示当前可用的预设列表"""
        try:
            presets = await self.converter.msst_processor.get_presets()
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
            yield event.plain_result(f"获取预设列表失败：{str(e)}\n{traceback.format_exc()}")

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

            result = "视频信息：\n"
            result += f"标题：{video_info['title']}\n"
            result += f"UP主：{video_info['uploader']}\n"
            result += f"分P数量：{len(video_info['parts'])}\n\n"

            if video_info["parts"]:
                result += "分P列表：\n"
                for part in video_info["parts"]:
                    result += f"{part['index']}. {part['title']} ({part['duration']})\n"

            result += "\n使用方法：\n"
            result += f"/convert_voice [说话人ID] [音调调整] bilibili {url_or_bvid}"

            yield event.plain_result(result)

        except Exception as e:
            logger.error(f"获取哔哩哔哩视频信息出错: {str(e)}\n{traceback.format_exc()}")
            yield event.plain_result(f"获取视频信息时出错：{str(e)}")

    @permission_type(PermissionType.ADMIN)
    @command("clear_cache")
    async def clear_cache(self, event: AstrMessageEvent):
        """清空转换缓存"""
        try:
            self.converter.cache_manager.clear_cache()
            yield event.plain_result("缓存已清空")
        except Exception as e:
            yield event.plain_result(f"清空缓存失败：{str(e)}\n{traceback.format_exc()}")

    @command("qqmusic_info")
    async def get_qqmusic_info(self, event: AstrMessageEvent):
        """获取QQ音乐歌曲信息

        用法：/qqmusic_info [歌曲名]
        """
        message = event.message_str.strip()
        args = message.split()[1:] if message else []

        if not args:
            yield event.plain_result("请提供歌曲名！\n用法：/qqmusic_info [歌曲名]")
            return

        song_name = " ".join(args)

        try:
            yield event.plain_result(f"正在搜索QQ音乐歌曲：{song_name}...")

            # 确保QQ音乐已登录
            if not await self.converter.qqmusic_api.ensure_login():
                yield event.plain_result("QQ音乐登录失败，请检查配置或重新登录")
                return

            # 搜索歌曲
            search_results = await self.converter.qqmusic_api.search(song_name, limit=5)

            if not search_results:
                yield event.plain_result(f"未找到QQ音乐歌曲：{song_name}")
                return

            result = f"找到 {len(search_results)} 首相关歌曲：\n\n"

            for i, song in enumerate(search_results, 1):
                song_name = song.get("name", "未知歌曲")
                singer_name = song.get("singer", [{}])[0].get("name", "未知歌手")
                album_name = song.get("album", {}).get("name", "未知专辑")
                duration = song.get("interval", "未知时长")

                result += f"{i}. {song_name} - {singer_name}\n"
                result += f"   专辑：{album_name}\n"
                result += f"   时长：{duration}秒\n\n"

            result += "使用方法：\n"
            result += f"/convert_voice [说话人ID] [音调调整] qq {song_name}"

            yield event.plain_result(result)

        except Exception as e:
            logger.error(f"获取QQ音乐歌曲信息出错: {str(e)}\n{traceback.format_exc()}")
            yield event.plain_result(f"获取QQ音乐歌曲信息时出错：{str(e)}")

    @permission_type(PermissionType.ADMIN)
    @command("svc_models", alias=["模型列表"])
    async def show_models(self, event: AstrMessageEvent):
        """展示当前可用的模型列表，支持切换默认模型目录

        用法：/svc_models [模型目录名]
        示例：/svc_models - 显示模型列表
              /svc_models default - 设置默认模型目录为default
        """
        message = event.message_str.strip()
        args = message.split()[1:] if message else []

        try:
            # 获取可用模型列表
            models = await self.converter.get_available_models()
            if not models:
                yield event.plain_result("获取模型列表失败！")
                return

            if len(args) > 0:
                model_dir = args[0]
                if model_dir not in models:
                    yield event.plain_result(f"模型目录 {model_dir} 不存在！")
                    return

                self.converter.model_dir = model_dir
                self.config["base_setting"]["model_dir"] = model_dir
                self.config.save_config()
                yield event.plain_result(f"已将默认模型目录设置为: {model_dir}")
                return

            model_info = "下面列出了可用的模型目录:\n"
            for i, model in enumerate(models, 1):
                model_info += f"{i}. {model}\n"

            model_info += f"\n当前默认模型目录: [{self.converter.model_dir}]\n"
            model_info += "Tips: 使用 /svc_models <模型目录名>，即可设置默认模型目录"

            yield event.plain_result(model_info)

        except Exception as e:
            yield event.plain_result(f"获取模型列表失败：{str(e)}\n{traceback.format_exc()}")
