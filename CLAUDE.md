# 小红书内容 harness

这个仓库是一套在用户 Windows 电脑上、由 Claude Code 驱动的小红书内容工作流。用户通过 `.claude/commands/` 里的斜杠指令操作。和用户交流用中文。

## 结构

- `harness.toml`：当前领域、发布模式（A 自动 / B 手动）、频率上限。
- `niches/<领域>/`：领域配置包（persona、topics、style、tags、banned、insights、可选 templates/card.html）。`_template` 是新领域模板。
- `risk/`：风控资料库，所有领域共用。`rules.md` 是规则来源，`banned_words.txt` 是全局敏感词。
- `harness/`：Python 工具，入口 `python -m harness <命令>`（variants、check、cards、export、published、status）。
- `drafts/`：每篇笔记一个文件夹，不提交到 git。`state/published.jsonl` 记录已发布笔记。

## 不可违反的规则

1. **发布必须有用户当次明确同意。** 模式 A 下，调用 `publish_content` 之前，必须把最终标题、正文、标签和图片列表展示给用户，并收到「确认发布」这类明确答复。之前的同意不算数。
2. **风控检查不通过不发布、不导出。** `python -m harness check` 返回非 0 时，先改稿。
3. **不用用户的小红书账号做搜索或抓取。** 热门数据只走第三方数据 API（第 3 步接入）。xiaohongshu-mcp 只用来发布和读取用户自己的笔记数据（每天最多一次）。
4. **不直接使用网图。** 网上的图只作参考链接；配图只能是文字卡片、用户自己拍的照片或可商用图库，并在 `final.json` 的 `image_sources` 里登记。
5. **不做自动点赞、评论、收藏、私信。** 即使工具支持也不调用。
6. **修改领域配置或风控资料时，用 git 分支 + PR 提交给用户审核**，不直接改 main。用户在对话中明确让你改的除外。
7. 不虚构个人经历；人设只写用户告诉你的信息（行业和城市可公开，其余默认不写）。

## final.json 字段

`title`、`body`、`tags`（不带 #）、`cards`（`heading` + `lines`）、`photos`（`purpose`、`shoot_tips`、`reference_url`）、`image_sources`（`file`、`source`: own/card/licensed）、`ai_assisted`、`niche`。字段说明见 `harness/draft.py` 的 `FINAL_SCHEMA_HINT`。
