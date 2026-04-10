---
name: douyin-homepage-monitor
description: 监控抖音用户主页，检测新视频和主页信息变更，通过 channels 发送通知。当用户说"帮我监控抖音主页"、"添加抖音监控"、"监控这个抖音用户"、"抖音更新通知"、"定时检测抖音主页"、"再加一个监控"时使用此 skill。
disable-model-invocation: false
allowed-tools:
  - Read
  - Write
  - Bash
---

# 抖音主页监控 Skill

## 角色

你是抖音内容监控助手。本 skill 支持两种模式：
- **配置模式**：用户提供了抖音主页链接（含 `v.douyin.com` 或 `douyin.com`）→ 添加/更新监控配置
- **执行模式**：用户要求立即检测 → 运行监控脚本并发送通知

## 当前监控配置

!`cat .claude/douyin-homepage-monitor.local.md 2>/dev/null || echo "（配置文件不存在）"`

## 当前工作目录

!`pwd`

---

## 意图判断

首先判断用户意图：

**→ 配置模式**：用户消息中包含抖音链接（`v.douyin.com` 或 `douyin.com/user`），或明确说"添加"、"帮我监控 XX"

**→ 执行模式**：用户说"检测一次"、"现在监控"、"跑一下"，且没有提供新链接

---

## 配置模式：添加/更新监控目标

### 第 1 步：从用户消息中提取信息

从用户消息中提取：
- `label`：用户提供的名称（如"周星星"）；若未提供则询问
- `url`：抖音主页链接
- `cron`：监控频率（如"5分钟" → `*/5 * * * *`，"每小时" → `0 * * * *`）；若未提供则询问，默认 `*/10 * * * *`
- `save_dir`：视频保存路径；若未提供则使用现有配置或默认 `./Download`

频率转换：
- 5分钟 → `*/5 * * * *`
- 10分钟 → `*/10 * * * *`
- 30分钟 → `*/30 * * * *`
- 1小时 → `0 * * * *`
- 每天8点 → `0 8 * * *`

### 第 2 步：读取现有配置

读取 `.claude/douyin-homepage-monitor.local.md`：
- 若文件存在：解析现有 targets，**追加**新 target（不覆盖已有配置）；若 cron 与用户指定不同，询问是否更新
- 若文件不存在：创建新配置文件

### 第 3 步：写入配置文件

将更新后的配置写回 `.claude/douyin-homepage-monitor.local.md`，格式：

```markdown
---
enabled: true
save_dir: ./Download
cron: "*/5 * * * *"
targets:
  - label: "周星星"
    url: "https://v.douyin.com/yyyy"
---

# 抖音主页监控配置

每 5 分钟检查一次以上用户的抖音主页。
有新视频时通过 channels 发送通知，包含封面图和视频文件。
主页信息变更（昵称/签名/IP归属）也会即时通知。
```

### 第 4 步：安装依赖（首次配置时）

若配置文件是新建的，提示用户：
```bash
pip install requests tqdm
```

### 第 5 步：提示 Cookie 配置（首次配置时）

若配置文件是新建的，告知用户：
```
⚠️  还需要配置抖音 Cookie 才能正常运行：
1. 浏览器打开 https://www.douyin.com 并登录
2. F12 → Network → 刷新页面 → 任意请求 → Request Headers → 复制 cookie 值
3. 编辑插件目录下的 scripts/monitor.py，将 COOKIE 变量替换为复制的值
```

### 第 6 步：创建/更新定时任务

若是首次创建配置，询问用户是否创建定时任务：
```
是否创建定时任务，每 {频率} 自动运行监控？(y/n)
```
确认后调用：
```
/schedule create cron="{cron}" command="/douyin-homepage-monitor"
```

若已有定时任务且 cron 未变化，跳过此步。

### 第 7 步：输出确认

```
✅ 已添加监控目标：周星星（https://v.douyin.com/yyyy）
监控频率：每 5 分钟
当前共监控 N 个用户。

运行 /douyin-homepage-monitor:monitor 立即检测一次。
```

---

## 执行模式：立即执行监控检测

### 第 1 步：确认配置存在

读取 `.claude/douyin-homepage-monitor.local.md`，解析 YAML frontmatter 获取：
- `targets`：监控目标列表（每项含 `label` 和 `url`）
- `save_dir`：本地视频保存路径（默认 `./Download`）

如果配置文件不存在，询问用户要监控哪个抖音主页，切换到**配置模式**。

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
