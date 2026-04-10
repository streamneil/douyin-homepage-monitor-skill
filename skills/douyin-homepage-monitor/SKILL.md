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
- **配置模式**：用户提供了抖音主页链接（含 `v.douyin.com` 或 `douyin.com`）→ 添加监控并执行首次全量抓取
- **执行模式**：用户要求立即检测 → 运行增量监控脚本并发送通知

## 当前监控配置

!`cat .claude/douyin-homepage-monitor.local.md 2>/dev/null || echo "（配置文件不存在）"`

## Plugin 安装目录

!`dirname $(dirname $(realpath ${CLAUDE_SKILL_PATH:-./skills/douyin-homepage-monitor/SKILL.md})) 2>/dev/null || pwd`

## 当前工作目录

!`pwd`

---

## 意图判断

首先判断用户意图：

**→ 配置模式**：用户消息中包含抖音链接（`v.douyin.com` 或 `douyin.com/user`），或明确说"添加"、"帮我监控 XX"

**→ 执行模式**：用户说"检测一次"、"现在监控"、"跑一下"，且没有提供新链接

---

## 配置模式：添加监控目标（首次全量抓取）

### 第 1 步：从用户消息中提取信息

从用户消息中提取：
- `label`：用户提供的名称（如"WP"）；若未提供则询问
- `url`：抖音主页链接（从消息中提取完整的 `https://v.douyin.com/...` 部分，忽略分享文案中的其他内容）
- `cron`：监控频率；**若未提供，默认使用 `*/5 * * * *`（5分钟）**，无需询问，直接告知用户

频率转换（最低 2 分钟）：
- 2分钟 → `*/2 * * * *`（最低限制）
- 5分钟 → `*/5 * * * *`（默认）
- 10分钟 → `*/10 * * * *`
- 30分钟 → `*/30 * * * *`
- 1小时 → `0 * * * *`

若用户要求低于 2 分钟，告知最低为 2 分钟，使用 `*/2 * * * *`。

### 第 2 步：确定 Plugin 目录和 save_dir

从上方 "Plugin 安装目录" 输出中获取 `PLUGIN_DIR`，设置：
```
save_dir = {PLUGIN_DIR}/Download
```

这确保视频总是保存在 plugin 目录下的 `Download/` 文件夹，而非用户当前项目目录。

### 第 3 步：读取现有配置，追加新目标

读取 `.claude/douyin-homepage-monitor.local.md`：
- 若文件存在：解析现有 targets，**追加**新 target，保持已有配置不变
- 若文件不存在：创建新配置文件

写入格式：
```markdown
---
enabled: true
save_dir: {PLUGIN_DIR}/Download
cron: "*/5 * * * *"
targets:
  - label: "WP"
    url: "https://v.douyin.com/xxx"
---

# 抖音主页监控配置

每 5 分钟检查一次以上用户的抖音主页。
有新视频时通过 channels 发送通知，包含封面图和视频文件。
主页信息变更（昵称/签名/IP归属）也会即时通知。
```

### 第 4 步：首次初始化 — 全量抓取并下载所有历史视频

告知用户："正在初始化，全量抓取历史视频，请稍候..."

运行初始化脚本（`--init` 模式）：

```bash
PLUGIN_DIR=$(dirname $(dirname $(realpath ${CLAUDE_SKILL_PATH:-./skills/douyin-homepage-monitor/SKILL.md})))
cd "$PLUGIN_DIR"
python3 scripts/monitor.py --init '{"save_dir":"{save_dir}","targets":[{"label":"{label}","url":"{url}"}]}'
```

### 第 5 步：解析 init_complete 事件

脚本会输出 JSON Lines，处理以下事件类型：

#### 事件：`error`（code: cookie_invalid）

```json
{
  "type": "error",
  "code": "cookie_invalid",
  "message": "..."
}
```

**立即告知用户**：
```
⚠️  Cookie 未配置或已失效！

未登录状态下，抖音 API 只返回部分数据（通常仅第一页约 10 条），
导致无法获取完整的作品列表。

请按以下步骤更新 Cookie：
1. 浏览器打开 https://www.douyin.com 并登录账号
2. 按 F12 → Network 标签 → 刷新页面
3. 点击任意请求 → Request Headers → 找到 "cookie" 字段
4. 复制完整的 cookie 值（很长的一串）
5. 编辑 {PLUGIN_DIR}/scripts/monitor.py
6. 将文件中的 COOKIE 变量（约第 25 行）替换为复制的值
7. 保存后重新运行此命令

更新 Cookie 后，重新运行：帮我监控 {label} {url}
```

**仍继续**处理后续事件（脚本会继续尝试）。

