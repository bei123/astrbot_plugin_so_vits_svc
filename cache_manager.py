#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
缓存管理模块
用于管理语音转换结果的缓存
"""

import os
import json
import time
import hashlib
import shutil
from typing import Optional, Dict
from astrbot.core import logger

class CacheManager:
    """缓存管理器"""

    def __init__(self, cache_dir: str = "data/cache/so-vits-svc", max_cache_size: int = 1024*1024*1024, max_cache_age: int = 7*24*60*60):
        """初始化缓存管理器

        Args:
            cache_dir: 缓存目录
            max_cache_size: 最大缓存大小（字节），默认1GB
            max_cache_age: 最大缓存时间（秒），默认7天
        """
        self.cache_dir = cache_dir
        self.max_cache_size = max_cache_size
        self.max_cache_age = max_cache_age
        self.index_file = os.path.join(cache_dir, "cache_index.json")
        self._init_cache()

    def _init_cache(self):
        """初始化缓存目录和索引"""
        os.makedirs(self.cache_dir, exist_ok=True)
        if not os.path.exists(self.index_file):
            self._save_index({})
        self._clean_expired_cache()

    def _load_index(self) -> Dict:
        """加载缓存索引"""
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载缓存索引失败: {str(e)}")
            return {}

    def _save_index(self, index: Dict):
        """保存缓存索引"""
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存索引失败: {str(e)}")

    def _generate_cache_key(self, input_file: str, speaker_id: str, pitch_adjust: int, **kwargs) -> Optional[str]:
        """生成缓存键

        Args:
            input_file: 输入文件路径
            speaker_id: 说话人ID
            pitch_adjust: 音调调整
            **kwargs: 其他参数

        Returns:
            缓存键，失败时返回 None
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(input_file):
                logger.error(f"输入文件不存在: {input_file}")
                return None

            # 读取文件内容的前1MB用于计算哈希
            with open(input_file, "rb") as f:
                file_content = f.read(1024*1024)

            # 组合所有参数
            params = {
                "file_hash": hashlib.md5(file_content).hexdigest(),
                "speaker_id": str(speaker_id),
                "pitch_adjust": str(pitch_adjust)
            }
            params.update({k: str(v) for k, v in kwargs.items()})

            # 生成参数字符串并计算哈希
            params_str = json.dumps(params, sort_keys=True)
            return hashlib.md5(params_str.encode()).hexdigest()

        except Exception as e:
            logger.error(f"生成缓存键失败: {str(e)}")
            return None

    def _clean_expired_cache(self):
        """清理过期和超大的缓存"""
        try:
            index = self._load_index()
            current_time = time.time()
            total_size = 0
            cache_files = []

            # 检查所有缓存文件
            for cache_key, cache_info in list(index.items()):
                cache_file = os.path.join(self.cache_dir, cache_key + ".wav")

                # 如果缓存文件不存在，从索引中删除
                if not os.path.exists(cache_file):
                    del index[cache_key]
                    continue

                # 获取文件信息
                file_size = os.path.getsize(cache_file)
                file_age = current_time - cache_info["timestamp"]

                # 如果文件过期，删除它
                if file_age > self.max_cache_age:
                    os.remove(cache_file)
                    del index[cache_key]
                    continue

                # 添加到缓存文件列表
                cache_files.append((cache_key, file_size, cache_info["timestamp"]))
                total_size += file_size

            # 如果总大小超过限制，删除最旧的文件直到满足大小限制
            if total_size > self.max_cache_size:
                # 按时间戳排序，最旧的在前面
                cache_files.sort(key=lambda x: x[2])

                # 删除旧文件直到总大小小于限制
                for cache_key, file_size, _ in cache_files:
                    if total_size <= self.max_cache_size:
                        break

                    cache_file = os.path.join(self.cache_dir, cache_key + ".wav")
                    os.remove(cache_file)
                    del index[cache_key]
                    total_size -= file_size

            # 保存更新后的索引
            self._save_index(index)

        except Exception as e:
            logger.error(f"清理缓存失败: {str(e)}")

    def get_cache(self, input_file: str, speaker_id: str, pitch_adjust: int, **kwargs) -> Optional[str]:
        """获取缓存的转换结果

        Args:
            input_file: 输入文件路径
            speaker_id: 说话人ID
            pitch_adjust: 音调调整
            **kwargs: 其他参数

        Returns:
            缓存的音频文件路径，如果没有缓存则返回None
        """
        try:
            cache_key = self._generate_cache_key(input_file, speaker_id, pitch_adjust, **kwargs)
            if not cache_key:
                return None

            index = self._load_index()
            if cache_key not in index:
                return None

            cache_file = os.path.join(self.cache_dir, cache_key + ".wav")
            if not os.path.exists(cache_file):
                del index[cache_key]
                self._save_index(index)
                return None

            return cache_file

        except Exception as e:
            logger.error(f"获取缓存失败: {str(e)}")
            return None

    def save_cache(self, input_file: str, output_file: str, speaker_id: str, pitch_adjust: int, **kwargs) -> Optional[str]:
        """保存转换结果到缓存

        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径
            speaker_id: 说话人ID
            pitch_adjust: 音调调整
            **kwargs: 其他参数

        Returns:
            缓存的音频文件路径，失败返回None
        """
        try:
            cache_key = self._generate_cache_key(input_file, speaker_id, pitch_adjust, **kwargs)
            if not cache_key:
                return None

            # 复制输出文件到缓存目录
            cache_file = os.path.join(self.cache_dir, cache_key + ".wav")
            shutil.copy2(output_file, cache_file)

            # 更新索引
            index = self._load_index()
            index[cache_key] = {
                "timestamp": time.time(),
                "input_file": os.path.basename(input_file),
                "speaker_id": speaker_id,
                "pitch_adjust": pitch_adjust,
                "params": kwargs
            }
            self._save_index(index)

            # 清理过期缓存
            self._clean_expired_cache()

            return cache_file

        except Exception as e:
            logger.error(f"保存缓存失败: {str(e)}")
            return None

    def clear_cache(self):
        """清空所有缓存"""
        try:
            # 删除所有缓存文件
            for file in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)

            # 重置索引
            self._save_index({})
            logger.info("缓存已清空")

        except Exception as e:
            logger.error(f"清空缓存失败: {str(e)}")

    @property
    def chorus_cache_file(self):
        return os.path.join(self.cache_dir, "chorus_cache.json")

    def _load_chorus_cache(self) -> dict:
        try:
            if not os.path.exists(self.chorus_cache_file):
                return {}
            with open(self.chorus_cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载副歌区间缓存失败: {str(e)}")
            return {}

    def _save_chorus_cache(self, cache: dict):
        try:
            with open(self.chorus_cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存副歌区间缓存失败: {str(e)}")

    def get_chorus_interval(self, cache_key: str, is_custom_key: bool = False) -> Optional[dict]:
        cache = self._load_chorus_cache()
        logger.info(f"[副歌区间缓存] 读取keys: {list(cache.keys())}")
        logger.info(f"[副歌区间缓存] 查找key: {cache_key}, 命中: {cache_key in cache}")
        return cache.get(cache_key)

    def save_chorus_interval(self, cache_key: str, interval: dict, is_custom_key: bool = False):
        cache = self._load_chorus_cache()
        cache[cache_key] = interval
        logger.info(f"[副歌区间缓存] 写入: {cache_key} -> {interval}")
        self._save_chorus_cache(cache)
        # 写入后立即读取并打印
        cache2 = self._load_chorus_cache()
        logger.info(f"[副歌区间缓存] 写入后立即读取: {cache_key} in cache2: {cache_key in cache2}, interval: {cache2.get(cache_key)}")
