---
name: resume
description: 恢复已暂停的抖音主页监控（将 enabled 改回 true）。
disable-model-invocation: true
allowed-tools:
  - Read
  - Write
  - Bash
---

# /douyin-homepage-monitor:resume — 恢复监控

## 执行步骤

1. 读取 `.claude/douyin-homepage-monitor.local.md`
2. 将 `enabled: false` 改为 `enabled: true`
3. 原子写回文件
4. 输出：`✅ 抖音监控已恢复运行。`
