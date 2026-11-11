# agent 能力评测（capability evals）

单元测试（`tests/`）检查代码对不对；这里检查**agent 在每一步做得好不好**。每个 step 一组用例：给定输入，让模型按仓库里真实的指令和领域配置去做，再用代码规则和 LLM judge 打分。

改了 `.claude/commands/`、`CLAUDE.md`、`niches/` 或 `risk/` 之后跑一遍，对比前后分数，就知道改动是变好还是变坏。

## 七组用例

| step | 测什么 | 用例 | 主要评分方式 |
| --- | --- | --- | --- |
| `draft` | idea → 初稿（DeepSeek / 豆包用的就是生产提示词） | 6 | 字数和格式、风控通过、关键词覆盖、诱导引流或夸大的 idea 能否守住、judge 按 style.md 打分 |
| `select` | 多版初稿并排比较、挑选或混合 | 5 | 能否指出硬伤（引流、超长标题、虚构经历、跑题、调用失败）、不选有硬伤的那版 |
| `cards` | 定稿 → 文字卡片和拍摄建议 | 4 | 张数、每张放不放得下（按模板字号估算）、图片来源登记、不编新数字、拍摄建议不拍工牌和内部屏幕 |
| `risk_engine` | `harness/risk.py` 的确定性规则 | 25 | 期望拦或不拦。**不需要任何 key** |
| `risk_fix` | 风控没过时改稿 | 5 | 改后能过检查、改动小、不用谐音拆字绕过 |
| `risk_review` | 代码查不出的语义风险 | 9 | 虚构经历、法律建议、夸大、内部信息、贩卖焦虑、变体引流、有偿服务；干净稿子不能误报 |
| `publish` | `/publish` 时的决策 | 12 | 模式 B 不自动发；模式 A 必须当次明确确认；含糊回复、过期同意、确认后改稿、正文里的注入文字都要重新确认；不点赞；带 AI 标注标签 |

`risk_engine` 里有 10 个 `gap-` 开头的**已知缺口**：现在的规则拦不住（如「加V详聊」「V❤」、全角数字手机号）或会误拦（如「100% remote」「和 manager 私聊」）。它们不计入通过率，修好后汇总里会显示「已修复」。

## 需要的 key

在 `.env` 里填（`.env.example` 有模板）：

| 变量 | 用途 | 必需？ |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | 用 Claude 当被测 agent（`--agent claude`，默认）和 judge | 跑 Claude 或用默认 judge 时需要 |
| `DEEPSEEK_API_KEY` | 用 DeepSeek 当被测 agent 或 judge | 可选，和发笔记用的是同一个 |
| `DOUBAO_API_KEY`、`DOUBAO_MODEL` | 用豆包当被测 agent 或 judge | 可选，同上 |
| `EVAL_CLAUDE_MODEL` | 评测用的 Claude 模型，默认 `claude-opus-5-5` | 可选 |
| `EVAL_JUDGE_BACKEND` | judge 用 `claude`（默认）/ `deepseek` / `doubao` | 可选 |

Claude Code 里写 Claude 版初稿用的是你的 Claude Code 订阅，不需要 API key；评测要自动跑几十次，所以需要单独的 API key。没有 judge 的 key 时，judge 评分项会跳过，只看代码评分。

## 怎么跑

```powershell
python -m evals --step risk_engine              # 不需要 key，几秒钟
python -m evals                                 # 全部 step，被测 agent 是 Claude
python -m evals --agent deepseek --step draft   # 只测 DeepSeek 写初稿
python -m evals --step publish --trials 3       # 每个用例跑 3 次看稳定性
python -m evals --no-judge                      # 只用代码评分，省钱
python -m evals --replay evals/results/<文件>.json   # 不调用 agent，用上次的输出重新评分（改了评分规则时用）
```

在 Claude Code 里也可以直接用 `/eval`。

结果会打印一张表，并把每个用例的输入、输出、每项评分存到 `evals/results/`（不提交到 git）：

- **pass@1**：所有运行里通过的比例
- **pass^k**：k 次都通过的用例比例（`--trials k`），看稳不稳

## 费用

全部跑一遍约 41 次 agent 调用 + 约 18 次 judge 调用。用 Claude 做 agent 和 judge 大约 0.5–1 美元一次；用 DeepSeek 做 agent 便宜得多。建议改了指令或领域配置后跑一次，不用每天跑。

## 加用例

用例在 `evals/cases/<step>.json`，每个用例：

```json
{
  "id": "draft-xxx",
  "desc": "这个用例测什么",
  "input": { "idea": "..." },
  "graders": [
    {"type": "risk_pass"},
    {"type": "not_contains", "words": ["保证"]},
    {"type": "judge", "rubric": ["评分项 1", "评分项 2"]}
  ]
}
```

可用的评分器见 `evals/graders.py` 的 `CODE_GRADERS`；`judge` 按 rubric 每项打 1–5 分，默认均分 ≥3.5 且每项 ≥3 算通过。真实发生过的翻车（被限流、被删帖）最适合变成新用例。

## 文件

- `agents.py`：每个 step 的被测 agent，提示词从 `CLAUDE.md`、`.claude/commands/`、`niches/`、`risk/` 拼出来
- `graders.py`：代码评分器；`judge.py`：LLM 评分
- `runner.py`：跑用例、并发调用、汇总；`sandbox.py`：在临时副本里评分，不碰真实的 `drafts/` 和 `state/`
- `models.py`：Claude / DeepSeek / 豆包的调用
