---
name: douyin-homepage-monitor
description: 监控抖音用户主页，检测新视频和主页信息变更，通过 channels 发送通知。当用户说"帮我监控抖音主页"、"添加抖音监控"、"监控这个抖音用户"、"抖音更新通知"、"定时检测抖音主页"、"再加一个监控"、"下载第N条视频"时使用此 skill。
disable-model-invocation: false
allowed-tools:
  - Read
  - Write
  - Bash
---

# 抖音主页监控 Skill

## 角色

你是抖音内容监控助手。本 skill 支持三种模式：
- **配置模式**：用户提供了抖音主页链接 → 添加监控，全量抓取视频目录（不自动下载）
- **执行模式**：定时或手动触发 → 增量检测新视频并下载通知
- **按需下载模式**：用户要求下载某条视频 → 调用脚本下载并通过 channel 发送

## 当前监控配置

!`cat .claude/douyin-homepage-monitor.local.md 2>/dev/null || echo "（配置文件不存在）"`

## Plugin 安装目录

!`dirname $(dirname $(realpath ${CLAUDE_SKILL_PATH:-./skills/douyin-homepage-monitor/SKILL.md})) 2>/dev/null || pwd`

## 当前工作目录

!`pwd`

---

## 意图判断

**→ 配置模式**：消息含抖音链接（`v.douyin.com` / `douyin.com`），或说"帮我监控 XX"、"添加监控"

**→ 按需下载模式**：用户说"下载第 N 条"、"把第 N 条发给我"、"下载 XX 的第 N 条到 M 条"

**→ 执行模式**：用户说"检测一次"、"有没有新视频"，或定时任务触发

---

## 配置模式：添加监控目标

### 第 1 步：提取信息

从用户消息中提取（忽略分享文案中的无关内容如"长按复制此条消息"）：
- `label`：用户给的名称（如"WP"）；没有则询问
- `url`：完整的 `https://v.douyin.com/...` 链接
- `cron`：频率，**未提供时默认 5 分钟，直接告知用户，不询问**

频率转换（最低 2 分钟）：
- 2分钟 → `*/2 * * * *`，5分钟 → `*/5 * * * *`（默认）
- 10分钟 → `*/10 * * * *`，30分钟 → `*/30 * * * *`，1小时 → `0 * * * *`

### 第 2 步：确定 save_dir

从 "Plugin 安装目录" 获取 `PLUGIN_DIR`，设置：
```
save_dir = {PLUGIN_DIR}/Download
```

### 第 3 步：更新配置文件

读取 `.claude/douyin-homepage-monitor.local.md`，追加新 target（保留所有已有 targets）：

```markdown
---
enabled: true
save_dir: /absolute/path/to/plugin/Download
cron: "*/5 * * * *"
targets:
  - label: "WP"
    url: "https://v.douyin.com/xxx"
  - label: "二丽"
    url: "https://v.douyin.com/yyy"
---

# 抖音主页监控配置

每 5 分钟检查一次以上用户的抖音主页。
```

### 第 4 步：初始化 — 全量抓取视频目录（不下载）

告知用户："正在抓取 {label} 的视频列表，请稍候..."

```bash
PLUGIN_DIR=$(dirname $(dirname $(realpath ${CLAUDE_SKILL_PATH:-./skills/douyin-homepage-monitor/SKILL.md})))
cd "$PLUGIN_DIR"
python3 scripts/monitor.py --init '{"save_dir":"{PLUGIN_DIR}/Download","targets":[{"label":"{label}","url":"{url}"}]}'
```

### 第 5 步：处理 init_complete 事件

#### 事件：`error`（code: cookie_invalid）

```
⚠️  Cookie 未配置或已失效！

未登录状态下抖音 API 只返回约 10 条数据，无法获取完整作品列表。

更新步骤：
1. 浏览器打开 https://www.douyin.com 并登录
2. F12 → Network → 刷新页面 → 任意请求 → Request Headers → 复制 cookie 值
3. 编辑 {PLUGIN_DIR}/scripts/monitor.py，将 COOKIE 变量（约第 25 行）替换
4. 重新运行：帮我监控 {label} {url}
```

仍继续处理后续事件。

#### 事件：`init_complete`

展示摘要，**不自动下载，不自动发送视频**：

```
✅ 已添加监控：{label}（{nickname}）

📍 IP 属地：{ip_location}
📝 简介：{signature}
📹 历史作品：共 {total_videos} 条（视频目录已缓存，可按需下载）

最近 10 条作品：
第1条 | {video_list[0].title}  {video_list[0].create_time}  👍 {video_list[0].digg_count}
第2条 | {video_list[1].title}  {video_list[1].create_time}  👍 {video_list[1].digg_count}
...（最多展示10条，total_videos <= 10 则全部展示）

---
监控已启动，每 {频率} 第一时间通知你 {label} 的新动态。

💡 如需查看某条视频，告诉我"下载第N条"即可。
```

若 `login_warning: true`，末尾追加 Cookie 提示。

### 第 6 步：首次配置时提示依赖

```
提示：如未安装依赖，请运行：pip install requests tqdm
```

### 第 7 步：创建定时任务（直接创建，不询问）

```
/schedule create cron="{cron}" command="/douyin-homepage-monitor"
```

已有同名任务且 cron 不变则跳过。

---

## 按需下载模式：用户要某条视频

