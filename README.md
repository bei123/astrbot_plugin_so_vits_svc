# So-Vits-SVC API 插件

这是一个用于 AstrBot 的 So-Vits-SVC API 歌曲转换插件。通过该插件，你可以方便地使用 So-Vits-SVC 的语音转换功能。

---

## 功能特点

- 支持语音转换（WAV格式）
- 支持 MSST 音频预处理
- 支持网易云音乐、QQ音乐、哔哩哔哩、抖音视频音频下载和转换
- 支持转换结果缓存，提高重复转换效率
- 可配置的 API 服务器地址
- 可自定义默认说话人和音调
- 支持队列管理和超时控制
- 实时状态监控
- 支持人声和伴奏混音处理（多轨混合、音量平衡、混响、淡入淡出、音频对齐、均衡器、压缩、母带处理）

---

## 配置说明

### 基础设置
- **`base_url`**: So-Vits-SVC API服务器地址
  - 默认值: `http://localhost:1145`
  - 说明: 指向So-Vits-SVC API服务的地址
- **`timeout`**: 请求超时时间(秒)
  - 默认值: 300
- **`msst_url`**: MSST-WebUI API地址
  - 默认值: `http://localhost:9000`
- **`msst_preset`**: MSST预设文件路径
  - 默认值: `wav.json`
- **`netease_cookie`**: 网易云音乐Cookie
  - 默认值: 空
- **`bbdown_cookie`**: 哔哩哔哩Cookie
  - 默认值: 空
- **`douyin_cookie`**: 抖音Cookie
  - 默认值: 空
  - 说明: 用于访问抖音API的Cookie，提高下载成功率。请从浏览器开发者工具中复制抖音网站的Cookie

### QQ音乐登录说明

使用QQ音乐功能时，系统会在控制台中输出base64编码的二维码图片。请按以下步骤完成登录：

1. 复制控制台中输出的base64编码图片
2. 在浏览器中打开新标签页
3. 在地址栏粘贴base64编码，按回车键
4. 使用QQ音乐APP扫描显示的二维码
5. 完成登录后即可使用QQ音乐相关功能

### 火山副歌检测API配置

使用副歌检测功能（`-c` 参数）需要配置火山引擎API密钥：

