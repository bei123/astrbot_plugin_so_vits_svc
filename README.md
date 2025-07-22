# So-Vits-SVC API 插件

这是一个用于 AstrBot 的 So-Vits-SVC API 语音转换插件。通过该插件，你可以方便地使用 So-Vits-SVC 的语音转换功能。

## 功能特点

- 支持语音转换（WAV格式）
- 支持 MSST 音频预处理
- 支持网易云音乐歌曲下载和转换
- 支持QQ音乐歌曲下载和转换
- 支持哔哩哔哩视频音频下载和转换
- 支持转换结果缓存，提高重复转换效率
- 可配置的API服务器地址
- 可自定义默认说话人和音调
- 支持队列管理和超时控制
- 实时状态监控
- 支持人声和伴奏混音处理
  - 支持多轨音频混合
  - 支持音量平衡调整
  - 支持混响效果
  - 支持淡入淡出效果
  - 支持音频对齐
  - 支持均衡器调节
  - 支持动态范围压缩
  - 支持母带处理

## 待完成功能

- [ ] 更多音频效果处理
  - [ ] 支持更多混响预设
  - [ ] 支持更多均衡器预设
  - [ ] 支持更多压缩器预设

## 安装方法

1. 确保你已经安装了 AstrBot
2. 将本插件目录复制到 AstrBot 的 `data/plugins` 目录下
3. 重启 AstrBot

## 配置说明

插件配置可以通过 AstrBot 管理面板进行修改，包含以下选项：

### 基础设置
- `base_url`: API服务器地址
  - 默认值: `http://localhost:1145`
  - 说明: 如果是本地部署，可以使用 `http://127.0.0.1:1145`

- `timeout`: 请求超时时间(秒)
  - 默认值: 300
  - 说明: 转换请求的超时时间

- `msst_url`: MSST-WebUI API地址
  - 默认值: `http://localhost:9000`
  - 说明: MSST-WebUI 的 API 地址

- `msst_preset`: MSST预设文件路径
  - 默认值: `wav.json`
  - 说明: MSST 处理使用的预设文件路径

- `netease_cookie`: 网易云音乐Cookie
  - 默认值: 空
  - 说明: 用于访问网易云音乐API的Cookie

- `bbdown_path`: BBDown可执行文件路径
  - 默认值: `BBDown`
  - 说明: BBDown可执行文件的路径，如果已添加到PATH中，可以直接使用BBDown

- `qqmusic_credential`: QQ音乐登录凭证
  - 默认值: 空
  - 说明: QQ音乐登录凭证，首次使用时会自动生成二维码进行登录

- `bbdown_cookie`: 哔哩哔哩Cookie
  - 默认值: 空
  - 说明: 用于访问哔哩哔哩API的Cookie，格式为SESSDATA=xxx;bili_jct=xxx;DedeUserID=xxx

### 语音转换设置
- `enable_mixing`: 是否开启混音
  - 默认值: true
  - 说明: 是否将转换后的人声与原伴奏混音

- `max_queue_size`: 最大队列大小
  - 默认值: 100
  - 说明: 超过此队列大小将拒绝新的转换请求

- `default_speaker`: 默认说话人ID
  - 默认值: "0"
  - 说明: 默认使用的说话人ID

- `default_pitch`: 默认音调调整
  - 默认值: 0
  - 说明: 默认的音调调整值，范围-12到12

- `default_k_step`: 默认扩散步数
  - 默认值: 100
  - 说明: 默认的扩散步数

- `default_shallow_diffusion`: 默认使用浅扩散
  - 默认值: true
  - 说明: 是否默认使用浅扩散

- `default_only_diffusion`: 默认使用纯扩散
  - 默认值: false
  - 说明: 是否默认使用纯扩散

- `default_cluster_infer_ratio`: 默认聚类推理比例
  - 默认值: 0
  - 说明: 默认的聚类推理比例

- `default_auto_predict_f0`: 默认自动预测音高
  - 默认值: false
  - 说明: 是否默认自动预测音高

- `default_noice_scale`: 默认噪声比例
  - 默认值: 0.4
  - 说明: 默认的噪声比例

- `default_f0_filter`: 默认过滤F0
  - 默认值: false
  - 说明: 是否默认过滤F0