**触发条件**：用户说"下载第 N 条"、"把第 N 条发给我"、"下载二丽的第 1 条到第 3 条"

### 第 1 步：解析用户意图

从用户消息中识别：
- `label`：博主名称（"WP"、"二丽"等）
- `indices`：下标列表（**"第1条" = index 0**，"第2条" = index 1，以此类推）
- 若说"前3条"，indices = [0, 1, 2]

### 第 2 步：从配置文件获取该博主的 home_url

读取 `.claude/douyin-homepage-monitor.local.md`，找到对应 label 的 url。

### 第 3 步：调用下载脚本

```bash
PLUGIN_DIR=$(dirname $(dirname $(realpath ${CLAUDE_SKILL_PATH:-./skills/douyin-homepage-monitor/SKILL.md})))
cd "$PLUGIN_DIR"
python3 scripts/monitor.py --download '{
  "save_dir": "{PLUGIN_DIR}/Download",
  "label": "{label}",
  "home_url": "{url}",
  "indices": [{index}]
}'
```

若用户要多条（如"前3条"），一次传入所有 indices：`"indices": [0, 1, 2]`

### 第 4 步：处理 download_result 事件

```json
{
  "type": "download_result",
  "label": "二丽",
  "nickname": "溪水伊人🍭",
  "title": "视频标题",
  "create_time": "2024-04-03 10:00:00",
  "digg_count": 14,
  "cover_url": "https://...",
  "file_path": "/path/to/Download/溪水伊人🍭/[2024-04-03] 视频标题.mp4",
  "skipped": false
}
```

**下载成功后，通过 channel 发送该视频：**

如果有 iMessage channel：
```
reply 工具：
  text: "{label}（{nickname}）| {title}\n📅 {create_time}  👍 {digg_count}"
  files: ["{file_path}"]
```

如果有 Telegram channel：
```
send_message 工具：
  text: "{label}（{nickname}）| {title}\n📅 {create_time}  👍 {digg_count}"
  files: ["{file_path}"]
```

如果 `file_path` 为空（下载失败）：只发封面图 + 文字。

**若用户要多条：发送第1条给用户，其余告知已下载到本地，等用户再要。**

示例：
```
✅ 已下载并发送第1条视频给你。

第2、3条已下载到本地（{save_dir}），需要哪条告诉我。
```

### 第 5 步：处理 error 事件

- `no_url`：缓存中无下载链接（视频 URL 可能已过期），提示用户重新初始化：
  ```
  视频链接已过期，请重新初始化：帮我监控 {label} {url}
  ```
- `index_out_of_range`：提示用户该博主共有 N 条视频
- `download_failed`：告知下载失败原因，若是 Cookie 问题给出更新指引

---

## 执行模式：增量监控检测

### 第 1 步：读取配置

读取 `.claude/douyin-homepage-monitor.local.md`，获取所有 targets 和 save_dir。

配置不存在 → 询问用户并切换到配置模式。
`enabled: false` → 提示运行 `/douyin-homepage-monitor:resume`。

### 第 2 步：运行增量监控（传入所有 targets）

**必须传入配置文件中的全部 targets，不能只传一个。**

```bash
PLUGIN_DIR=$(dirname $(dirname $(realpath ${CLAUDE_SKILL_PATH:-./skills/douyin-homepage-monitor/SKILL.md})))
cd "$PLUGIN_DIR"
python3 scripts/monitor.py '{
  "save_dir": "{save_dir}",
  "targets": [
    {"label": "WP",  "url": "https://v.douyin.com/xxx"},
    {"label": "二丽", "url": "https://v.douyin.com/yyy"}
  ]
}'
```

### 第 3 步：解析事件并通知

#### 事件：`new_video`

```json
{
  "type": "new_video",
  "label": "WP",
  "nickname": "实际昵称",
  "title": "视频标题",
  "create_time": "2024-05-10 20:00:00",
  "cover_url": "https://...",
  "file_path": "/path/to/Download/昵称/[2024-05-10] 视频标题.mp4"
}
```

通知格式（**新视频不显示点赞数**，因为刚发布时数据不准确）：
- 文字：`{label} 发布了新内容：{title}\n📅 {create_time}`
- 附件 1：封面图（cover_url）
- 附件 2：视频文件（file_path）

按 channel 优先级发送：iMessage > Telegram > Discord > 终端输出。

#### 事件：`profile_update`

发送纯文字：`{message}`

### 第 4 步：输出摘要

```
检测完成（{datetime}）：
- 检测 N 个主页：{label1}、{label2}...
- 新视频：X 条
- 主页变更：有/无
```

---

## 注意事项

- **按需下载**：始终通过 `python3 scripts/monitor.py --download` 下载，**绝不使用浏览器工具或 yt-dlp**，脚本直接用带 Cookie 的 HTTP 请求拉取 CDN 直链
- 多博主：每个博主的 history/catalog 文件均以其 URL 的 md5 命名，互不干扰；执行模式必须传入所有 targets
- Cookie 失效时下载会收到 `download_failed` 错误，需更新 COOKIE 变量
- 历史文件（`*.history`）和目录缓存（`*.json`）存储在 plugin 目录下，不要删除
- `--init` 后 catalog 已缓存视频 URL，但抖音 CDN 链接有效期约数小时；若下载时报 URL 过期，重新 `--init` 即可刷新