**官方文档**：[火山引擎副歌检测API文档](https://www.volcengine.com/docs/6489/73670)

#### 获取AppKey
1. 登录火山引擎控制台
2. 在"音频技术"中的应用管理页面获取AppKey
3. **重要**：首先需要在"副歌检测"服务中开通服务

#### 获取AK和SK
1. 在火山引擎控制台的"API访问密钥"页面
2. 新建访问密钥，获取AK（Access Key）和SK（Secret Key）

#### 配置参数
- **`ak`**: 火山引擎Access Key
- **`sk`**: 火山引擎Secret Key  
- **`appkey`**: 火山引擎AppKey（从音频技术应用管理获取）


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

## 快速开始

1. **配置API服务**：按照下面的环境准备部分架起So-Vits-SVC API和MSST-WebUI API
2. **配置插件参数**：设置必要的API密钥和Cookie
3. **使用转换命令**：使用 `/唱` 命令进行歌曲转换

**基本使用示例：**
```shell
/唱 0 0 起风了  # 转换网易云音乐中的"起风了"
/唱 0 0 起风了 -c  # 只转换副歌部分
/唱 0 0 起风了 -q 30  # 跳过前30秒，截取30秒进行转换
```

---

## 使用方法

### 环境准备

在使用此插件之前，需要先架起两个API服务：

#### 1. 架起 So-Vits-SVC API

1. 克隆 So-Vits-SVC 仓库（api分支）：
```bash
git clone -b api https://github.com/bei123/so-vits-svc.git
cd so-vits-svc
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 创建模型目录结构：
```bash
mkdir -p model
cd model
# 在model文件夹中创建你的模型文件夹，例如：
mkdir my_model
cd my_model
# 将模型文件（.pth）和配置文件（config.json）放入模型文件夹中
```

4. 启动 So-Vits-SVC API 服务：
```bash
python fastapi_api_full_song.py
```

默认情况下，API服务会在 `http://localhost:1145` 启动。

**注意：** 确保在 `model` 文件夹中正确放置了模型文件（.pth）和配置文件（config.json），API服务才能正常工作。

#### 2. 架起 MSST-WebUI API

1. 克隆 MSST-WebUI 仓库（api分支）：
```bash
git clone -b api https://github.com/bei123/MSST-WebUI.git
cd MSST-WebUI
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 启动 MSST-WebUI 界面：
```bash
python webUI.py
```

4. 在浏览器中访问 `http://localhost:7860`，在WebUI界面中：
   - 下载所需的模型
   - 配置预设文件
   - 将预设文件名填入插件的 `msst_preset` 配置项

5. 启动 MSST-WebUI API 服务：
```bash
python scripts/preset_infer_api.py
```

默认情况下，API服务会在 `http://localhost:9000` 启动。

**注意：** 必须先通过WebUI界面下载模型和配置预设文件，然后才能正常使用API服务。

#### 3. 验证服务状态

启动两个API服务后，可以使用以下命令验证服务是否正常运行：

```bash
# 检查 So-Vits-SVC API
curl http://localhost:1145/docs

# 检查 MSST-WebUI API  
curl http://localhost:9000/docs
```

### 常用命令

- `/svc_status`：检查服务状态
- `/svc_presets`：查看预设列表
- `/svc_speakers`：查看说话人列表
- `/cancel_convert`：取消转换任务
- `/bilibili_info`：获取哔哩哔哩视频信息
- `/clear_cache`：清空所有缓存
- `/douyin_info`：获取抖音视频信息
- `/唱`：转换语音（所有用户均可用）

### 自定义命令别名

在配置文件的 `command_config` 中可以自定义多个转换命令别名，例如：

```json
{
  "command_config": {
    "convert_command_aliases": ["唱歌", "变声", "转换", "牢剑唱"]
  }
}
```

这样你就可以使用自定义的别名来调用转换命令，比如：
- `/唱歌` 等同于 `/唱`
- `/变声` 等同于 `/唱`
- `/转换` 等同于 `/唱`
- `/牢剑唱` 等同于 `/唱`

**注意：** 在配置界面中，你可以通过"转换命令别名"设置来添加、编辑或删除这些别名。

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

### 更多使用示例

```shell
# 使用不同模型转换
/唱 0 0 起风了 -m H  # 使用H模型
/唱 0 0 起风了 -m G  # 使用G模型

# 组合使用参数
/唱 0 0 起风了 -m H -c  # 指定模型 + 副歌检测
/唱 0 0 起风了 -m H -q 30  # 指定模型 + 快速截取

# 转换不同平台的音乐
/唱 0 0 qq 起风了  # QQ音乐
/唱 0 0 bilibili BV1xx411c7mD  # 哔哩哔哩视频
/唱 0 0 douyin https://v.douyin.com/yWuwc--_--c/  # 抖音视频
```

### 参数说明

- **`-q`**: 快速截取模式，跳过前30秒后截取指定秒数，格式为 `-q 秒数`，例如 `-q 30` 表示跳过前30秒后截取30秒
- **`-m`**: 指定模型，格式为 `-m 模型名称`，例如 `-m H` 表示使用H模型
- **`-c`**: 副歌检测模式，只对检测到的副歌片段进行处理，提高转换效率

**注意：** `-q` 和 `-c` 参数不能同时使用，因为它们都是用来截取音频片段的。

> **注意：**

> - 转换完成后会自动发送转换后的音频文件
> - 使用网易云音乐下载时，需要正确配置 `netease_cookie`
> - 使用哔哩哔哩下载时，需要正确配置 `bbdown_cookie`
> - 使用QQ音乐下载时，需要按照QQ音乐登录说明完成登录
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
6. 火山引擎副歌检测API配置是否正确（使用 `-c` 参数时）
7. QQ音乐登录是否成功

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