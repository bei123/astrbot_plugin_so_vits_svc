#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
So-Vits-SVC API 插件
提供语音转换、MSST音频处理和网易云音乐下载功能
"""

from typing import Optional, Dict, List
import os
import time
import uuid
import requests
import json
import aiohttp
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star import Star, Context
from astrbot.api.event.filter import permission_type
from astrbot.api.star import register
from astrbot.core.config import AstrBotConfig
from astrbot.core import logger
from astrbot.core.message.components import Record
from astrbot.core.star.filter.permission import PermissionType
from .netease_api import NeteaseMusicAPI
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

        # 初始化组件
        self.session = requests.Session()
        self.msst_processor = MSSTProcessor(self.msst_url)
        self.netease_api = NeteaseMusicAPI(self.config)

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

    async def convert_voice_async(
        self,
        input_wav: str,
        output_wav: str,
        speaker_id: Optional[str] = None,
        pitch_adjust: Optional[int] = None,
    ) -> bool:
        """异步转换语音"""
        async with self.task_lock:  # 使用锁确保同一时间只有一个任务在执行
            if self.current_task is not None:
                raise RuntimeError("当前已有任务正在处理，请等待完成后再试")

            try:
                self.current_task = asyncio.current_task()
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    self.executor,
                    self.convert_voice,
                    input_wav,
                    output_wav,
                    speaker_id,
                    pitch_adjust,
                )
            finally:
                self.current_task = None

    def convert_voice(
        self,
        input_wav: str,
        output_wav: str,
        speaker_id: Optional[str] = None,
        pitch_adjust: Optional[int] = None,
    ) -> bool:
        """转换语音

        Args:
            input_wav: 输入音频文件路径
            output_wav: 输出音频文件路径
            speaker_id: 说话人ID，默认使用配置值
            pitch_adjust: 音调调整，默认使用配置值

        Returns:
            转换是否成功
        """
        # 使用默认值
        if speaker_id is None:
            speaker_id = self.default_speaker
        if pitch_adjust is None:
            pitch_adjust = self.default_pitch

        # 检查服务健康状态
        health = self.check_health()
        if not health:
            raise RuntimeError("服务未就绪")

        if not health.get("model_loaded"):
            raise RuntimeError("模型未加载")

        if health.get("queue_size", 0) >= self.max_queue_size:
            raise RuntimeError("服务器任务队列已满，请稍后重试")

        # 检查输入文件
        if not os.path.exists(input_wav):
            raise FileNotFoundError(f"输入文件不存在: {input_wav}")

        # 先进行 MSST 处理
        processed_file = self.msst_processor.process_audio(input_wav, self.msst_preset)
        if not processed_file:
            raise RuntimeError("MSST 处理失败")

        try:
            # 读取处理后的音频文件
            with open(processed_file, "rb") as f:
                audio_data = f.read()

            # 准备请求数据
            files = {"audio": ("input.wav", audio_data, "audio/wav")}
            data = {
                "tran": str(pitch_adjust),
                "spk": str(speaker_id),
                "wav_format": "wav",
            }

            # 发送请求
            logger.info(f"开始转换音频: {processed_file}")
            logger.info(f"使用说话人ID: {speaker_id}")
            logger.info(f"音调调整: {pitch_adjust}")

            start_time = time.time()
            response = self.session.post(
                f"{self.api_url}/wav2wav", data=data, files=files, timeout=self.timeout
            )

            # 处理响应
            if response.status_code == 200:
                with open(output_wav, "wb") as f:
                    f.write(response.content)

                process_time = time.time() - start_time
                logger.info(f"转换成功！输出文件已保存为: {output_wav}")
                logger.info(f"处理耗时: {process_time:.2f}秒")
                return True
            else:
                try:
                    error_msg = response.json().get("error", "未知错误")
                except (json.JSONDecodeError, AttributeError):
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"转换失败！状态码: {response.status_code}")
                logger.error(f"错误信息: {error_msg}")
                return False

        except requests.Timeout:
            logger.error("请求超时")
            return False
        except Exception as e:
            logger.error(f"发生错误: {str(e)}")
            return False
        finally:
            # 清理处理后的文件
            if processed_file and os.path.exists(processed_file):
                os.remove(processed_file)


@register(
    name="so-vits-svc-api",
    author="Soulter",
    desc="So-Vits-SVC API 语音转换插件",
    version="1.0.0",
)
class SoVitsSvcPlugin(Star):
    """So-Vits-SVC API 插件主类"""

    # 定义命令字符串为类属性
    CONVERT_VOICE_CMD = "convert_voice"
    SVC_STATUS_CMD = "svc_status"
    SVC_PRESETS_CMD = "svc_presets"
    SVC_SPEAKERS_CMD = "svc_speakers"
    CANCEL_CONVERT_CMD = "cancel_convert"

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
                },
            }
        }

    def _init_config(self) -> None:
        """初始化配置"""
        self.converter = VoiceConverter(self.config)
        self.temp_dir = "data/temp/so-vits-svc"
        os.makedirs(self.temp_dir, exist_ok=True)

        # 从配置中获取命令字符串并更新类属性
        command_config = self.config.get("command_config", {})
        SoVitsSvcPlugin.CONVERT_VOICE_CMD = command_config.get("convert_voice", SoVitsSvcPlugin.CONVERT_VOICE_CMD)
        SoVitsSvcPlugin.SVC_STATUS_CMD = command_config.get("svc_status", SoVitsSvcPlugin.SVC_STATUS_CMD)
        SoVitsSvcPlugin.SVC_PRESETS_CMD = command_config.get("svc_presets", SoVitsSvcPlugin.SVC_PRESETS_CMD)
        SoVitsSvcPlugin.SVC_SPEAKERS_CMD = command_config.get("svc_speakers", SoVitsSvcPlugin.SVC_SPEAKERS_CMD)
        SoVitsSvcPlugin.CANCEL_CONVERT_CMD = command_config.get("cancel_convert", SoVitsSvcPlugin.CANCEL_CONVERT_CMD)

    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """测试插件是否正常工作"""
        yield event.plain_result("So-Vits-SVC 插件已加载！")

    @permission_type(PermissionType.ADMIN)
    @filter.command(SVC_STATUS_CMD, alias={"状态", "status"})
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

    @filter.command(CONVERT_VOICE_CMD, alias={"转换", "convert"})
    async def convert_voice(self, event: AstrMessageEvent):
        """转换语音

        用法：
            1. /convert_voice [说话人ID] [音调调整] - 上传音频文件进行转换
            2. /convert_voice [说话人ID] [音调调整] [歌曲名] - 搜索并转换网易云音乐
        """
        # 解析参数
        message = event.message_str.strip()
        args = []
        speaker_id = None
        pitch_adjust = None
        song_name = None

        # 检查是否是自定义命令
        if message.startswith(self.CONVERT_VOICE_CMD):
            args = message[len(self.CONVERT_VOICE_CMD):].strip().split()
        elif message.startswith("转换"):
            args = message[2:].strip().split()
        elif message.startswith("convert"):
            args = message[7:].strip().split()
        else:
            # 尝试直接解析整个消息
            args = message.split()

        # 如果参数数量不足，尝试使用默认值
        if len(args) < 2:
            speaker_id = self.converter.default_speaker
            pitch_adjust = self.converter.default_pitch
            if len(args) == 1:
                song_name = args[0]
        else:
            speaker_id = args[0]
            try:
                pitch_adjust = int(args[1])
                if not -12 <= pitch_adjust <= 12:
                    raise ValueError("音调调整必须在-12到12之间")
            except ValueError as e:
                yield event.plain_result(f"参数错误：{str(e)}")
                return

            if len(args) > 2:
                song_name = " ".join(args[2:])

        # 生成临时文件路径
        input_file = os.path.join(self.temp_dir, f"input_{uuid.uuid4()}.wav")
        output_file = os.path.join(self.temp_dir, f"output_{uuid.uuid4()}.wav")

        # 生成任务ID
        task_id = str(uuid.uuid4())

        try:
            # 如果指定了歌曲名，从网易云下载
            if song_name:
                try:
                    yield event.plain_result(f"正在搜索歌曲：{song_name}...")
                    song_info = (
                        self.converter.netease_api.get_song_with_highest_quality(
                            song_name
                        )
                    )

                    if not song_info:
                        yield event.plain_result(f"未找到歌曲：{song_name}")
                        return

                    if not song_info.get("url"):
                        yield event.plain_result(
                            "无法获取歌曲下载链接，可能是版权限制。"
                        )
                        return

                    yield event.plain_result(
                        f"找到歌曲：{song_info.get('name', '未知歌曲')} - {song_info.get('ar_name', '未知歌手')}\n"
                        f"音质：{song_info.get('level', '未知音质')}\n"
                        f"大小：{song_info.get('size', '未知大小')}\n"
                        f"正在下载..."
                    )

                    downloaded_file = self.converter.netease_api.download_song(
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
                    logger.error(f"处理网易云音乐时出错: {str(e)}")
                    yield event.plain_result(f"搜索/下载歌曲时出错：{str(e)}")
                    return

            # 否则检查是否有上传的音频文件
            else:
                if (
                    not hasattr(event.message_obj, "files")
                    or not event.message_obj.files
                ):
                    yield event.plain_result(
                        "请上传要转换的音频文件或指定歌曲名！\n"
                        "用法：\n"
                        "1. /convert_voice [说话人ID] [音调调整] - 上传音频文件\n"
                        "2. /convert_voice [说话人ID] [音调调整] [歌曲名] - 搜索网易云音乐"
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

            # 转换音频
            yield event.plain_result("正在转换音频，请稍候...")

            # 创建异步任务
            task = asyncio.create_task(
                self.converter.convert_voice_async(
                    input_wav=input_file,
                    output_wav=output_file,
                    speaker_id=speaker_id,
                    pitch_adjust=pitch_adjust,
                )
            )

            # 存储任务
            self.conversion_tasks[task_id] = {
                "task": task,
                "input_file": input_file,
                "output_file": output_file,
                "event": event
            }

            # 等待任务完成
            success = await task

            if success:
                yield event.plain_result("转换成功！正在发送文件...")
                chain = [Record.fromFileSystem(output_file)]
                yield event.chain_result(chain)
            else:
                yield event.plain_result("转换失败！请检查服务状态或参数是否正确。")

        except Exception as e:
            yield event.plain_result(f"转换过程中发生错误：{str(e)}")
        finally:
            # 清理任务
            if task_id in self.conversion_tasks:
                del self.conversion_tasks[task_id]
            # 清理临时文件
            try:
                if os.path.exists(input_file):
                    os.remove(input_file)
                if os.path.exists(output_file):
                    os.remove(output_file)
            except (OSError, IOError) as e:
                logger.error(f"清理临时文件失败: {str(e)}")

    @permission_type(PermissionType.ADMIN)
    @filter.command(CANCEL_CONVERT_CMD, alias={"取消", "cancel"})
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
                except (OSError, IOError) as e:
                    logger.error(f"清理临时文件失败: {str(e)}")
                del self.conversion_tasks[task_id]
                yield event.plain_result("已取消转换任务")
                return

        yield event.plain_result("没有找到可取消的转换任务")

    @permission_type(PermissionType.ADMIN)
    @filter.command(SVC_SPEAKERS_CMD, alias={"说话人", "speakers"})
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
    @filter.command(SVC_PRESETS_CMD, alias={"预设", "presets"})
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
