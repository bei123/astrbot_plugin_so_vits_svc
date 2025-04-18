"""QQ音乐搜索和下载模块"""

import asyncio
import json

import aiofiles
import aiohttp

from .qqmusic_api import search, song
from .qqmusic_api.login import QRCodeLoginEvents, QRLoginType, check_qrcode, get_qrcode
from .qqmusic_api.utils.credential import Credential


def save_credential(credential: Credential):
    """保存登录凭证到文件"""
    data = {
        "musicid": credential.musicid,
        "musickey": credential.musickey
    }
    with open("qqmusic_credential.json", "w", encoding="utf-8") as f:
        json.dump(data, f)


def load_credential() -> Credential | None:
    """从文件加载登录凭证"""
    try:
        with open("qqmusic_credential.json", encoding="utf-8") as f:
            data = json.load(f)
        return Credential(musicid=data["musicid"], musickey=data["musickey"])
    except Exception:
        return None


async def login() -> Credential | None:
    """执行QQ音乐登录流程
    
    Returns:
        Optional[Credential]: 登录凭证,如果登录失败则返回None
    """
    # 先尝试加载已保存的凭证
    credential = load_credential()
    if credential:
        return credential
        
    # 需要重新登录
    print("正在获取QQ音乐登录二维码...")
    try:
        # 获取QQ登录二维码
        qr = await get_qrcode(QRLoginType.QQ)
        
        # 保存二维码图片
        qr.save("login_qr.png")
        print("二维码已保存为 login_qr.png, 请使用QQ音乐APP扫描")
        
        # 等待扫码
        while True:
            event, credential = await check_qrcode(qr)
            if event == QRCodeLoginEvents.DONE and credential:
                print("登录成功!")
                # 保存凭证
                save_credential(credential)
                return credential
            if event == QRCodeLoginEvents.SCAN:
                print("等待扫码...")
            elif event == QRCodeLoginEvents.CONF:
                print("已扫码, 等待确认...")
            elif event == QRCodeLoginEvents.TIMEOUT:
                print("二维码已过期, 请重新运行程序")
                return None
            elif event == QRCodeLoginEvents.REFUSE:
                print("已拒绝登录")
                return None
            await asyncio.sleep(2)
    except Exception as e:
        print(f"登录出错: {e}")
        return None


async def download_song(url: str, filename: str) -> bool:
    """下载歌曲文件
    
    Args:
        url: 下载链接
        filename: 保存的文件名
        
    Returns:
        bool: 是否下载成功
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    async with aiofiles.open(filename, "wb") as f:
                        await f.write(await response.read())
                    return True
                return False
    except Exception as e:
        print(f"下载出错: {e}")
        return False


async def search_and_download(keyword: str, credential: Credential):
    """搜索并下载歌曲
    
    Args:
        keyword: 搜索关键词
        credential: 登录凭证
    """
    # 1. 搜索歌曲
    search_result = await search.search_by_type(keyword=keyword, num=1)
    if not search_result:
        print("未找到相关歌曲")
        return
        
    song_info = search_result[0]
    song_mid = song_info["mid"]
    song_name = song_info["name"]
    singer_name = song_info.get("singer", [{}])[0].get("name", "未知歌手")
    
    print(f"\n找到歌曲: {song_name} - {singer_name}")
    
    # 2. 获取下载链接
    # 尝试不同音质
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
        except Exception:
            continue
            
    if not urls or not urls.get(song_mid):
        print("无法获取下载链接, 可能是会员歌曲")
        return
        
    # 3. 下载歌曲
    url = urls[song_mid]
    print(f"开始下载: {song_name} - {singer_name}")
    print(f"音质: {used_type.name if used_type else '未知'}")
    
    # 获取文件扩展名
    extension = ".mp3"
    if used_type in [song.SongFileType.FLAC, song.SongFileType.MASTER, 
                    song.SongFileType.ATMOS_2, song.SongFileType.ATMOS_51]:
        extension = ".flac"
    elif used_type in [song.SongFileType.OGG_640, song.SongFileType.OGG_320]:
        extension = ".ogg"
    elif used_type in [song.SongFileType.ACC_192, song.SongFileType.ACC_96, 
                      song.SongFileType.ACC_48]:
        extension = ".m4a"
        
    # 保存文件
    filename = f"{song_name} - {singer_name}{extension}"
    if await download_song(url, filename):
        print(f"下载完成: {filename}")
    else:
        print("下载失败")


async def main():
    """主函数"""
    # 1. 先登录
    credential = await login()
    if not credential:
        return
        
    # 2. 搜索并下载
    while True:
        keyword = input("\n请输入要搜索的歌曲名(输入 'q' 退出): ")
        if keyword.lower() == "q":
            break
        await search_and_download(keyword, credential)


if __name__ == "__main__":
    asyncio.run(main())