# So-Vits-SVC API 插件

这是一个用于 AstrBot 的 So-Vits-SVC API 语音转换插件。通过该插件，你可以方便地使用 So-Vits-SVC 的语音转换功能。

---

## 功能特点

- 支持语音转换（WAV格式）
- 支持 MSST 音频预处理
- 支持网易云音乐、QQ音乐、哔哩哔哩视频音频下载和转换
- 支持转换结果缓存，提高重复转换效率
- 可配置的 API 服务器地址
- 可自定义默认说话人和音调
- 支持队列管理和超时控制
- 实时状态监控
- 支持人声和伴奏混音处理（多轨混合、音量平衡、混响、淡入淡出、音频对齐、均衡器、压缩、母带处理）

---

## 配置说明

### 基础设置
- **`base_url`**: API服务器地址（sovits-svc-api）
  - 默认值: `http://localhost:1145`
  - 说明: 
- **`timeout`**: 请求超时时间(秒)
  - 默认值: 300
- **`msst_url`**: MSST-WebUI API地址
  - 默认值: `http://localhost:9000`
- **`msst_preset`**: MSST预设文件路径
  - 默认值: `wav.json`
- **`netease_cookie`**: 网易云音乐Cookie
  - 默认值: 空
- **`bbdown_path`**: BBDown可执行文件路径
  - 默认值: `BBDown`
- **`qqmusic_credential`**: QQ音乐登录凭证
  - 默认值: 空
- **`bbdown_cookie`**: 哔哩哔哩Cookie
  - 默认值: 空
- ** 'douyin_cookie' **: 抖音Cookie
  - 默认值: 空


### 语音转换设置
- **`enable_mixing`**: 是否开启混音（默认 true）
- **`max_queue_size`**: 最大队列大小（默认 100）
- **`default_speaker`**: 默认说话人ID（默认 "0"）
- **`default_pitch`**: 默认音调调整（默认 0，范围-12到12）
- **`default_k_step`**: 默认扩散步数（默认 100）
- **`default_shallow_diffusion`**: 默认使用浅扩散（默认 true）
- **`default_only_diffusion`**: 默认使用纯扩散（默认 false）
- **`default_cluster_infer_ratio`**: 默认聚类推理比例（默认 0）
- **`default_auto_predict_f0`**: 默认自动预测音高（默认 false）
- **`default_noice_scale`**: 默认噪声比例（默认 0.4）
- **`default_f0_filter`**: 默认过滤F0（默认 false）
- **`default_f0_predictor`**: 默认F0预测器（默认 "fcpe"）
- **`default_enhancer_adaptive_key`**: 默认增强器自适应键（默认 0）
- **`default_cr_threshold`**: 默认交叉参考阈值（默认 0.05）

### 缓存设置
- **`cache_dir`**: 缓存目录（默认 `data/cache/so-vits-svc`）
- **`max_cache_size`**: 最大缓存大小(字节)（默认 1GB）
- **`max_cache_age`**: 最大缓存时间(秒)（默认 7天）

### 混音设置
- **`sample_rate`**: 采样率（默认 44100）
- **`headroom`**: 伴奏增益（默认 -8dB）
- **`voc_input`**: 人声输入增益（默认 -4dB）
- **`revb_gain`**: 混响增益（默认 0dB）

---

## 使用方法

### 常用命令

- `/svc_status`：检查服务状态
- `/svc_presets`：查看预设列表
- `/svc_speakers`：查看说话人列表
- `/cancel_convert`：取消转换任务
- `/bilibili_info`：获取哔哩哔哩视频信息
- `/clear_cache`：清空所有缓存
- `/douyin_info`：获取抖音视频信息
- `/唱`：转换语音（所有用户均可用）

### 检查服务状态
```shell
/svc_status
```
显示当前服务状态，包括：服务是否正常运行、模型加载状态、队列大小、API版本、API地址、MSST配置信息、默认配置信息。

### 转换语音
默认使用网易云音乐作为默认源
```shell
/唱 0 0 起风了 -m # -m H 参数可以指定模型
/唱 0 0 起风了 -c # -c 参数使用副歌检测，只对副歌片段进行处理
/唱 0 0 起风了  # 搜索并转换网易云音乐中的"起风了"
/唱 0 0 bilibili BV1xx411c7mD  # 通过BV号转换哔哩哔哩视频
/唱 0 0 bilibili https://www.bilibili.com/video/BV1xx411c7mD  # 提供链接转换哔哩哔哩视频
/唱 0 0 qq 起风了  # 搜索并转换QQ音乐中的"起风了"
/唱 0 0 douyin https://v.douyin.com/yWuwc--_--c/  # 转换抖音视频
```

