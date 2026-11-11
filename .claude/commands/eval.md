---
description: 跑 agent 能力评测，看各步骤（初稿、挑选、卡片、风控、发布决策）做得怎么样
argument-hint: [step 或 agent，例如 draft、publish、deepseek，可省略]
---

参数：$ARGUMENTS

1. 根据参数拼命令：参数里的 step 名（draft、select、cards、risk_engine、risk_fix、risk_review、publish）各加一个 `--step`；deepseek / doubao / claude 作为 `--agent`；没有参数就跑全部。
2. 如果要调用模型（不只是 risk_engine），先告诉用户大概费用（全部跑一遍用 Claude 约 0.5–1 美元），等用户同意再跑。
3. 运行 `python -m evals <参数>`。没有 key 时它会只跑 risk_engine 并提示，照实告诉用户缺哪个 key（见 `evals/README.md`）。
4. 用中文总结：每个 step 的通过率；失败的用例逐个说明是哪项评分没过、agent 实际输出了什么；已知缺口有没有被修复。
5. 如果失败指向某个指令或领域配置的问题，提出具体修改建议（按 CLAUDE.md 规则 6 走分支 + PR），不要直接改。