#### 事件：`init_complete`

```json
{
  "type": "init_complete",
  "label": "WP",
  "nickname": "实际昵称",
  "signature": "个人签名",
  "ip_location": "浙江",
  "save_dir": "/path/to/Download/实际昵称",
  "total_videos": 10,
  "downloaded": 9,
  "failed": 1,
  "video_list": [
    {"title": "视频标题", "create_time": "2024-01-01 10:00:00", "file_path": "..."}
  ],
  "login_warning": false
}
```

**展示摘要**（作品数量多时只展示前 5 条，其余折叠提示）：

```
✅ 已添加监控：{label}（{nickname}）

📍 IP 属地：{ip_location}
📁 视频保存路径：{save_dir}
📹 历史作品：共 {total_videos} 条，已下载 {downloaded} 条

最新作品（最近 5 条）：
1. {video_list[-1].title}（{video_list[-1].create_time}）
2. ...
...

（共 {total_videos} 条，其余已下载到本地）

---
我将每 {频率} 第一时间通知你 {label} 的新动态。
```

若 `total_videos` <= 5，展示全部。

若 `login_warning: true`，在摘要末尾追加 Cookie 提示。

### 第 6 步：提示安装依赖（首次配置时）

若配置文件是新建的：
```
提示：如未安装依赖，请运行：pip install requests tqdm
```

### 第 7 步：创建定时任务

直接创建，无需询问用户确认：
```
/schedule create cron="{cron}" command="/douyin-homepage-monitor"
```

若已有同名定时任务且 cron 未变，跳过。

---

## 执行模式：增量监控检测

### 第 1 步：确认配置存在

读取 `.claude/douyin-homepage-monitor.local.md`，解析 YAML frontmatter。

如果配置文件不存在，询问用户要监控哪个抖音主页，切换到**配置模式**。

如果 `enabled: false`，提示用户运行 `/douyin-homepage-monitor:resume` 恢复。

### 第 2 步：运行增量监控脚本

```bash
PLUGIN_DIR=$(dirname $(dirname $(realpath ${CLAUDE_SKILL_PATH:-./skills/douyin-homepage-monitor/SKILL.md})))
cd "$PLUGIN_DIR"
python3 scripts/monitor.py '<CONFIG_JSON>'
```

其中 `<CONFIG_JSON>` 格式（save_dir 使用绝对路径）：
```json
{
  "save_dir": "{PLUGIN_DIR}/Download",
  "targets": [
    {"label": "WP", "url": "https://v.douyin.com/xxx"}
  ]
}
```

### 第 3 步：解析事件并通知

逐行解析脚本输出：

#### 事件：`error`（code: cookie_invalid）

提示用户更新 Cookie（同配置模式第 5 步的提示内容）。

#### 事件：`new_video`

```json
{
  "type": "new_video",
  "label": "WP",
  "nickname": "实际昵称",
  "title": "视频标题",
  "create_time": "2024-05-10 20:00:00",
  "cover_url": "https://...",
  "file_path": "/path/to/Download/昵称/[2024-05-10 20:00:00] 视频标题.mp4",
  "message": "WP 发布了新视频：视频标题（2024-05-10 20:00:00）"
}
```

**通知格式：**
- 文本消息：`{label} 发布了新内容：{title}\n发布时间：{create_time}`
- 附件 1：封面图（`cover_url`）
- 附件 2：视频文件（`file_path`，本地 mp4 文件）

**发送方式（按优先级）：**

如果有 iMessage channel：
```
reply 工具：text + files: ["{file_path}"]
```

如果有 Telegram channel：
```
send_message 工具：text + files: ["{file_path}"]
```

如果有 Discord channel：使用对应工具发送附件。

如果没有任何 channel：在终端输出通知内容并显示文件路径。

#### 事件：`profile_update`

```json
{
  "type": "profile_update",
  "label": "WP",
  "changes": ["昵称: 旧名 → 新名"],
  "message": "WP 更新了主页信息：昵称: 旧名 → 新名"
}
```

发送纯文本通知：`{message}`

### 第 4 步：输出摘要

```
检测完成：
- 检测了 N 个主页
- 发现 X 条新视频
- 主页信息变更：有/无
```

---

## 注意事项

- `file_path` 为空字符串时，说明下载失败，仅发送文本+封面图通知
- **Cookie 失效是最常见问题**，会导致 API 只返回第一页数据（约 10 条），不是 "懒加载" 问题
- `save_dir` 必须使用 plugin 目录的绝对路径，而非相对路径
- 历史记录文件（`*.history`）存储在 plugin 安装目录下，不要删除
- 首次 `--init` 后，后续定时调用无需 `--init`，只做增量检测
