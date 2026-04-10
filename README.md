# douyin-homepage-monitor

一个 [OpenClaw](https://openclaw.ai) 插件，用于监控抖音用户主页，检测新视频发布和主页信息变更，并通过 channels（iMessage、Telegram、Discord 等）发送通知。

## 功能

- **新视频通知**：检测到新视频时，自动下载并通过 channel 发送视频文件和封面图
- **主页变更通知**：昵称、签名、IP 归属地等信息变更时实时推送
- **定时自动监控**：通过 `/schedule` 创建定时任务，无需手动触发
- **多 channel 支持**：自动适配 iMessage、Telegram、Discord 等已配置的 channel

## 命令

| 命令 | 说明 |
|------|------|
| `/douyin-homepage-monitor:setup` | 初始化配置，引导填写监控目标和频率，自动创建定时任务 |
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

### 配置 Cookie

> 抖音接口需要登录态，必须配置 Cookie 才能正常工作。

1. 在浏览器打开 [https://www.douyin.com](https://www.douyin.com) 并登录
2. 按 `F12` → Network 标签 → 刷新页面
3. 点击任意请求 → Request Headers → 找到 `cookie` 字段
4. 复制完整的 cookie 值
5. 编辑插件目录下的 `scripts/monitor.py`，将 `COOKIE` 变量替换为复制的值

### 安装 Python 依赖

```bash
pip install requests retrying tqdm
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
- `requests`、`retrying`、`tqdm`
- OpenClaw（含 `/schedule` skill）
