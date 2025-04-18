#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
哔哩哔哩API模块
提供解析和下载哔哩哔哩视频音频的功能
"""

import os
import json
import requests
import subprocess
import tempfile
import re
from typing import Dict, Optional, List, Tuple
from astrbot.core import logger


class BilibiliAPI:
    """哔哩哔哩API类"""

    def __init__(self, config: Dict = None):
        """初始化API

        Args:
            config: 插件配置字典
        """
        self.config = config or {}
        self.base_setting = self.config.get("base_setting", {})
        self.bbdown_path = self.base_setting.get("bbdown_path", "BBDown")
        self.bbdown_cookie = self.base_setting.get("bbdown_cookie", "")
        self.temp_dir = os.path.join("data", "temp", "bilibili")
        os.makedirs(self.temp_dir, exist_ok=True)

    def _run_bbdown(self, command: List[str]) -> Tuple[int, str, str]:
        """运行BBDown命令

        Args:
            command: 命令参数列表

        Returns:
            返回码、标准输出和标准错误
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(self.bbdown_path):
                error_msg = f"BBDown可执行文件不存在: {self.bbdown_path}"
                logger.error(error_msg)
                return -1, "", error_msg
                
            # 检查文件是否有执行权限
            if not os.access(self.bbdown_path, os.X_OK):
                error_msg = f"BBDown可执行文件没有执行权限: {self.bbdown_path}"
                logger.error(error_msg)
                return -1, "", error_msg
            
            # 构建完整命令
            # BBDown的正确命令格式是: BBDown <url> [command] [options]
            # 我们需要确保URL是第一个参数
            full_command = [self.bbdown_path]
            
            # 如果有cookie，添加cookie参数
            if self.bbdown_cookie:
                full_command.extend(["-c", self.bbdown_cookie])
            
            # 添加其他参数
            full_command.extend(command)
            
            logger.info(f"执行BBDown命令: {' '.join(full_command)}")
            
            # 执行命令
            process = subprocess.Popen(
                full_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate()
            return process.returncode, stdout, stderr
            
        except Exception as e:
            logger.error(f"执行BBDown命令出错: {str(e)}")
            return -1, "", str(e)

    def extract_bvid(self, url_or_bvid: str) -> Optional[str]:
        """从URL或BV号中提取BV号

        Args:
            url_or_bvid: 哔哩哔哩视频URL或BV号

        Returns:
            提取的BV号，如果无法提取则返回None
        """
        # 如果已经是BV号格式
        if re.match(r'^BV[a-zA-Z0-9]+$', url_or_bvid):
            return url_or_bvid
            
        # 尝试从URL中提取BV号
        bvid_pattern = r'BV[a-zA-Z0-9]+'
        match = re.search(bvid_pattern, url_or_bvid)
        if match:
            return match.group(0)
            
        # 尝试从URL中提取av号
        av_pattern = r'av(\d+)'
        match = re.search(av_pattern, url_or_bvid)
        if match:
            av_id = match.group(1)
            # 使用BBDown将av号转换为BV号
            returncode, stdout, stderr = self._run_bbdown(["--info", f"av{av_id}"])
            if returncode == 0:
                bvid_match = re.search(bvid_pattern, stdout)
                if bvid_match:
                    return bvid_match.group(0)
                    
        return None

    def get_video_info(self, url_or_bvid: str) -> Optional[Dict]:
        """获取视频信息

        Args:
            url_or_bvid: 视频URL或BV号

        Returns:
            视频信息，包括标题、UP主、分P信息等
        """
        try:
            # 提取BV号
            bvid = self.extract_bvid(url_or_bvid)
            if not bvid:
                logger.error(f"无法从 {url_or_bvid} 中提取BV号")
                return None
                
            # 构建URL
            if not url_or_bvid.startswith("http"):
                url = f"https://www.bilibili.com/video/{bvid}"
            else:
                url = url_or_bvid
                
            # 使用BBDown的info功能
            # 根据BBDown文档，正确的命令格式是: BBDown <url> --info
            # 注意：URL必须放在第一个参数位置，--info放在URL后面
            returncode, stdout, stderr = self._run_bbdown([url, "--info"])
            
            if returncode != 0:
                logger.error(f"获取视频信息失败: {stderr}")
                return None
            
            # 解析视频信息
            info = {
                "bvid": bvid,
                "title": "",
                "uploader": "",
                "parts": []
            }
            
            lines = stdout.strip().split('\n')
            for line in lines:
                if "标题:" in line:
                    info["title"] = line.split("标题:", 1)[1].strip()
                elif "UP主:" in line:
                    info["uploader"] = line.split("UP主:", 1)[1].strip()
                elif re.match(r'^\d+\.', line):
                    # 解析分P信息
                    part_match = re.match(r'^(\d+)\.\s+(.+?)\s+\((\d+:\d+)\)$', line)
                    if part_match:
                        part_index, part_title, duration = part_match.groups()
                        info["parts"].append({
                            "index": int(part_index),
                            "title": part_title,
                            "duration": duration
                        })
            
            return info
            
        except Exception as e:
            logger.error(f"获取视频信息出错: {str(e)}")
            return None

    def download_audio(self, url_or_bvid: str, part_index: Optional[int] = None, output_dir: Optional[str] = None) -> Optional[str]:
        """下载视频音频

        Args:
            url_or_bvid: 视频URL或BV号
            part_index: 分P序号，不指定则下载所有分P
            output_dir: 输出目录，不指定则使用临时目录

        Returns:
            下载的音频文件路径，失败返回None
        """
        try:
            # 提取BV号
            bvid = self.extract_bvid(url_or_bvid)
            if not bvid:
                logger.error(f"无法从 {url_or_bvid} 中提取BV号")
                return None
                
            # 构建URL
            if not url_or_bvid.startswith("http"):
                url = f"https://www.bilibili.com/video/{bvid}"
            else:
                url = url_or_bvid
                
            # 设置输出目录
            if not output_dir:
                output_dir = self.temp_dir
            
            # 构建命令
            # 根据BBDown文档，正确的命令格式是: BBDown <url> --audio-only [options]
            # 注意：URL必须放在第一个参数位置
            command = [url, "--audio-only"]
            
            # 添加工作目录参数
            command.extend(["--work-dir", output_dir])
            
            # 如果指定了分P，添加分P参数
            if part_index is not None:
                command.extend(["-p", str(part_index)])
            
            # 执行下载
            returncode, stdout, stderr = self._run_bbdown(command)
            
            if returncode != 0:
                logger.error(f"下载音频失败: {stderr}")
                return None
            
            # 查找下载的文件
            # BBDown通常会将文件保存在指定目录下，文件名格式为: 标题_音频.m4a
            files = os.listdir(output_dir)
            audio_files = [f for f in files if f.endswith('.m4a')]
            
            if not audio_files:
                logger.error("未找到下载的音频文件")
                return None
            
            # 返回最新下载的文件路径
            latest_file = max([os.path.join(output_dir, f) for f in audio_files], key=os.path.getctime)
            return latest_file
            
        except Exception as e:
            logger.error(f"下载音频出错: {str(e)}")
            return None

    def process_video(self, url_or_bvid: str) -> Optional[Dict]:
        """处理视频，获取信息并下载音频

        Args:
            url_or_bvid: 视频URL或BV号

        Returns:
            视频信息，包括下载的音频文件路径
        """
        # 1. 获取视频信息
        video_info = self.get_video_info(url_or_bvid)
        
        if not video_info:
            logger.error(f"获取视频信息失败: {url_or_bvid}")
            return None
        
        # 2. 下载音频
        audio_file = self.download_audio(url_or_bvid)
        
        if not audio_file:
            logger.error(f"下载音频失败: {url_or_bvid}")
            return None
        
        # 3. 返回结果
        return {
            "status": 200,
            "bvid": video_info["bvid"],
            "title": video_info["title"],
            "uploader": video_info["uploader"],
            "audio_file": audio_file,
            "parts": video_info["parts"]
        }

    def download_song(self, video_info: Dict, save_path: Optional[str] = None) -> Optional[str]:
        """下载视频音频

        Args:
            video_info: 视频信息，包含bvid字段
            save_path: 保存路径，默认为临时目录

        Returns:
            下载的文件路径
        """
        if not video_info or not video_info.get("bvid"):
            logger.error("无效的视频信息")
            return None
        
        bvid = video_info["bvid"]
        
        if save_path:
            if not os.path.exists(save_path):
                os.makedirs(save_path)
            output_dir = save_path
        else:
            output_dir = self.temp_dir
        
        return self.download_audio(bvid, output_dir=output_dir)


# 使用示例
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="哔哩哔哩API工具")
    parser.add_argument("url_or_bvid", help="哔哩哔哩视频URL或BV号")
    parser.add_argument("--download", action="store_true", help="下载音频")
    parser.add_argument("--save-path", help="保存路径")
    
    args = parser.parse_args()
    
    # 创建API实例
    api = BilibiliAPI()
    
    # 处理视频
    video = api.process_video(args.url_or_bvid)
    
    # 如果需要下载音频
    if args.download and video:
        api.download_song(video, args.save_path) 