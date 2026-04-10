---
name: setup
description: 初始化抖音监控配置。引导用户填写要监控的抖音主页链接、自定义名称和监控频率，生成配置文件并安排定时任务。
disable-model-invocation: true
allowed-tools:
  - Read
  - Write
  - Bash
---

# /douyin-homepage-monitor:setup — 初始化监控配置

ARGUMENTS: $ARGUMENTS

## 目标

引导用户完成抖音主页监控的完整配置：
1. 询问要监控的抖音用户信息
2. 询问监控频率
3. 生成 `.claude/douyin-homepage-monitor.local.md` 配置文件
4. 使用 `/schedule` 创建定时任务（每次到点自动运行 `/douyin-homepage-monitor`）
5. 提示安装依赖

## 执行步骤

### 步骤 1：检查现有配置

读取 `.claude/douyin-homepage-monitor.local.md`（如存在），展示当前配置并询问是否覆盖还是追加。

### 步骤 2：收集监控目标

询问用户（可多轮对话）：

```
请告诉我要监控的抖音用户信息（可以一次添加多个）：

1. 用户名称（你给他起的名字，如"刘德华"）
2. 抖音主页链接（在抖音 App → 主页 → 分享 → 复制链接，格式如 https://v.douyin.com/xxxxx）

如果有多个用户，请继续提供。输入"完成"结束。
```

### 步骤 3：收集监控频率

```
请设置监控频率（每隔多久检查一次）：
- 推荐选项：5分钟 / 10分钟 / 30分钟 / 1小时
- 或自定义（如"每天早上8点"）
```

将用户输入转换为 cron 表达式：
- 5分钟 → `*/5 * * * *`
- 10分钟 → `*/10 * * * *`
- 30分钟 → `*/30 * * * *`
- 1小时 → `0 * * * *`
- 每天8点 → `0 8 * * *`

### 步骤 4：询问视频保存路径

```
视频文件保存路径（直接回车使用默认 ./Download/）：
```

默认值：`./Download`

### 步骤 5：写入配置文件

创建 `.claude/douyin-homepage-monitor.local.md`：

```markdown
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

# 抖音主页监控配置

每 5 分钟检查一次以上用户的抖音主页。
有新视频时通过 channels 发送通知，包含封面图和视频文件。
主页信息变更（昵称/签名/IP归属）也会即时通知。
```

### 步骤 6：安装依赖

```bash
pip install requests retrying tqdm
```

### 步骤 7：提示 Cookie 配置

告知用户：
```
⚠️  重要：需要更新抖音 Cookie 才能正常工作。

步骤：
1. 在浏览器打开 https://www.douyin.com 并登录
2. 按 F12 → Network 标签 → 刷新页面
3. 点击任意请求 → Request Headers → 找到 "cookie" 字段
4. 复制完整的 cookie 值
5. 编辑 <plugin目录>/scripts/monitor.py
6. 将第 30 行左右的 COOKIE 变量替换为你复制的值
```

### 步骤 8：创建定时任务

使用 `/schedule` skill 安排定时监控（如果用户确认）：

```
我将为你创建一个定时任务，每 {频率} 自动运行抖音监控。
确认创建？(y/n)
```

确认后，调用：
```
/schedule create cron="{cron_expression}" command="/douyin-homepage-monitor"
```

### 步骤 9：配置完成

输出配置摘要：
```
✅ 抖音监控配置完成！

监控目标：
  - 刘德华 → https://v.douyin.com/xxxxx
  - 周杰伦 → https://v.douyin.com/yyyyy

监控频率：每 5 分钟
视频保存：./Download/

已创建定时任务。

⚠️  别忘了更新 scripts/monitor.py 中的 Cookie！

手动测试命令：
  /douyin-homepage-monitor
```
