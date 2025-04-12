#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
网易云音乐API模块
提供搜索和下载网易云音乐的功能
"""

import requests
import json
import os
import urllib.parse
from hashlib import md5
from random import randrange
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from typing import Dict

class NeteaseMusicAPI:
    """网易云音乐API类"""
    
    def __init__(self, config: Dict = None):
        """初始化API
        
        Args:
            config: 插件配置字典
        """
        self.config = config or {}
        self.cookies = self._parse_cookie(self.config.get('base_setting', {}).get('netease_cookie', ''))
    
    def _parse_cookie(self, text):
        """解析cookie字符串为字典"""
        cookie_ = [item.strip().split('=', 1) for item in text.strip().split(';') if item]
        cookie_ = {k.strip(): v.strip() for k, v in cookie_}
        return cookie_
    
    def _hex_digest(self, data):
        """将字节数据转换为十六进制字符串"""
        return "".join([hex(d)[2:].zfill(2) for d in data])
    
    def _hash_digest(self, text):
        """计算文本的MD5摘要"""
        HASH = md5(text.encode("utf-8"))
        return HASH.digest()
    
    def _hash_hex_digest(self, text):
        """计算文本的MD5摘要并转换为十六进制字符串"""
        return self._hex_digest(self._hash_digest(text))
    
    def _post(self, url, params):
        """发送POST请求"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36 Chrome/91.0.4472.164 NeteaseMusicDesktop/2.10.2.200154',
            'Referer': '',
        }
        cookies = {
            "os": "pc",
            "appver": "",
            "osver": "",
            "deviceId": "pyncm!"
        }
        cookies.update(self.cookies)
        response = requests.post(url, headers=headers, cookies=cookies, data={"params": params})
        return response.text
    
    def search(self, keyword, limit=30):
        """搜索歌曲
        
        Args:
            keyword: 搜索关键词
            limit: 返回结果数量限制，默认30
            
        Returns:
            搜索结果列表，每个元素包含歌曲ID、名称、歌手、专辑等信息
        """
        url = "https://interface3.music.163.com/eapi/search/get"
        AES_KEY = b"e82ckenh8dichen8"
        config = {
            "os": "pc",
            "appver": "",
            "osver": "",
            "deviceId": "pyncm!",
            "requestId": str(randrange(20000000, 30000000))
        }

        payload = {
            'hlpretag': '<span class="s-fc7">',
            'hlposttag': '</span>',
            's': keyword,
            'type': '1',
            'offset': '0',
            'total': 'true',
            'limit': str(limit),
            'header': json.dumps(config),
        }

        url2 = urllib.parse.urlparse(url).path.replace("/eapi/", "/api/")
        digest = self._hash_hex_digest(f"nobody{url2}use{json.dumps(payload)}md5forencrypt")
        params = f"{url2}-36cd479b6b5-{json.dumps(payload)}-36cd479b6b5-{digest}"
        padder = padding.PKCS7(algorithms.AES(AES_KEY).block_size).padder()
        padded_data = padder.update(params.encode()) + padder.finalize()
        cipher = Cipher(algorithms.AES(AES_KEY), modes.ECB())
        encryptor = cipher.encryptor()
        enc = encryptor.update(padded_data) + encryptor.finalize()
        params = self._hex_digest(enc)
        
        response_text = self._post(url, params)
        
        try:
            result = json.loads(response_text)
            if 'result' in result and 'songs' in result['result']:
                songs = result['result']['songs']
                return [{
                    'id': song.get('id'),
                    'name': song.get('name', '未知歌曲'),
                    'artists': [artist.get('name', '未知歌手') for artist in song.get('artists', [])],
                    'album': song.get('album', {}).get('name', '未知专辑'),
                    'pic_url': song.get('album', {}).get('picUrl', '')  # 修改字段名为pic_url
                } for song in songs if song.get('id') and song.get('name')]  # 只返回有效数据
            return []
        except json.JSONDecodeError:
            print(f"解析JSON失败，响应内容: {response_text[:100]}...")
            return []
    
    def get_song_url(self, song_id, level="lossless"):
        """获取歌曲下载链接
        
        Args:
            song_id: 歌曲ID
            level: 音质等级，可选值：standard, exhigh, lossless, hires, sky, jyeffect, jymaster
            
        Returns:
            歌曲下载链接和大小信息
        """
        url = "https://interface3.music.163.com/eapi/song/enhance/player/url/v1"
        AES_KEY = b"e82ckenh8dichen8"
        config = {
            "os": "pc",
            "appver": "",
            "osver": "",
            "deviceId": "pyncm!",
            "requestId": str(randrange(20000000, 30000000))
        }

        payload = {
            'ids': [song_id],
            'level': level,
            'encodeType': 'flac',
            'header': json.dumps(config),
        }

        if level == 'sky':
            payload['immerseType'] = 'c51'
        
        url2 = urllib.parse.urlparse(url).path.replace("/eapi/", "/api/")
        digest = self._hash_hex_digest(f"nobody{url2}use{json.dumps(payload)}md5forencrypt")
        params = f"{url2}-36cd479b6b5-{json.dumps(payload)}-36cd479b6b5-{digest}"
        padder = padding.PKCS7(algorithms.AES(AES_KEY).block_size).padder()
        padded_data = padder.update(params.encode()) + padder.finalize()
        cipher = Cipher(algorithms.AES(AES_KEY), modes.ECB())
        encryptor = cipher.encryptor()
        enc = encryptor.update(padded_data) + encryptor.finalize()
        params = self._hex_digest(enc)
        
        response_text = self._post(url, params)
        
        try:
            result = json.loads(response_text)
            if 'data' in result and result['data'] and result['data'][0]['url']:
                return {
                    'url': result['data'][0]['url'],
                    'size': result['data'][0]['size'],
                    'level': result['data'][0]['level']
                }
            return None
        except json.JSONDecodeError:
            print(f"解析JSON失败，响应内容: {response_text[:100]}...")
            return None
    
    def get_song_detail(self, song_id):
        """获取歌曲详细信息
        
        Args:
            song_id: 歌曲ID
            
        Returns:
            歌曲详细信息，包括名称、歌手、专辑等
        """
        url = "https://interface3.music.163.com/api/v3/song/detail"
        data = {'c': json.dumps([{"id":song_id,"v":0}])}
        response = requests.post(url=url, data=data)
        result = response.json()
        
        if 'songs' in result and result['songs']:
            song = result['songs'][0]
            return {
                'name': song['name'],
                'artists': [artist['name'] for artist in song['ar']],
                'album': song['al']['name'],
                'picUrl': song['al']['picUrl']
            }
        return None
    
    def get_lyric(self, song_id):
        """获取歌词
        
        Args:
            song_id: 歌曲ID
            
        Returns:
            歌词信息，包括原文歌词和翻译歌词
        """
        url = "https://interface3.music.163.com/api/song/lyric"
        data = {'id': song_id, 'cp': 'false', 'tv': '0', 'lv': '0', 'rv': '0', 'kv': '0', 'yv': '0', 'ytv': '0', 'yrv': '0'}
        response = requests.post(url=url, data=data, cookies=self.cookies)
        result = response.json()
        
        return {
            'lyric': result.get('lrc', {}).get('lyric', ''),
            'tlyric': result.get('tlyric', {}).get('lyric', None)
        }
    
    def get_music_level(self, value):
        """获取音质描述
        
        Args:
            value: 音质代码
            
        Returns:
            音质描述
        """
        levels = {
            'standard': "标准音质",
            'exhigh': "极高音质",
            'lossless': "无损音质",
            'hires': "Hires音质",
            'sky': "沉浸环绕声",
            'jyeffect': "高清环绕声",
            'jymaster': "超清母带"
        }
        return levels.get(value, "未知音质")
    
    def format_size(self, value):
        """格式化文件大小
        
        Args:
            value: 文件大小（字节）
            
        Returns:
            格式化后的文件大小
        """
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = 1024.0
        for i in range(len(units)):
            if (value / size) < 1:
                return "%.2f%s" % (value, units[i])
            value = value / size
        return value
    
    def get_song_with_highest_quality(self, keyword):
        """获取搜索到的第一首歌曲的最高音质版本
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            歌曲信息，包括下载链接、歌词等
        """
        # 1. 搜索歌曲
        songs = self.search(keyword)
        
        if not songs:
            print(f"未找到与 '{keyword}' 相关的歌曲")
            return None
        
        # 2. 获取第一首歌曲
        first_song = songs[0]
        song_id = first_song['id']
        
        # 3. 按音质从高到低尝试
        qualities = ["jymaster", "jyeffect", "sky", "hires", "lossless", "exhigh", "standard"]
        
        for quality in qualities:
            url_info = self.get_song_url(song_id, quality)
            
            if url_info:
                song_url = url_info['url']
                song_size = url_info['size']
                song_level = url_info['level']
                
                # 4. 获取歌词
                lyric_info = self.get_lyric(song_id)
                
                # 5. 返回结果
                return {
                    "status": 200,
                    "id": song_id,
                    "name": first_song['name'],
                    "pic": first_song.get('pic_url', ''),  # 使用新的字段名
                    "ar_name": ', '.join(first_song['artists']),
                    "al_name": first_song['album'],
                    "level": self.get_music_level(song_level),
                    "size": self.format_size(song_size),
                    "url": song_url,
                    "lyric": lyric_info['lyric'],
                    "tlyric": lyric_info['tlyric']
                }
        
        print("获取歌曲详情失败")
        return None
    
    def download_song(self, song_info, save_path=None):
        """下载歌曲
        
        Args:
            song_info: 歌曲信息，包含url和name字段
            save_path: 保存路径，默认为当前目录
            
        Returns:
            下载的文件路径
        """
        if not song_info or not song_info.get("url"):
            print("无效的歌曲信息")
            return None
        
        download_url = song_info["url"]
        song_name = song_info["name"]
        
        if save_path:
            if not os.path.exists(save_path):
                os.makedirs(save_path)
            file_path = os.path.join(save_path, f"{song_name}.mp3")
        else:
            file_path = f"{song_name}.mp3"
        
        print(f"开始下载 {song_name}...")
        response = requests.get(download_url, stream=True)
        if response.status_code == 200:
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            print(f"歌曲已下载到 {file_path}")
            return file_path
        else:
            print("下载失败")
            return None

# 使用示例
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="网易云音乐API工具")
    parser.add_argument("keyword", help="搜索关键词")
    parser.add_argument("--download", action="store_true", help="下载歌曲")
    parser.add_argument("--save-path", help="保存路径")
    
    args = parser.parse_args()
    
    # 创建API实例
    api = NeteaseMusicAPI()
    
    # 搜索并获取最高音质版本
    song = api.get_song_with_highest_quality(args.keyword)
    
    # 如果需要下载歌曲
    if args.download and song:
        api.download_song(song, args.save_path) 