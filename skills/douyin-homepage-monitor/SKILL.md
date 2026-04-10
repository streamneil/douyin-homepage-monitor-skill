---
name: douyin-homepage-monitor
description: 监控抖音用户主页，检测新视频和主页信息变更，通过 channels 发送通知。当用户要求"监控抖音"、"抖音更新通知"、"定时检测抖音主页"时使用此 skill。
disable-model-invocation: false
allowed-tools:
  - Read
  - Write
  - Bash
---

# 抖音主页监控 Skill

## 角色

你是抖音内容监控助手。本 skill 负责：
1. 读取用户的监控配置（`.claude/douyin-homepage-monitor.local.md`）
2. 调用 `scripts/monitor.py` 执行一轮检测
3. 解析脚本输出，通过可用的 channel 发送通知

## 当前监控配置

!`cat .claude/douyin-homepage-monitor.local.md 2>/dev/null || echo "（配置文件不存在，请先运行 /douyin-homepage-monitor:setup）"`

## 当前工作目录

!`pwd`

## 执行步骤

### 第 1 步：确认配置存在

读取 `.claude/douyin-homepage-monitor.local.md`，解析 YAML frontmatter 获取：
- `targets`：监控目标列表（每项含 `label` 和 `url`）
- `save_dir`：本地视频保存路径（默认 `./Download`）

如果配置文件不存在，告知用户运行 `/douyin-homepage-monitor:setup` 完成初始化，然后停止。

### 第 2 步：运行监控脚本

构造 JSON 配置并运行：

```bash
PLUGIN_DIR=$(dirname $(dirname $(realpath ${CLAUDE_SKILL_PATH:-./skills/douyin-homepage-monitor/SKILL.md})))
cd "$PLUGIN_DIR"
python3 scripts/monitor.py '<CONFIG_JSON>'
```

其中 `<CONFIG_JSON>` 格式：
```json
{
  "save_dir": "<save_dir from config>",
  "targets": [
    {"label": "刘德华", "url": "https://v.douyin.com/xxxxx"}
  ]
}
```

脚本以 JSON Lines 格式输出到 stdout，每行一个事件。

### 第 3 步：解析事件并通知

逐行解析脚本输出，对每个事件：

#### 事件类型：`new_video`

```json
{
  "type": "new_video",
  "label": "刘德华",
  "nickname": "刘德华官方",
  "title": "新歌MV",
  "create_time": "2024-05-10 20:00:00",
  "cover_url": "https://...",
  "file_path": "./Download/刘德华官方/[2024-05-10 20:00:00] 新歌MV.mp4",
  "message": "刘德华 发布了新视频：新歌MV（2024-05-10 20:00:00）"
}
```

**通知格式：**
- 文本消息：`{label} 发布了新内容：{title}（{create_time}）`
- 附件 1：封面图（`cover_url`，通过 URL 发送）
- 附件 2：视频文件（`file_path`，通过 channels 的 `files` 参数发送本地文件）

**发送方式（通过可用 channel）：**

如果有 iMessage channel：
```
使用 reply 工具发送到用户配置的 chat_id：
- text: "{label} 发布了新内容：{title}\n发布时间：{create_time}"
- files: ["{file_path}"]  // 本地 mp4 文件路径
```

如果有 Telegram channel：
```
使用 send_message 工具：
- text: "{label} 发布了新内容：{title}\n发布时间：{create_time}"
- files: ["{file_path}"]
```

如果有 Discord channel：
```
使用对应工具发送，附上文件
```

如果没有任何 channel，在终端输出通知内容并显示文件路径。

#### 事件类型：`profile_update`

```json
{
  "type": "profile_update",
  "label": "刘德华",
  "nickname": "刘德华官方v2",
  "changes": ["昵称: 刘德华官方 → 刘德华官方v2"],
  "message": "刘德华 更新了主页信息：昵称: 刘德华官方 → 刘德华官方v2"
}
```

**通知格式（纯文本）：**
```
{label} 更新了主页信息：
{changes[0]}
{changes[1]}
...
```

### 第 4 步：输出摘要

完成后报告：
- 检测了哪些主页
- 发现了多少条新视频
- 是否有主页信息变更
- 是否有通知发送失败

## 注意事项

- `file_path` 为空字符串时，说明下载失败，仅发送文本+封面图通知
- `save_dir` 路径相对于 plugin 安装目录
- Cookie 失效会导致脚本无输出或报错，提醒用户更新 `scripts/monitor.py` 中的 `COOKIE` 变量
- 历史记录文件（`*.history`）存储在 plugin 安装目录下，不要删除
