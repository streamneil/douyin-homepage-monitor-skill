---
name: status
description: 查看抖音监控的当前状态，包括监控目标、频率、历史记录数量和最近的通知。
disable-model-invocation: true
allowed-tools:
  - Read
  - Bash
---

# /douyin-homepage-monitor:status — 查看监控状态

## 执行步骤

### 步骤 1：读取配置

读取 `.claude/douyin-homepage-monitor.local.md`，如不存在则提示未初始化。

### 步骤 2：统计历史记录

对每个监控目标，计算对应的 `.history` 文件中的视频条数：

```bash
# history 文件命名规则：{md5(url)}-aweme.history
# 统计行数即已记录的视频数
wc -l *.history 2>/dev/null || echo "（暂无历史记录）"
```

### 步骤 3：查看定时任务

```bash
/schedule list
```

过滤出包含 `douyin-homepage-monitor` 的任务。

### 步骤 4：输出状态报告

格式：
```
📊 抖音监控状态
═══════════════════════════════

状态：✅ 运行中 / ⏸️  已暂停

监控目标（共 N 个）：
  ├─ 刘德华
  │    链接：https://v.douyin.com/xxxxx
  │    已记录视频：42 条
  └─ 周杰伦
       链接：https://v.douyin.com/yyyyy
       已记录视频：18 条

监控频率：每 5 分钟
视频保存：./Download/

定时任务：✅ 已创建（ID: xxx）

操作提示：
  /douyin-homepage-monitor:monitor    — 立即执行一次检测
  /douyin-homepage-monitor:setup      — 修改配置
  /douyin-homepage-monitor:pause      — 暂停监控
```
