import aiohttp
from functools import reduce
from hashlib import md5
import urllib.parse
import time
import re
import os
import asyncio


mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

def getMixinKey(orig: str):
    "对 imgKey 和 subKey 进行字符顺序打乱编码"
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, "")[:32]

def encWbi(params: dict, img_key: str, sub_key: str):
    "为请求参数进行 wbi 签名"
    mixin_key = getMixinKey(img_key + sub_key)
    curr_time = round(time.time())
    params["wts"] = curr_time                                   # 添加 wts 字段
    params = dict(sorted(params.items()))                       # 按照 key 重排参数
    # 过滤 value 中的 "!'()*" 字符
    params = {
        k : "".join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v
        in params.items()
    }
    query = urllib.parse.urlencode(params)                      # 序列化参数
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()    # 计算 w_rid
    params["w_rid"] = wbi_sign
    return params

def sanitize_filename(name):
    # 去除Windows非法文件名字符
    return re.sub(r'[\\/:*?"<>|]', "", name)

def unescape_url(url):
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), url)

async def fetch_json(session, url, **kwargs):
    async with session.get(url, **kwargs) as resp:
        resp.raise_for_status()
        return await resp.json()

async def download_file(session, url, path, headers):
    async with session.get(url, headers=headers) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            async for chunk in resp.content.iter_chunked(8192):
                f.write(chunk)

async def download_audio_by_url(session, url, save_path, headers):
    print(f"[音频下载] 正在下载音频流: {url}")
    async with session.get(url, headers=headers) as resp:
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            async for chunk in resp.content.iter_chunked(8192):
                f.write(chunk)
    print(f"[音频下载] 音频流已保存为: {save_path}")

async def getWbiKeys(session, headers):
    "获取最新的 img_key 和 sub_key"
    url = "https://api.bilibili.com/x/web-interface/nav"
    async with session.get(url, headers=headers) as resp:
        resp.raise_for_status()
        json_content = await resp.json()
        img_url: str = json_content["data"]["wbi_img"]["img_url"]
        sub_url: str = json_content["data"]["wbi_img"]["sub_url"]
        img_key = img_url.rsplit("/", 1)[1].split(".")[0]
        sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]
        return img_key, sub_key

async def fetch_bilibili_video_info(bvid, cookie=None):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "referer": "https://www.bilibili.com",
        "cookie": cookie or ""
    }
    async with aiohttp.ClientSession() as session:
        info_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        info_data = await fetch_json(session, info_url, headers=headers)
        if info_data["code"] == 0:
            video_info = info_data["data"]
            parts = [{
                "index": 1,
                "title": video_info["title"],
                "duration": video_info["duration"]
            }]
            return {
                "bvid": bvid,
                "title": video_info["title"],
                "uploader": video_info["owner"]["name"],
                "parts": parts,
                "cid": video_info["cid"],
                "desc": video_info["desc"],
                "pic": video_info["pic"]
            }
        else:
            return {}

async def download_bilibili_audio(bvid, save_dir, only_audio=False, cookie=None):
    # 构造headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "referer": "https://www.bilibili.com",
        "cookie": cookie or ""
    }
    os.makedirs(save_dir, exist_ok=True)
    async with aiohttp.ClientSession() as session:
        # 获取视频信息
        info = await fetch_bilibili_video_info(bvid, cookie=cookie)
        if not info:
            print("获取视频信息失败")
            return None
        cid = info["cid"]
        title = sanitize_filename(info["title"])
        # 获取wbi签名
        img_key, sub_key = await getWbiKeys(session, headers)
        params = {
            "bvid": bvid,
            "cid": cid,
            "qn": "80",
            "fnval": "16",
            "fnver": "0",
            "fourk": "1",
            "otype": "json",
            "platform": "web",
        }
        signed_params = encWbi(params, img_key, sub_key)
        stream_url = "https://api.bilibili.com/x/player/wbi/playurl"
        async with session.get(stream_url, params=signed_params, headers=headers) as stream_resp:
            stream_resp.raise_for_status()
            stream_data = await stream_resp.json()
        dash = stream_data.get("data", {}).get("dash")
        if not dash:
            print("未获取到dash流信息")
            return None
        # 以下为原有音频下载逻辑
        print("可用音频流：")
        for a in dash["audio"]:
            print(f"id={a['id']} 码率={a['bandwidth']//1000}kbps 编码={a['codecs']} baseUrl={a['baseUrl']}")
        if "flac" in dash and dash["flac"] and dash["flac"].get("audio"):
            f = dash["flac"]["audio"]
            print(f"无损音频流: id={f['id']} 码率={f['bandwidth']//1000}kbps 编码={f['codecs']} baseUrl={f['baseUrl']}")
        # 优先选择flac无损音轨
        audio_url = None
        audio_desc = None
        if "flac" in dash and dash["flac"] and dash["flac"].get("audio"):
            f = dash["flac"]["audio"]
            audio_url = unescape_url(f["baseUrl"])
            audio_desc = f["id"]
        else:
            audio_quality_priority = [30250, 30280, 30232, 30216]
            for q in audio_quality_priority:
                for audio in dash["audio"]:
                    if audio.get("id") == q:
                        audio_url = unescape_url(audio["baseUrl"])
                        audio_desc = q
                        break
                if audio_url:
                    break
            if not audio_url:
                audio_url = unescape_url(dash["audio"][0]["baseUrl"])
                audio_desc = dash["audio"][0].get("id")
        audio_path = os.path.join(save_dir, "audio.m4s")
        print(f"[DASH] 正在下载音频流（音质代码：{audio_desc}）...")
        await download_file(session, audio_url, audio_path, headers)
        print(f"[DASH] 音频流已保存为: {audio_path}")
        if only_audio:
            # 转为wav
            output_wav = os.path.join(save_dir, f"{title}.wav")
            print(f"[DASH] 正在转换音频流为: {output_wav}")
            try:
                import asyncio
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", audio_path, "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", output_wav
                )
                await proc.communicate()
                print(f"[DASH] 转换完成: {output_wav}")
                os.remove(audio_path)
            except Exception as e:
                print("[DASH] 音频转换失败，请手动转换。错误：", e)
        # 杜比/无损音频单独下载
        if "dolby" in dash and dash["dolby"] and dash["dolby"].get("audio"):
            dolby_url = unescape_url(dash["dolby"]["audio"][0]["baseUrl"])
            dolby_path = os.path.join(save_dir, "dolby_audio.m4s")
            print("[DASH] 正在下载杜比音频流...")
            await download_file(session, dolby_url, dolby_path, headers)
            print(f"[DASH] 杜比音频流已保存为: {dolby_path}")
        if "flac" in dash and dash["flac"] and dash["flac"].get("audio"):
            flac_url = unescape_url(dash["flac"]["audio"]["baseUrl"])
            flac_path = os.path.join(save_dir, "flac_audio.m4s")
            print("[DASH] 正在下载无损音频流...")
            await download_file(session, flac_url, flac_path, headers)
            print(f"[DASH] 无损音频流已保存为: {flac_path}")
        return audio_path

