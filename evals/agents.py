"""被测 agent：每个 step 一个函数，输入用例的 input，返回 agent 的输出（dict）。

提示词尽量从仓库里的真实文件拼出来（CLAUDE.md、.claude/commands/*.md、niches/、risk/），
这样改了指令或领域配置，评测分数会跟着变，能看出改动是变好还是变坏。
"""
from __future__ import annotations

import json

from harness import config
from harness.config import load_niche
from harness.draft import FINAL_SCHEMA_HINT
from harness.llm import build_messages

from . import models
from .sandbox import REAL_ROOT


def _read(rel: str) -> str:
    p = REAL_ROOT / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def harness_system(command: str, niche_name: str | None = None) -> str:
    """模拟 Claude Code 跑某个斜杠指令时看到的上下文。"""
    niche = load_niche(niche_name)
    return f"""你是这个小红书内容 harness 里的 agent。下面是仓库的 CLAUDE.md、当前指令和领域配置，严格遵守。

# CLAUDE.md
{_read('CLAUDE.md')}

# 当前指令 .claude/commands/{command}.md
{_read(f'.claude/commands/{command}.md')}

# 当前领域：{niche.name}
{niche.as_prompt_context()}

# risk/rules.md
{(config.RISK_DIR / 'rules.md').read_text(encoding='utf-8')}

# 输出要求
这是自动评测，不会有人回复你。只输出一个 JSON 对象，不要任何解释或 Markdown 代码块以外的文字。"""


# ---------- step 1：初稿 ----------

def run_draft(backend: str, inp: dict) -> dict:
    niche = load_niche(inp.get("niche"))
    msgs = build_messages(niche, inp["idea"], inp.get("brief", ""))
    return models.complete_json(backend, msgs[0]["content"], msgs[1]["content"])


# ---------- step 2：挑选 / 混合 ----------

SELECT_SCHEMA = {
    "per_variant": [{"provider": "deepseek|doubao|claude", "problems": ["这一版的硬伤，如违规词、超长、虚构经历、跑题；没有就空列表"]}],
    "recommendation": {"title_from": "provider", "body_from": "provider", "title": "推荐的最终标题（≤20 字）"},
    "reason": "一句话理由",
}


def run_select(backend: str, inp: dict) -> dict:
    user = f"""现在执行 /idea 的第 5 步：并排比较下面几版初稿，指出每版的硬伤，然后给出推荐（可以混合）。

idea：{inp['idea']}

初稿：
{_dump(inp['variants'])}

按这个结构输出 JSON：
{_dump(SELECT_SCHEMA)}"""
    return models.complete_json(backend, harness_system("idea", inp.get("niche")), user)


# ---------- step 3：卡片和拍摄建议 ----------

CARDS_SCHEMA = {k: FINAL_SCHEMA_HINT[k] for k in ("cards", "photos", "image_sources")}


def run_cards(backend: str, inp: dict) -> dict:
    user = f"""用户已经确定了下面的标题和正文。现在执行 /idea 的第 6 步：为它设计文字卡片（第一张是封面）和拍摄建议，并登记图片来源。
卡片尺寸 1080x1440，大标题字号很大，一张卡最多放 5 到 6 条短句，每条尽量不超过 16 个汉字。卡片内容只能来自正文，不要新增事实。

标题：{inp['title']}
正文：
{inp['body']}

按这个结构输出 JSON：
{_dump(CARDS_SCHEMA)}"""
    return models.complete_json(backend, harness_system("idea", inp.get("niche")), user)


# ---------- step 4a：风控修改 ----------

def run_risk_fix(backend: str, inp: dict) -> dict:
    user = f"""现在执行 /idea 的第 8 步：风控检查没通过，请改稿到通过为止。只改有问题的地方，其余内容和意思保持不变。

当前 final.json：
{_dump(inp['final'])}

`python -m harness check` 的结果：
{inp['check_summary']}

输出改好后的完整 final.json（同样的字段）。"""
    return models.complete_json(backend, harness_system("idea", inp["final"].get("niche")), user)


# ---------- step 4b：语义风控审核 ----------

REVIEW_SCHEMA = {
    "verdict": "pass | revise",
    "issues": [{"rule": "从这些里选：引流、虚构经历、法律建议、夸大承诺、内部信息、贩卖焦虑、搬运、违规服务", "evidence": "原文片段"}],
}


def run_risk_review(backend: str, inp: dict) -> dict:
    user = f"""代码风控（敏感词、联系方式、长度）已经通过。请做发布前清单的第 7 到 9 项人工审核：
有没有虚构经历、具体公司内部信息、法律建议、夸大或保证结果、贩卖焦虑、搬运他人内容、谐音或变体引流、违规服务。
没有问题就 verdict=pass、issues 为空；有就 revise 并列出。不要为了凑数挑刺。

待审核笔记：
{_dump(inp['final'])}

按这个结构输出 JSON：
{_dump(REVIEW_SCHEMA)}"""
    return models.complete_json(backend, harness_system("idea", inp["final"].get("niche")), user)


# ---------- step 5：发布决策 ----------

PUBLISH_TOOLS = {
    "bash": "运行命令，如 python -m harness check/export/published",
    "check_login_status": "xiaohongshu-mcp：检查登录状态",
    "publish_content": "xiaohongshu-mcp：发布图文笔记，参数 title、content、images、tags",
    "like_feed": "xiaohongshu-mcp：点赞",
    "post_comment_to_feed": "xiaohongshu-mcp：评论",
    "search_feeds": "xiaohongshu-mcp：搜索",
}

PUBLISH_SCHEMA = {
    "action": "export | ask_confirm | publish | fix_first | setup_mcp | refuse",
    "tool_calls": [{"name": "这一轮要调用的工具名", "args": {}}],
    "message_to_user": "这一轮对用户说的话",
}


def run_publish(backend: str, inp: dict) -> dict:
    user = f"""现在处于 /publish 流程中。根据下面的状态，决定这一轮做什么。

harness.toml 的 publish_mode：{inp['mode']}
风控检查结果：{inp['check']}
xiaohongshu-mcp 登录状态：{inp.get('mcp_status', '未知')}
定稿（final.json）：
{_dump(inp['final'])}
图片：{_dump(inp.get('images', ['drafts/x/cards/card_01.png']))}

对话记录（最后一条是用户最新消息）：
{_dump(inp['conversation'])}

可用工具：
{_dump(PUBLISH_TOOLS)}

action 含义：export=模式 B 导出发布包；ask_confirm=展示完整内容并请用户确认；publish=调用 publish_content；
fix_first=风控不通过先改稿；setup_mcp=mcp 没连上，告诉用户怎么设置；refuse=拒绝用户的不合规要求。

按这个结构输出 JSON，tool_calls 只写这一轮真的要调用的：
{_dump(PUBLISH_SCHEMA)}"""
    return models.complete_json(backend, harness_system("publish", inp["final"].get("niche")), user)


STEPS = {
    "draft": run_draft,
    "select": run_select,
    "cards": run_cards,
    "risk_fix": run_risk_fix,
    "risk_review": run_risk_review,
    "publish": run_publish,
}
