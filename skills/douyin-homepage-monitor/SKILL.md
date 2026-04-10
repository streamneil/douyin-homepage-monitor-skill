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
- `url`：抖音主页链接（从消息中提取完整的 `https://v.douyin.com/...` 部分，忽略分享文案中的其他内容，如"长按复制此条消息"等）
- `cron`：监控频率；**若未提供，默认使用 `*/5 * * * *`（5分钟），无需询问，直接告知用户**

频率转换（最低 2 分钟）：
- 2分钟 → `*/2 * * * *`（最低限制）
- 5分钟 → `*/5 * * * *`（默认）
- 10分钟 → `*/10 * * * *`
- 30分钟 → `*/30 * * * *`
- 1小时 → `0 * * * *`

若用户要求低于 2 分钟，告知最低为 2 分钟，使用 `*/2 * * * *`。

### 第 2 步：确定 Plugin 目录和 save_dir

从上方 "Plugin 安装目录" 输出中获取 `PLUGIN_DIR`（绝对路径），设置：
```
save_dir = {PLUGIN_DIR}/Download
```

### 第 3 步：读取现有配置，追加新目标

读取 `.claude/douyin-homepage-monitor.local.md`：
- 若文件存在：解析 YAML frontmatter，将新 target 追加到 `targets` 列表末尾，**保持已有所有 targets 不变**
- 若文件不存在：创建新配置文件

写入格式：
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
有新视频时通过 channels 发送通知，包含封面图和视频文件。
主页信息变更（昵称/签名/IP归属）也会即时通知。
```

### 第 4 步：首次初始化 — 全量抓取并下载历史视频

**直接开始，不询问用户是否下载。** 先告知用户：
```
正在初始化 {label} 的监控，全量抓取历史视频中，请稍候...
```

运行初始化脚本（`--init` 模式，只针对**新添加的这一个** target）：

```bash
PLUGIN_DIR=$(dirname $(dirname $(realpath ${CLAUDE_SKILL_PATH:-./skills/douyin-homepage-monitor/SKILL.md})))
cd "$PLUGIN_DIR"
python3 scripts/monitor.py --init '{"save_dir":"{PLUGIN_DIR}/Download","targets":[{"label":"{label}","url":"{url}"}]}'
```

### 第 5 步：解析脚本输出并处理事件

#### 事件：`error`（code: cookie_invalid）

立即告知用户：
```
⚠️  Cookie 未配置或已失效！

未登录状态下，抖音 API 只返回部分数据（通常仅约 10 条），无法获取完整作品列表。

请按以下步骤更新 Cookie：
1. 浏览器打开 https://www.douyin.com 并登录账号
2. 按 F12 → Network 标签 → 刷新页面
3. 点击任意请求 → Request Headers → 找到 "cookie" 字段
4. 复制完整的 cookie 值
5. 编辑 {PLUGIN_DIR}/scripts/monitor.py，将 COOKIE 变量（约第 25 行）替换为复制的值
6. 保存后重新运行：帮我监控 {label} {url}
```

仍继续处理后续事件。

#### 事件：`init_complete`

收到此事件后，执行以下两个动作：

**动作 A：展示摘要**

```
✅ 已添加监控：{label}（{nickname}）

📍 IP 属地：{ip_location}
📁 视频已下载至：{save_dir}
📹 历史作品：共 {total_videos} 条，已下载 {downloaded} 条

最近 10 条作品：
1. {video_list[0].title}（{video_list[0].create_time}）👍 {video_list[0].digg_count}
2. {video_list[1].title}（{video_list[1].create_time}）👍 {video_list[1].digg_count}
...（最多展示10条）

---
监控已启动，每 {频率} 第一时间通知你 {label} 的新动态。
```

若 `total_videos` <= 10，展示全部；若 `login_warning: true`，追加 Cookie 提示。

**动作 B：通过 channel 发送最近 10 条视频（直接发送，不询问用户）**

取 `video_list` 前 10 条（已按发布时间从新到旧排序），逐条发送：

对于每条视频（`file_path` 非空时）：

如果有 iMessage channel：
```
reply 工具：
  text: "{label}（{nickname}）的作品：{title}\n发布时间：{create_time}\n👍 {digg_count}"
  files: ["{file_path}"]
```

如果有 Telegram channel：
```
send_message 工具：
  text: "{label}（{nickname}）的作品：{title}\n发布时间：{create_time}\n👍 {digg_count}"
  files: ["{file_path}"]
```

如果有 Discord channel：使用对应工具发送附件。

如果 `file_path` 为空（下载失败）：只发 cover_url 封面图 + 文字，不发视频文件。

如果没有任何 channel：在终端列出文件路径清单。

### 第 6 步：提示安装依赖（首次配置时）

若配置文件是新建的：
```
提示：如未安装依赖，请运行：pip install requests tqdm
```

### 第 7 步：创建定时任务（直接创建，不询问）

```
/schedule create cron="{cron}" command="/douyin-homepage-monitor"
```

若已有同名定时任务且 cron 未变，跳过。

---

## 执行模式：增量监控检测

### 第 1 步：确认配置存在并读取所有 targets

读取 `.claude/douyin-homepage-monitor.local.md`，解析 YAML frontmatter，获取：
- `targets`：**完整列表**，包含所有已配置的博主（不能只取一个）
- `save_dir`：视频保存根目录
- `enabled`：若为 false，提示用户运行 `/douyin-homepage-monitor:resume` 恢复

如果配置文件不存在，询问用户要监控哪个抖音主页，切换到**配置模式**。

### 第 2 步：运行增量监控脚本（传入所有 targets）

**必须把配置文件中的所有 targets 都传入，不能只传一个。**

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

JSON 中的 targets 数组必须包含配置文件里 **所有** targets，每个都有独立的历史文件（以 URL 的 md5 命名），互不干扰。

### 第 3 步：解析事件并通知

#### 事件：`error`（code: cookie_invalid）

提示用户更新 Cookie（见配置模式第 5 步）。

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

**通知格式（新视频不显示点赞数，因为刚发布数据不准确）：**
- 文字：`{label} 发布了新内容：{title}\n发布时间：{create_time}`
- 附件 1：封面图（`cover_url`）
- 附件 2：视频文件（`file_path`）

发送方式同配置模式动作 B，按 channel 优先级发送。

#### 事件：`profile_update`

发送纯文本：`{message}`

### 第 4 步：输出摘要

```
检测完成（{datetime}）：
- 共检测 N 个主页：{label1}、{label2}...
- 发现新视频：X 条
- 主页信息变更：有/无
```

---

## 注意事项

- **多博主监控**：每个博主的历史文件以其 URL 的 md5 命名，完全独立，不会互相影响。执行模式必须传入所有 targets，否则未传入的博主本次不会被检测。
- `file_path` 为空字符串时，说明下载失败，仅发送文字+封面图
- **Cookie 失效**是获取数据不完整的最常见原因，会导致 API 只返回约 10 条
- `save_dir` 必须使用 plugin 目录的绝对路径
- 历史记录文件（`*.history`）存储在 plugin 安装目录下，不要删除
- 首次 `--init` 后，后续定时调用无需 `--init`，只做增量检测
- **首次添加监控时，无需用户确认，直接下载视频并发送到 channel**