- `default_f0_predictor`: 默认F0预测器
  - 默认值: "fcpe"
  - 说明: 默认使用的F0预测器

- `default_enhancer_adaptive_key`: 默认增强器自适应键
  - 默认值: 0
  - 说明: 默认的增强器自适应键值

- `default_cr_threshold`: 默认交叉参考阈值
  - 默认值: 0.05
  - 说明: 默认的交叉参考阈值

### 缓存设置
- `cache_dir`: 缓存目录
  - 默认值: `data/cache/so-vits-svc`
  - 说明: 存储缓存文件的目录路径

- `max_cache_size`: 最大缓存大小(字节)
  - 默认值: 1073741824 (1GB)
  - 说明: 缓存的最大容量

- `max_cache_age`: 最大缓存时间(秒)
  - 默认值: 604800 (7天)
  - 说明: 缓存文件的最大保存时间

### 混音设置
- `sample_rate`: 采样率
  - 默认值: 44100
  - 说明: 音频处理的采样率

- `headroom`: 伴奏增益
  - 默认值: -8
  - 说明: 伴奏的音量增益，单位dB

- `voc_input`: 人声输入增益
  - 默认值: -4
  - 说明: 人声的输入增益，单位dB

- `revb_gain`: 混响增益
  - 默认值: 0
  - 说明: 混响效果的增益，单位dB

## 使用方法

### 权限说明
- 以下命令仅限管理员使用：
  - `/svc_status` - 检查服务状态
  - `/svc_presets` - 查看预设列表
  - `/svc_speakers` - 查看说话人列表
  - `/cancel_convert` - 取消转换任务
  - `/bilibili_info` - 获取哔哩哔哩视频信息
  - `/clear_cache` - 清空所有缓存
- 以下命令所有用户均可使用：
  - `/convert_voice` - 转换语音

### 检查服务状态
```
/svc_status
```
显示当前服务状态，包括：
- 服务是否正常运行
- 模型加载状态
- 当前队列大小
- API版本
- API地址
- MSST配置信息
- 默认配置信息

### 查看预设列表
```
/svc_presets
```
显示所有可用的 MSST 预设文件列表。

### 获取哔哩哔哩视频信息
```
/bilibili_info [BV号或链接]
```
获取指定BV号或链接的视频详细信息，包括标题、UP主、分P信息等。

### 查询歌曲信息

1. 查询QQ音乐歌曲信息：
   ```
   /qqmusic_info [歌曲名]
   ```
   
   首次使用QQ音乐功能时，需要先进行登录：
   1. 执行 `/qqmusic_info` 命令后，会生成一个二维码
   2. 系统会输出类似以下格式的信息：
      ```
      [时间] [Plug] [INFO] [...]: 请复制以下下链接到浏览器打开二维码:
      [时间] [Plug] [INFO] [...]: data:image/png;base64,iVBORw0KGgoAAAAAN...（一长串base64编码）
      [时间] [Plug] [INFO] [...]: 请使用QQ音乐APP扫描二维码
      [时间] [Plug] [INFO] [...]: 等待扫码...
      ```
   3. 复制以 `data:image/png;base64,` 开头的完整链接
   4. 将链接粘贴到浏览器地址栏中并访问，即可看到登录二维码
   5. 使用 QQ 音乐 APP 扫描二维码进行登录
   6. 如果第一次扫码失败，可以再次尝试，这是正常现象
   7. 登录成功后，凭证会自动保存，下次使用无需重新登录


### 转换语音
```
/convert_voice [说话人ID] [音调调整] [歌曲名]
```
参数说明：
- `说话人ID`: 可选，不填则使用默认值
- `音调调整`: 可选，范围-12到12，不填则使用默认值
- `歌曲名`: 可选，不填则需要上传音频文件

使用示例：
```
/convert_voice 0 0  # 使用说话人0，不调整音调，需要上传音频文件
/convert_voice 1 6  # 使用说话人1，提高6个半音，需要上传音频文件
/convert_voice 0 0 起风了  # 搜索并转换网易云音乐中的"起风了"
/convert_voice 0 0 bilibili BV1xx411c7mD  # 转换哔哩哔哩视频
/convert_voice 0 0 bilibili https://www.bilibili.com/video/BV1xx411c7mD  # 转换哔哩哔哩视频
/convert_voice 0 0 qq 起风了  # 搜索并转换QQ音乐中的"起风了"
```

