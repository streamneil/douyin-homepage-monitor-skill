---
name: pause
description: 暂停抖音主页监控（将 enabled 改为 false）。
disable-model-invocation: true
allowed-tools:
  - Read
  - Write
  - Bash
---

# /douyin-homepage-monitor:pause — 暂停监控

## 执行步骤

1. 读取 `.claude/douyin-homepage-monitor.local.md`
2. 将 `enabled: true` 改为 `enabled: false`
3. 原子写回文件
4. 输出：`⏸️  抖音监控已暂停。运行 /douyin-homepage-monitor:resume 恢复。`

**注意**：暂停只是让 skill 跳过执行，定时任务仍在运行但不会做任何事。
如需彻底停止定时任务，运行 `/schedule delete <task-id>`。
