from typing import Optional, Dict
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star import Star, Context
from astrbot.api.event.filter import command
from astrbot.api.star import register
from astrbot.core.config import AstrBotConfig
from astrbot.core import logger
import os
import time
import requests
import uuid
import json

class VoiceConverter:
    def __init__(self, config: Dict):
        """初始化语音转换器
        
        Args:
            config: 插件配置字典
        """
        self.base_setting = config.get('base_setting', {})
        self.voice_config = config.get('voice_config', {})
        
        # 基础设置
        self.api_url = self.base_setting.get('base_url', 'http://localhost:1145')
        self.timeout = self.base_setting.get('timeout', 300)
        
        # 语音转换设置
        self.max_queue_size = self.voice_config.get('max_queue_size', 100)
        self.default_speaker = self.voice_config.get('default_speaker', '0')
        self.default_pitch = self.voice_config.get('default_pitch', 0)
        
        self.session = requests.Session()
            
    def check_health(self):
        """检查服务健康状态"""
        try:
            response = self.session.get(f"{self.api_url}/health")
            return response.json()
        except Exception as e:
            logger.error(f"健康检查失败: {str(e)}")
            return None
            
    def convert_voice(self, input_wav, output_wav, speaker_id=None, pitch_adjust=None):
        """
        转换语音
        
        参数:
            input_wav: 输入音频文件路径
            output_wav: 输出音频文件路径
            speaker_id: 说话人ID，如果为None则使用默认值
            pitch_adjust: 音调调整，如果为None则使用默认值
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
            
        # 准备请求数据
        data = {
            "audio_path": os.path.abspath(input_wav),
            "tran": str(pitch_adjust),
            "spk": str(speaker_id),
            "wav_format": "wav"
        }
        
        try:
            # 发送请求
            logger.info(f"开始转换音频: {input_wav}")
            logger.info(f"使用说话人ID: {speaker_id}")
            logger.info(f"音调调整: {pitch_adjust}")
            
            start_time = time.time()
            response = self.session.post(f"{self.api_url}/wav2wav", data=data, timeout=self.timeout)
            
            # 检查响应
            if response.status_code == 200:
                # 保存输出文件
                with open(output_wav, "wb") as f:
                    f.write(response.content)
                    
                process_time = time.time() - start_time
                logger.info(f"转换成功！输出文件已保存为: {output_wav}")
                logger.info(f"处理耗时: {process_time:.2f}秒")
                return True
            else:
                error_msg = response.json().get("error", "未知错误")
                logger.error(f"转换失败！状态码: {response.status_code}")
                logger.error(f"错误信息: {error_msg}")
                return False
                
        except requests.Timeout:
            logger.error("请求超时")
            return False
        except Exception as e:
            logger.error(f"发生错误: {str(e)}")
            return False

@register(
    name="so-vits-svc-api",
    author="Soulter",
    desc="So-Vits-SVC API 语音转换插件",
    version="1.0.0"
)
class SoVitsSvcPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        """初始化插件
        
        Args:
            context: 插件上下文
            config: 插件配置
        """
        super().__init__(context)
        self.config = config
        self._init_config()

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
                                "default": "http://localhost:1145"
                            },
                            "timeout": {
                                "description": "请求超时时间(秒)",
                                "type": "integer",
                                "hint": "转换请求的超时时间",
                                "default": 300
                            }
                        }
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
                                "default": 100
                            },
                            "default_speaker": {
                                "description": "默认说话人ID",
                                "type": "string",
                                "hint": "默认使用的说话人ID",
                                "default": "0"
                            },
                            "default_pitch": {
                                "description": "默认音调调整",
                                "type": "integer",
                                "hint": "默认的音调调整值，范围-12到12",
                                "default": 0
                            }
                        }
                    }
                }
            }
        }
        
    def _init_config(self) -> None:
        """初始化配置"""
        # 创建转换器实例
        self.converter = VoiceConverter(self.config)
        self.temp_dir = "data/temp/so-vits-svc"
        os.makedirs(self.temp_dir, exist_ok=True)

    @command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """测试插件是否正常工作"""
        await event.reply("So-Vits-SVC 插件已加载！")

    @command("svc_status")
    async def check_status(self, event: AstrMessageEvent):
        """检查服务状态"""
        health = self.converter.check_health()
        if not health:
            await event.platform.send_message(
                event.message_obj.group_id if event.message_obj.group_id else event.message_obj.sender.id,
                "服务未就绪，请检查 So-Vits-SVC API 服务是否已启动。"
            )
            return
            
        status = "✅ 服务正常运行\n"
        status += f"模型加载状态: {'已加载' if health.get('model_loaded') else '未加载'}\n"
        status += f"当前队列大小: {health.get('queue_size', 0)}\n"
        status += f"API 版本: {health.get('version', '未知')}\n"
        status += f"API 地址: {self.converter.api_url}\n"
        status += f"默认说话人ID: {self.converter.default_speaker}\n"
        status += f"默认音调调整: {self.converter.default_pitch}"
        
        await event.platform.send_message(
            event.message_obj.group_id if event.message_obj.group_id else event.message_obj.sender.id,
            status
        )

    @command("convert_voice")
    async def convert_voice(self, event: AstrMessageEvent):
        """
        转换语音
        用法：/convert_voice [说话人ID] [音调调整(-12到12)]
        示例：/convert_voice 0 0
        """
        # 解析参数
        args = event.get_args()
        speaker_id = None
        pitch_adjust = None
        
        if len(args) >= 2:
            speaker_id = args[0]
            try:
                pitch_adjust = int(args[1])
                if not -12 <= pitch_adjust <= 12:
                    raise ValueError("音调调整必须在-12到12之间")
            except ValueError as e:
                await event.platform.send_message(
                    event.message_obj.group_id if event.message_obj.group_id else event.message_obj.sender.id,
                    f"参数错误：{str(e)}"
                )
                return

        # 检查是否有音频文件
        if not event.message.attachments:
            await event.platform.send_message(
                event.message_obj.group_id if event.message_obj.group_id else event.message_obj.sender.id,
                "请上传要转换的音频文件！"
            )
            return

        attachment = event.message.attachments[0]
        if not attachment.filename.lower().endswith(('.wav', '.mp3')):
            await event.platform.send_message(
                event.message_obj.group_id if event.message_obj.group_id else event.message_obj.sender.id,
                "只支持 WAV 或 MP3 格式的音频文件！"
            )
            return

        # 下载音频文件
        input_file = os.path.join(self.temp_dir, f"input_{event.message.id}.wav")
        output_file = os.path.join(self.temp_dir, f"output_{event.message.id}.wav")

        try:
            # 下载文件
            await event.platform.send_message(
                event.message_obj.group_id if event.message_obj.group_id else event.message_obj.sender.id,
                "正在下载音频文件..."
            )
            await attachment.download(input_file)
            
            # 转换音频
            await event.platform.send_message(
                event.message_obj.group_id if event.message_obj.group_id else event.message_obj.sender.id,
                "正在转换音频，请稍候..."
            )
            success = self.converter.convert_voice(
                input_wav=input_file,
                output_wav=output_file,
                speaker_id=speaker_id,
                pitch_adjust=pitch_adjust
            )

            if success:
                # 发送转换后的文件
                await event.platform.send_message(
                    event.message_obj.group_id if event.message_obj.group_id else event.message_obj.sender.id,
                    "转换成功！正在发送文件..."
                )
                await event.platform.send_file(
                    event.message_obj.group_id if event.message_obj.group_id else event.message_obj.sender.id,
                    output_file
                )
            else:
                await event.platform.send_message(
                    event.message_obj.group_id if event.message_obj.group_id else event.message_obj.sender.id,
                    "转换失败！请检查服务状态或参数是否正确。"
                )

        except Exception as e:
            await event.platform.send_message(
                event.message_obj.group_id if event.message_obj.group_id else event.message_obj.sender.id,
                f"转换过程中发生错误：{str(e)}"
            )

        finally:
            # 清理临时文件
            try:
                if os.path.exists(input_file):
                    os.remove(input_file)
                if os.path.exists(output_file):
                    os.remove(output_file)
            except:
                pass
