---
description: 切换或查看当前专精领域
argument-hint: [领域名]
---

参数：$ARGUMENTS

- 没有参数：列出 `niches/` 下所有领域（跳过 `_template`），标出当前领域（`harness.toml` 的 `active_niche`），每个领域一句话概括其 persona 和 style。
- 有参数：如果 `niches/<参数>/` 存在，修改 `harness.toml` 的 `active_niche`，然后用三句话概括这个领域的人设、文风和禁区。不存在就提示用 `/new-niche <名字>` 新建。