> **注意：**

> - 转换完成后会自动发送转换后的音频文件
> - 使用网易云音乐下载时，需要正确配置 `netease_cookie`
> - 使用哔哩哔哩下载时，需要正确配置 `bbdown_path` 和 `bbdown_cookie`
> - 使用QQ音乐下载时，需要正确配置 `qqmusic_credential`
> - 使用抖音下载时，需要正确配置 `douyin_cookie`

---

## 副歌检测与缓存

插件支持自动检测音频的副歌（高潮）区间，并在推理前自动裁切副歌片段，提升转换效率和体验。

### 支持的副歌检测
- 支持对上传音频、网易云音乐、QQ音乐、哔哩哔哩视频等来源的音频进行副歌区间检测
- 副歌检测基于火山引擎SAMI接口，自动识别歌曲高潮部分
- 副歌区间检测结果会自动裁切音频，仅对副歌片段进行后续处理

### 副歌区间缓存机制
- 副歌区间检测结果会缓存，避免同一音频/歌曲重复请求副歌检测API
- 缓存key策略：
  - 网易云：`netease_<歌曲ID>_<音质>`
  - QQ音乐：`qq_<songmid>_<音质>`
  - 哔哩哔哩：`bilibili_<bvid>`
  - 抖音：`douyin_<aweme_id>`
- 副歌区间缓存文件为 `data/cache/so-vits-svc/chorus_cache.json`
- 命中缓存时会直接使用已检测的副歌区间，无需再次请求API
- 副歌区间检测和缓存机制对所有支持的音频来源均有效
- 副歌区间缓存可大幅减少API调用次数，提高处理速度

---

## 缓存机制说明

插件实现了一个简单的缓存系统，用于存储转换结果，提高转换效率。该系统基于输入文件内容、转换参数和缓存配置生成唯一的缓存键，并使用哈希值作为缓存键。缓存项的存储路径为 `data/cache/so-vits-svc`，默认大小为1GB，默认缓存时间为7天。

1. **缓存键生成：**
   - 基于输入文件内容的哈希值
   - 转换参数（说话人ID、音调等）
   - 所有参数组合唯一确定一个缓存项
2. **缓存清理：**
   - 自动清理过期的缓存文件
   - 当缓存总大小超过限制时，自动删除最旧的文件
   - 支持手动清理所有缓存
3. **缓存命中：**
   - 当使用相同的输入文件和参数进行转换时，直接返回缓存的结果
   - 大大减少重复转换的时间和资源消耗
4. **缓存更新：**
   - 每次成功转换后，自动保存到缓存
   - 缓存文件包含完整的参数信息，便于追踪和管理

---

## 问题反馈

如果遇到问题，请检查：
1. API服务是否正常运行（使用 `/svc_status` 检查）
2. MSST-WebUI 服务是否正常运行
3. 配置参数是否正确
4. 网易云音乐 cookie 是否有效
5. 哔哩哔哩 cookie 是否有效

---

## API 实现

本插件使用的 API 实现参考：

- [MSST-WebUI API](https://github.com/bei123/MSST-WebUI/blob/api/scripts/preset_infer_api.py)
- [So-Vits-SVC API](https://github.com/bei123/so-vits-svc/blob/api/fastapi_api_full_song.py)
- [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)

---

## 致谢

本项目使用了以下开源项目：

- [MSST-WebUI](https://github.com/SUC-DriverOld/MSST-WebUI) - 用于音频预处理和分离
- [So-Vits-SVC](https://github.com/svc-develop-team/so-vits-svc) - 用于音频转换
- [Netease_url](https://github.com/Suxiaoqinx/Netease_url) - 用于网易云音乐解析和下载
- [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) - 用于哔哩哔哩音频下载，与解析
- [QQMusicApi](https://github.com/luren-dc/QQMusicApi) - 用于QQ音乐解析和下载
- [Douyin_TikTok_Download_API](https://github.com/Evil0ctal/Douyin_TikTok_Download_API) - 用于抖音音频下载，与解析
- 自动混音感谢橘子佬（代码见AutoSpark目录）

感谢这些优秀的开源项目。