注意：
- 上传音频文件时支持 WAV 或 MP3 格式
- 转换过程中会显示进度提示
- 转换完成后会自动发送转换后的音频文件
- 使用网易云音乐下载时，需要正确配置 `netease_cookie`
- 使用哔哩哔哩下载时，需要正确配置 `bbdown_path` 和 `bbdown_cookie`
- 使用QQ音乐下载时，需要正确配置 `qqmusic_credential`

### 缓存管理
```
/clear_cache
```
清空所有缓存文件。此命令仅限管理员使用。

### 缓存机制说明

插件实现了一个智能的缓存系统，可以缓存已经转换过的语音文件，以提高重复转换的效率：

1. 缓存键生成：
   - 基于输入文件内容的哈希值
   - 转换参数（说话人ID、音调等）
   - 所有参数组合唯一确定一个缓存项

2. 缓存清理：
   - 自动清理过期的缓存文件
   - 当缓存总大小超过限制时，自动删除最旧的文件
   - 支持手动清理所有缓存

3. 缓存命中：
   - 当使用相同的输入文件和参数进行转换时，直接返回缓存的结果
   - 大大减少重复转换的时间和资源消耗

4. 缓存更新：
   - 每次成功转换后，自动保存到缓存
   - 缓存文件包含完整的参数信息，便于追踪和管理

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
  - 其他上传音频：使用音频内容hash
- 副歌区间缓存文件为 `data/cache/so-vits-svc/chorus_cache.json`
- 命中缓存时会直接使用已检测的副歌区间，无需再次请求API

### 使用说明
- 使用 `/convert_voice ... -c` 参数可启用副歌检测与裁切
- 副歌区间检测和缓存机制对所有支持的音频来源均有效
- 副歌区间缓存可大幅减少API调用次数，提高处理速度

## 依赖要求

- Python 3.10+
- requests
- MSST-WebUI 服务（用于音频预处理）
- BBDown（用于下载哔哩哔哩视频音频）

## 注意事项

1. 使用前请确保 So-Vits-SVC API 服务已正确部署并运行
2. 使用前请确保 MSST-WebUI 服务已正确部署并运行
3. 使用哔哩哔哩下载功能前，请确保已安装 BBDown 并正确配置
4. 建议根据服务器性能调整队列大小和超时时间
5. 音频文件会被临时保存在 `data/temp/so-vits-svc` 目录下，转换完成后自动删除
6. 使用网易云音乐下载功能时，请确保 cookie 有效且未过期
7. 使用哔哩哔哩下载功能时，请确保 cookie 有效且未过期
8. 混音功能默认开启，可以通过配置中的 `enable_mixing` 选项控制
9. 混音参数可以通过配置中的 `mixing_config` 进行调整，包括采样率、增益等

## 问题反馈

如果遇到问题，请检查：
1. API服务是否正常运行（使用 `/svc_status` 检查）
2. MSST-WebUI 服务是否正常运行
3. BBDown 是否正确安装并配置
4. 配置参数是否正确
5. 上传的音频文件格式是否支持
6. 网易云音乐 cookie 是否有效
7. 哔哩哔哩 cookie 是否有效

## API 实现

本插件使用的 API 实现参考：

- MSST-WebUI API: https://github.com/bei123/MSST-WebUI/blob/api/scripts/preset_infer_api.py
- So-Vits-SVC API: https://github.com/bei123/so-vits-svc/blob/api/fastapi_api_full_song.py
- BBDown: https://github.com/nilaoda/BBDown

## 致谢

本项目使用了以下开源项目：

- [MSST-WebUI](https://github.com/SUC-DriverOld/MSST-WebUI) - 用于音频预处理和分离
- [So-Vits-SVC](https://github.com/svc-develop-team/so-vits-svc) - 用于音频转换
- [Netease_url](https://github.com/Suxiaoqinx/Netease_url) - 用于网易云音乐解析和下载
- [BBDown](https://github.com/nilaoda/BBDown) - 用于哔哩哔哩视频下载
- [QQMusicApi](https://github.com/luren-dc/QQMusicApi) - 用于QQ音乐解析和下载
- 自动混音感谢橘子佬（代码见AutoSpark目录）

感谢这些优秀的开源项目。

## 开源协议

MIT License
