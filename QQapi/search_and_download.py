import asyncio
import anyio
import httpx
import json
import os
from qqmusic_api import search, song
from qqmusic_api.login import get_qrcode, check_qrcode, QRLoginType, QRCodeLoginEvents
from qqmusic_api.utils.credential import Credential

# 保存凭证的文件名
CREDENTIAL_FILE = "qqmusic_credential.json"

def save_credential(credential: Credential):
    """保存登录凭证到文件"""
    data = {
        "musicid": credential.musicid,
        "musickey": credential.musickey
    }
    with open(CREDENTIAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

def load_credential() -> Credential | None:
    """从文件加载登录凭证"""
    if not os.path.exists(CREDENTIAL_FILE):
        return None
    try:
        with open(CREDENTIAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Credential(musicid=data["musicid"], musickey=data["musickey"])
    except:
        return None

async def login():
    # 先尝试加载已保存的凭证
    credential = load_credential()
    if credential:
        print("已加载保存的登录凭证")
        return credential
        
    print("正在获取二维码...")
    # 获取QQ登录二维码
    qr = await get_qrcode(QRLoginType.QQ)
    
    # 保存二维码图片
    qr.save("login_qr.png")
    print(f"二维码已保存为 login_qr.png，请使用QQ音乐APP扫描")
    
    # 等待扫码
    while True:
        event, credential = await check_qrcode(qr)
        if event == QRCodeLoginEvents.DONE and credential:
            print("登录成功！")
            # 保存凭证
            save_credential(credential)
            return credential
        elif event == QRCodeLoginEvents.SCAN:
            print("等待扫码...")
        elif event == QRCodeLoginEvents.CONF:
            print("已扫码，等待确认...")
        elif event == QRCodeLoginEvents.TIMEOUT:
            print("二维码已过期，请重新运行程序")
            return None
        elif event == QRCodeLoginEvents.REFUSE:
            print("已拒绝登录")
            return None
        await asyncio.sleep(2)

async def search_and_download(keyword: str, credential):
    # 1. 搜索歌曲
    search_result = await search.search_by_type(keyword=keyword, num=1)
    
    if not search_result or len(search_result) == 0:
        print(f"未找到与 '{keyword}' 相关的歌曲")
        return
    
    # 2. 获取第一个搜索结果
    first_song = search_result[0]
    song_mid = first_song['mid']
    song_name = first_song['name']
    print(f"找到歌曲: {song_name}")
    
    # 3. 获取下载链接
    file_types = [
        song.SongFileType.MASTER,    # 臻品母带
        song.SongFileType.ATMOS_2,   # 臻品全景声
        song.SongFileType.ATMOS_51,  # 臻品音质
        song.SongFileType.FLAC,      # 无损
        song.SongFileType.OGG_640,   # 640kbps
        song.SongFileType.OGG_320,   # 320kbps
        song.SongFileType.MP3_320,   # 320kbps
        song.SongFileType.ACC_192,   # 192kbps
        song.SongFileType.MP3_128,   # 128kbps
        song.SongFileType.ACC_96,    # 96kbps
        song.SongFileType.ACC_48     # 48kbps
    ]
    
    urls = None
    used_type = None
    
    # 依次尝试不同音质
    for file_type in file_types:
        try:
            urls = await song.get_song_urls(
                mid=[song_mid],
                credential=credential,
                file_type=file_type
            )
            if urls and urls.get(song_mid):
                used_type = file_type
                break
        except:
            continue
    
    if not urls or not urls.get(song_mid):
        print("无法获取下载链接，可能是会员歌曲")
        return
    
    # 4. 下载歌曲
    try:
        async with httpx.AsyncClient() as client:
            url = urls[song_mid]
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                # 根据不同的音质类型设置文件名后缀和扩展名
                quality_map = {
                    song.SongFileType.MASTER: ("master", ".flac"),    # 臻品母带
                    song.SongFileType.ATMOS_2: ("atmos_2", ".flac"),  # 臻品全景声
                    song.SongFileType.ATMOS_51: ("atmos_51", ".flac"), # 臻品音质
                    song.SongFileType.FLAC: ("flac", ".flac"),        # 无损
                    song.SongFileType.OGG_640: ("640k", ".ogg"),      # 640kbps
                    song.SongFileType.OGG_320: ("320k", ".ogg"),      # 320kbps
                    song.SongFileType.MP3_320: ("320k", ".mp3"),      # 320kbps
                    song.SongFileType.ACC_192: ("192k", ".m4a"),      # 192kbps
                    song.SongFileType.MP3_128: ("128k", ".mp3"),      # 128kbps
                    song.SongFileType.ACC_96: ("96k", ".m4a"),        # 96kbps
                    song.SongFileType.ACC_48: ("48k", ".m4a")         # 48kbps
                }
                quality, extension = quality_map.get(used_type, ("unknown", ".mp3"))
                file_path = f"{song_name}_{quality}{extension}"
                async with await anyio.open_file(file_path, "wb") as f:
                    async for chunk in response.aiter_bytes(1024 * 5):
                        if chunk:
                            await f.write(chunk)
                print(f"下载完成: {file_path} ({quality})")
    except Exception as e:
        print(f"下载出错: {e}")

async def main():
    # 1. 先登录
    credential = await login()
    if not credential:
        return
    
    # 2. 搜索并下载
    while True:
        keyword = input("\n请输入要搜索的歌曲名（输入 'q' 退出）: ")
        if keyword.lower() == 'q':
            break
        await search_and_download(keyword, credential)

if __name__ == "__main__":
    asyncio.run(main())