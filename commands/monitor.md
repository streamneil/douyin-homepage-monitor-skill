---
name: monitor
description: 立即执行一次抖音主页监控检测。检查所有已配置用户的主页，将新视频下载并通过 channels 发送通知。
disable-model-invocation: true
allowed-tools:
  - Read
  - Write
  - Bash
---

# /douyin-homepage-monitor:monitor — 立即执行监控

ARGUMENTS: $ARGUMENTS

## 执行步骤

### 步骤 1：读取配置

读取 `.claude/douyin-homepage-monitor.local.md`，解析 YAML frontmatter。

如果文件不存在，提示用户先运行 `/douyin-homepage-monitor:setup`，然后停止。

如果 `enabled: false`，提示用户监控已禁用，停止。

### 步骤 2：找到 plugin 目录

```bash
# 寻找 monitor.py 脚本位置
find . -name "monitor.py" -path "*/douyin-homepage-monitor*/scripts/*" 2>/dev/null | head -1
```

如果找不到，尝试：
```bash
ls scripts/monitor.py 2>/dev/null
```

### 步骤 3：执行监控

从配置中构造 JSON，运行监控脚本。

**构造 JSON 示例**（根据配置中的 targets 动态生成）：
```bash
python3 scripts/monitor.py '{"save_dir":"./Download","targets":[{"label":"刘德华","url":"https://v.douyin.com/xxxxx"}]}'
```

逐行读取输出（JSON Lines 格式），应用 `skills/douyin-homepage-monitor/SKILL.md` 中的通知逻辑。

### 步骤 4：发送通知

对每个 `new_video` 事件：
- 发送文本消息：`{label} 发布了新内容：{title}\n发布时间：{create_time}`
- 发送视频文件（`file_path`）通过 channel 的 files 参数

对每个 `profile_update` 事件：
- 发送文本消息：`{message}`

使用可用的 channel（按优先级：iMessage > Telegram > Discord > 终端输出）。

### 步骤 5：报告结果

在终端输出检测摘要。