async def bilibili_download_api(bvid, save_dir, qn="80", fnval="16", only_audio=False, cookie=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "referer": "https://www.bilibili.com",
        "cookie": cookie or ""
    }
    os.makedirs(save_dir, exist_ok=True)
    # 获取视频信息
    info = await fetch_bilibili_video_info(bvid, cookie=cookie)
    if not info:
        print("获取视频信息失败")
        return
    cid = info["cid"]
    title = sanitize_filename(info["title"])
    async with aiohttp.ClientSession() as session:
        img_key, sub_key = await getWbiKeys(session, headers)
        params = {
            "bvid": bvid,
            "cid": cid,
            "qn": qn,
            "fnval": fnval,
            "fnver": "0",
            "fourk": "1",
            "otype": "json",
            "platform": "web",
        }
        signed_params = encWbi(params, img_key, sub_key)
        stream_url = "https://api.bilibili.com/x/player/wbi/playurl"
        async with session.get(stream_url, params=signed_params, headers=headers) as stream_resp:
            stream_resp.raise_for_status()
            stream_data = await stream_resp.json()
        data = stream_data.get("data", {})
        if "dash" in data:
            dash = data["dash"]
            video_url = unescape_url(dash["video"][0]["baseUrl"])
            if only_audio:
                await download_bilibili_audio(bvid, save_dir, only_audio=True, cookie=cookie)
            else:
                video_path = os.path.join(save_dir, "video.m4s")
                print("[DASH] 正在下载视频流...")
                await download_file(session, video_url, video_path, headers)
                await download_bilibili_audio(bvid, save_dir, only_audio=False, cookie=cookie)
                print(f"[DASH] 视频流已保存为: {video_path}")
                audio_path = os.path.join(save_dir, "audio.m4s")
                print(f"[DASH] 音频流已保存为: {audio_path}")
                # 合并音视频流
                output_mp4 = os.path.join(save_dir, f"{title}.mp4")
                print(f"[DASH] 正在合并音视频流为: {output_mp4}")
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "ffmpeg", "-y", "-i", video_path, "-i", audio_path,
                        "-c:v", "copy", "-c:a", "copy", "-f", "mp4", output_mp4
                    )
                    await proc.communicate()
                    print(f"[DASH] 合并完成: {output_mp4}")
                    os.remove(video_path)
                    os.remove(audio_path)
                except Exception as e:
                    print("[DASH] 合并失败，请手动合并。错误：", e)
        elif "durl" in data:
            durl = data["durl"]
            print("提示：该视频不支持DASH流，已自动切换为MP4分段下载。")
            print("[FLV/MP4] 正在下载视频流...")
            seg_paths = []
            for i, item in enumerate(durl):
                seg_url = unescape_url(item["url"])
                seg_path = os.path.join(save_dir, f"segment{i+1}.flv")
                print(f"下载分段{i+1}...")
                await download_file(session, seg_url, seg_path, headers)
                print(f"分段{i+1}已保存为: {seg_path}")
                seg_paths.append(seg_path)
            output_mp4 = os.path.join(save_dir, f"{title}.mp4")
            print(f"[FLV/MP4] 正在合并分段为: {output_mp4}")
            try:
                concat_list = "|".join(seg_paths)
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", f"concat:{concat_list}", "-c", "copy", output_mp4
                )
                await proc.communicate()
                print(f"[FLV/MP4] 合并完成: {output_mp4}")
                for seg_path in seg_paths:
                    os.remove(seg_path)
            except Exception as e:
                print("[FLV/MP4] 合并失败，请手动合并。错误：", e)
        else:
            print("未获取到视频流信息")
