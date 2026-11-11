"""LLM 评分（judge）：按用例里的 rubric 逐条打 1–5 分。

judge 默认用 Claude（EVAL_JUDGE_BACKEND=claude），也可以换成 deepseek / doubao。
judge 和被测 agent 最好不是同一个模型，否则容易自己给自己打高分。
"""
from __future__ import annotations

import json
import os

from harness.config import load_niche

from . import models

JUDGE_SYSTEM = """你是小红书「{niche}」领域的资深编辑，负责给 AI agent 的产出打分。
评分要严格、具体，引用原文说明理由。只根据给出的材料评分，不要脑补。

领域文风要求：
{style}

只输出 JSON：{{"scores": [{{"criterion": "评分项原文", "score": 1到5的整数, "reason": "一句话理由"}}]}}
分数含义：5 完全做到；4 基本做到，有小瑕疵；3 一般；2 明显不足；1 完全没做到或做反了。"""


def judge_backend() -> str:
    return os.getenv("EVAL_JUDGE_BACKEND", "claude")


def make_judge():
    """有可用的 judge 后端时返回评分函数，否则返回 None（judge 评分项会被跳过）。"""
    backend = judge_backend()
    if not models.available(backend):
        return None

    def judge(output, ctx, rubric: list[str], pass_mean: float = 3.5, min_each: int = 3):
        niche = load_niche(ctx.get("niche"))
        system = JUDGE_SYSTEM.format(niche=niche.name, style=niche.text("style.md"))
        user = f"""任务：{ctx['task_desc']}

agent 收到的输入：
{json.dumps(ctx['input'], ensure_ascii=False, indent=2)}

agent 的输出：
{json.dumps(output, ensure_ascii=False, indent=2)}

评分项：
""" + "\n".join(f"{i}. {r}" for i, r in enumerate(rubric, 1))
        try:
            data = models.complete_json(backend, system, user, max_tokens=4000)
            scores = [int(s["score"]) for s in data["scores"]]
        except Exception as e:
            return {"grader": "judge", "passed": False, "detail": f"judge 出错：{e}"}
        if len(scores) != len(rubric):
            return {"grader": "judge", "passed": False, "detail": f"judge 只给了 {len(scores)}/{len(rubric)} 项分数"}
        mean = sum(scores) / len(scores)
        passed = mean >= pass_mean and min(scores) >= min_each
        detail = f"均分 {mean:.1f}（{scores}）；" + "；".join(
            f"{s.get('score')}分 {s.get('reason', '')}" for s in data["scores"] if int(s["score"]) < 4
        )
        return {"grader": "judge", "passed": passed, "detail": detail, "scores": data["scores"], "mean": mean}

    return judge
