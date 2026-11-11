---
description: 从一个 idea 生成笔记：Claude 策划 + DeepSeek/豆包/Claude 三版初稿 → 你挑选 → 定稿、卡片、风控检查
argument-hint: <你的 idea>
---

用户的 idea：$ARGUMENTS

按顺序做：

1. 读 `harness.toml` 得到当前领域，读 `niches/<领域>/` 下所有文件和 `risk/rules.md`。idea 为空时，从 `topics.md` 和 `insights.md` 推荐 3 个选题让用户选，然后停下。
2. **写选题策划**（5 行以内）：目标读者、切入角度、开头钩子、要点结构、3 个候选标题（每个 ≤20 字）。
3. 运行：`python -m harness variants "<idea>" --brief "<选题策划>"`。记下输出的草稿文件夹。某个模型失败（比如没配 key）就跳过它，告诉用户原因。
4. **写 Claude 版**：按同样的策划和领域配置写一版，存为 `<草稿文件夹>/variants/claude.json`，字段同 `FINAL_SCHEMA_HINT`，再加 `"provider": "claude"`。
5. **并排展示**：每版给出标题、开头两句、要点列表、字数。最后给出你的推荐（可以是混合，比如「用豆包的标题 + Claude 的正文」）和一句理由。然后停下，等用户选择或修改。
6. 用户确定后，写 `<草稿文件夹>/final.json`（加上 `"niche": "<领域>"`），`image_sources` 先登记卡片（`card_01.png` 等，source 为 `card`）。
7. 运行 `python -m harness cards <草稿文件夹>` 和 `python -m harness check <草稿文件夹>`。
8. 告诉用户：卡片已生成的路径；拍摄建议（如有）；风控结果。有「必须修改」就改到通过为止。最后提示下一步用 `/publish`。如果用户要放自己拍的照片，让他放进 `<草稿文件夹>/photos/` 并告诉你，你在 `image_sources` 里登记为 `own`。
