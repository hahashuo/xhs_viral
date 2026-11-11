---
description: 发布最新定稿。模式 B 导出手机发布包；模式 A 经你确认后自动发布
argument-hint: [草稿文件夹名，可省略]
---

草稿：$ARGUMENTS（为空则用 drafts/ 里最新的一篇）

1. 读 `harness.toml` 的 `publish_mode`。
2. 运行 `python -m harness check <草稿> --mode <模式>`。不通过就停下，列出问题并提出修改方案。

**模式 B（默认）**
3. 运行 `python -m harness export <草稿>`，告诉用户发布包路径，以及：把文件夹里的图片和文字传到手机（微信文件传输助手、AirDrop、云盘都可以），在手机小红书 App 里发布，勾选「AI 辅助创作」。
4. 提醒用户发完后运行 `/published`。

**模式 A**
3. 先确认 xiaohongshu-mcp 已连接（`check_login_status`）。没连接就告诉用户按 README 的「模式 A 设置」启动，然后停下。
4. 把将要发布的内容完整展示：标题、正文、标签、图片的绝对路径列表。问用户「确认发布吗？」，然后停下。
5. 只有用户这一次明确回答确认后，调用 `publish_content`：`title`、`content`（正文 + 空行 + 标签行）、`images`（本地绝对路径）、`tags`。标签里必须有「AI辅助创作」。
6. 成功后运行 `python -m harness published <草稿> --mode A --url <返回的链接，如有>`。
