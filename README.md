# douyin-homepage-monitor

一个 [OpenClaw](https://openclaw.ai) 插件，用于监控抖音用户主页，检测新视频发布和主页信息变更，并通过 channels（iMessage、Telegram、Discord 等）发送通知。

## 功能

- **新视频通知**：检测到新视频时，自动下载并通过 channel 发送视频文件和封面图
- **主页变更通知**：昵称、签名、IP 归属地等信息变更时实时推送
- **定时自动监控**：通过 `/schedule` 创建定时任务，无需手动触发
- **多 channel 支持**：自动适配 iMessage、Telegram、Discord 等已配置的 channel

## 使用方式

### 方式一：自然语言对话（推荐）

安装后，直接在对话中描述需求，无需记忆命令：

```
帮我监控周星星的抖音主页：https://v.douyin.com/yyyy，5分钟检测一次
```

```
再加一个：刘德华 https://v.douyin.com/xxxx
```

```
帮我检测一下现在有没有新视频
```

Skill 会自动识别意图：
- 消息中包含抖音链接 → **配置模式**：自动提取链接（忽略分享文案中的无关内容）、追加监控目标、全量抓取视频目录（不自动下载历史视频）、创建定时任务
- 要求立即检测 → **执行模式**：增量检测并发送通知

**首次添加监控目标时的行为：**

1. 全量抓取该用户所有历史视频的元数据，缓存到本地目录（不自动下载视频文件）
2. 写入历史记录（后续只通知新发布的内容，不重复处理）
3. 展示作品摘要（最近 10 条）
4. 告知监控频率：`我将每 5 分钟第一时间通知你 XX 的新动态`
5. 自动创建定时任务

> 历史视频不会自动下载。需要某条历史视频时，说"下载第N条"即可按需获取。

**未指定频率时默认 5 分钟检测一次，最低 2 分钟。**

### 方式二：命令

| 命令 | 说明 |
|------|------|
| `/douyin-homepage-monitor:setup` | 引导式配置，适合首次使用 |
| `/douyin-homepage-monitor:monitor` | 立即执行一次检测 |
| `/douyin-homepage-monitor:status` | 查看监控状态、目标列表、历史记录数量 |
| `/douyin-homepage-monitor:pause` | 暂停监控 |
| `/douyin-homepage-monitor:resume` | 恢复监控 |

## 在 OpenClaw 中安装

### 方法一：通过插件市场安装（推荐）

在 OpenClaw 中运行：

```
/plugins install douyin-homepage-monitor
```

### 方法二：手动安装

1. 下载本仓库的 `.skill` 文件：

   ```bash
   curl -L -o douyin-homepage-monitor.skill \
     https://github.com/streamneil/douyin-homepage-monitor-skill/releases/latest/download/douyin-homepage-monitor.skill
   ```

2. 在 OpenClaw 中安装：

   ```
   /plugins install ./douyin-homepage-monitor.skill
   ```

### 方法三：从源码安装

1. 克隆本仓库：

   ```bash
   git clone https://github.com/streamneil/douyin-homepage-monitor-skill.git
   ```

2. 在 OpenClaw 中安装本地插件：

   ```
   /plugins install ./douyin-homepage-monitor-skill
   ```

## 初始化配置

安装后运行：

```
/douyin-homepage-monitor:setup
```

按提示完成以下步骤：
1. 填写要监控的抖音用户名称和主页链接
2. 设置监控频率（推荐 5~30 分钟）
3. 设置视频保存路径（默认 `./Download`）

### 配置 Cookie（必须）

> 抖音 API 需要完整的登录态 Cookie 才能获取用户完整视频列表（超过约 20 条）。

1. 在浏览器打开 [https://www.douyin.com](https://www.douyin.com) 并**登录**
2. 按 `F12` → Network 标签 → 刷新页面
3. 点击任意请求 → Request Headers → 找到 `cookie` 字段
4. 复制完整的 cookie 值（是很长的一串字符串，需含 `sessionid`、`uid_tt` 等字段）
5. 编辑插件目录下的 `scripts/monitor.py`，将 `COOKIE` 变量（约第 25 行）替换为复制的值

`ttwid` 和 `msToken` 会在运行时自动动态获取并覆盖 Cookie 中的旧值，Cookie 失效后（通常数月）重复上述步骤更新即可。

### 安装 Python 依赖

```bash
pip install requests aiohttp pyyaml gmssl tqdm
```

## 配置文件

配置保存在项目的 `.claude/douyin-homepage-monitor.local.md`，格式如下：

```yaml
---
enabled: true
save_dir: ./Download
cron: "*/5 * * * *"
targets:
  - label: "刘德华"
    url: "https://v.douyin.com/xxxxx"
  - label: "周杰伦"
    url: "https://v.douyin.com/yyyyy"
---
```

> 此文件包含个人配置，已默认加入 `.gitignore`，不会被提交到代码仓库。

## 通知示例

**新视频通知：**
```
刘德华 发布了新内容：新歌MV
发布时间：2024-05-10 20:00:00
[附：封面图 + 视频文件]
```

**主页变更通知：**
```
刘德华 更新了主页信息：
昵称: 刘德华官方 → 刘德华官方v2
```

## 依赖

- Python 3.8+
- `requests`、`aiohttp`、`pyyaml`、`gmssl`、`tqdm`
- OpenClaw（含 `/schedule` skill）

## 技术架构

本插件使用 [jiji262/douyin-downloader](https://github.com/jiji262/douyin-downloader) 的核心模块：

- **XBogus 签名**：完整的 URL 签名算法，与抖音官方对齐
- **MsTokenManager**：支持真实 msToken 生成和伪造回退
- **DouyinAPIClient**：抖音 Web API 客户端，支持用户信息、视频列表、视频详情等接口

**核心优势**：
- 使用 `aweme_id` 实时获取视频下载链接，**解决 CDN 链接过期问题**
- 签名算法稳定，与抖音 API 兼容性高
- 无需 ffmpeg 合合音视频，直接获取单文件直链
