---
description: 切换发布模式：A 审批后自动发布，B 只生成由你手动发
argument-hint: A | B
---

参数：$ARGUMENTS

- 没有参数：显示当前模式和两种模式的区别。
- `A` 或 `B`：修改 `harness.toml` 的 `publish_mode`。切到 A 时提醒：新号建议先用 B 跑两周；需要先按 README 设置 xiaohongshu-mcp；每次发布前仍会请你确认。
