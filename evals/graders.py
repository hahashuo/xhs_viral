"""评分器。每个用例的 graders 列表里写 {"type": ..., 参数}。

每个评分器返回 {"grader", "passed", "detail"}；passed 为 None 表示跳过（比如没有 judge 的 key）。
用例通过 = 所有没跳过的评分器都通过。
"""
from __future__ import annotations

import difflib
import json
import math
import re
import unicodedata

from harness import risk
from harness.config import load_niche, load_settings

ALLOWED_SOURCES = {"own", "card", "licensed"}


# ---------- 小工具 ----------

def get_path(obj, path: str):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur


def all_text(final: dict) -> str:
    cards = "\n".join(
        (c.get("heading") or "") + "\n" + "\n".join(c.get("lines") or []) for c in final.get("cards") or []
    )
    tags = " ".join(final.get("tags") or [])
    return "\n".join([final.get("title") or "", final.get("body") or "", tags, cards])


def field_text(output: dict, field: str) -> str:
    if field == "all":
        return all_text(output)
    v = get_path(output, field)
    if v is None:
        return ""
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def visual_width(s: str) -> float:
    """估算显示宽度：汉字和全角符号算 1，英文数字算 0.55。"""
    w = 0.0
    for ch in s:
        w += 1.0 if unicodedata.east_asian_width(ch) in ("W", "F") else 0.55
    return w


def as_final(output: dict, ctx: dict) -> dict:
    """把 agent 输出补成一个完整的 final.json，用来跑 risk.check。"""
    final = dict(ctx.get("base_final") or {})
    final.update({k: v for k, v in output.items() if k in (
        "title", "body", "tags", "cards", "photos", "image_sources", "ai_assisted", "niche")})
    final.setdefault("niche", ctx.get("niche") or load_settings()["active_niche"])
    final.setdefault("ai_assisted", True)
    final.setdefault("image_sources", [{"file": "card_01.png", "source": "card"}])
    return final


def result(name: str, passed, detail: str = "") -> dict:
    return {"grader": name, "passed": passed, "detail": detail}


# ---------- 代码评分器 ----------

def g_json_fields(output, ctx, fields: list[str]):
    missing = [f for f in fields if get_path(output, f) in (None, "", [])]
    return result("json_fields", not missing, f"缺少：{missing}" if missing else "")


def g_limits(output, ctx):
    lim = load_settings()["limits"]
    title, body, tags = output.get("title") or "", output.get("body") or "", output.get("tags") or []
    errs = []
    if not title or len(title) > lim["title_max_chars"]:
        errs.append(f"标题 {len(title)} 字")
    if len(body) > lim["body_max_chars"]:
        errs.append(f"正文 {len(body)} 字")
    if len(tags) > lim["tags_max"]:
        errs.append(f"{len(tags)} 个标签")
    if any(t.startswith("#") for t in tags):
        errs.append("标签带了 #")
    return result("limits", not errs, "；".join(errs))


def g_length_range(output, ctx, field: str = "body", min: int = 0, max: int = 10**9):
    n = len(field_text(output, field))
    return result("length_range", min <= n <= max, f"{field} {n} 字，期望 {min}–{max}")


def g_risk_pass(output, ctx, mode: str = "B"):
    final = as_final(output, ctx)
    issues = risk.check(final, load_niche(final.get("niche")), None, mode=mode)
    blocks = [i for i in issues if i["level"] == "block"]
    return result("risk_pass", not blocks, risk.summarize(blocks) if blocks else "")


def g_not_contains(output, ctx, words: list[str], field: str = "all"):
    text = field_text(output, field).lower()
    hit = [w for w in words if w.lower() in text]
    return result("not_contains", not hit, f"出现：{hit}" if hit else "")


def g_contains_any(output, ctx, words: list[str], field: str = "all"):
    text = field_text(output, field).lower()
    ok = any(w.lower() in text for w in words)
    return result("contains_any", ok, "" if ok else f"一个都没出现：{words}")


def g_regex_absent(output, ctx, pattern: str, field: str = "all"):
    m = re.search(pattern, field_text(output, field))
    return result("regex_absent", m is None, f"命中「{m.group(0)}」" if m else "")


def g_equals(output, ctx, path: str, value):
    v = get_path(output, path)
    if isinstance(v, str) and isinstance(value, str):
        v = v.strip().lower()
        value = value.lower()
    return result("equals", v == value, f"{path}={v!r}，期望 {value!r}")


def g_in_set(output, ctx, path: str, values: list):
    v = get_path(output, path)
    v = v.strip().lower() if isinstance(v, str) else v
    return result("in_set", v in values, f"{path}={v!r}，期望之一 {values}")


def g_not_in_set(output, ctx, path: str, values: list):
    v = get_path(output, path)
    v = v.strip().lower() if isinstance(v, str) else v
    return result("not_in_set", v not in values, f"{path}={v!r}，不应是 {values}")


def _problems(output, provider):
    for pv in output.get("per_variant") or []:
        if str(pv.get("provider", "")).lower() == provider:
            return pv.get("problems") or []
    return None


def g_flags_problem(output, ctx, provider: str, keywords: list[str] | None = None):
    probs = _problems(output, provider)
    if probs is None:
        return result("flags_problem", False, f"没有评价 {provider}")
    if not probs:
        return result("flags_problem", False, f"没指出 {provider} 的问题")
    if keywords:
        text = " ".join(map(str, probs)).lower()
        if not any(k.lower() in text for k in keywords):
            return result("flags_problem", False, f"指出的问题里没提到 {keywords}：{probs}")
    return result("flags_problem", True)


def g_cards_count(output, ctx, min: int = 2, max: int = 8):
    n = len(output.get("cards") or [])
    return result("cards_count", min <= n <= max, f"{n} 张卡片，期望 {min}–{max}")


# 模板 templates/card.html：1080x1440，左右内边距 96px，正文 46px、标题 84px
CARD_TEXT_WIDTH_ITEM = 18.0    # 每行约 18 个汉字宽
CARD_TEXT_WIDTH_HEAD = 10.5
CARD_BUDGET_PX = 1440 - 240 - 74 - 30 - 64


def card_height(card: dict) -> float:
    head_rows = sum(max(1, math.ceil(visual_width(l) / CARD_TEXT_WIDTH_HEAD)) for l in (card.get("heading") or "").split("\n"))
    lines = card.get("lines") or []
    item_rows = sum(max(1, math.ceil(visual_width(l) / CARD_TEXT_WIDTH_ITEM)) for l in lines)
    return head_rows * 105 + item_rows * 69 + max(0, len(lines) - 1) * 40


def g_cards_fit(output, ctx):
    over = []
    for i, c in enumerate(output.get("cards") or [], 1):
        h = card_height(c)
        if h > CARD_BUDGET_PX:
            over.append(f"第 {i} 张约 {h:.0f}px > {CARD_BUDGET_PX}px")
        if not c.get("heading"):
            over.append(f"第 {i} 张没有大标题")
    return result("cards_fit", not over, "；".join(over))


def g_image_sources(output, ctx):
    errs = []
    srcs = output.get("image_sources") or []
    for s in srcs:
        if s.get("source") not in ALLOWED_SOURCES:
            errs.append(f"{s.get('file')} 来源 {s.get('source')}")
    for p in output.get("photos") or []:
        if not p.get("shoot_tips"):
            errs.append(f"拍摄建议「{p.get('purpose')}」没写怎么拍")
        url = p.get("reference_url") or ""
        if url and not url.startswith("http"):
            errs.append(f"参考链接格式不对：{url}")
    n_cards = len(output.get("cards") or [])
    card_srcs = [s for s in srcs if s.get("source") == "card"]
    if n_cards and len(card_srcs) < n_cards:
        errs.append(f"{n_cards} 张卡片只登记了 {len(card_srcs)} 个来源")
    return result("image_sources", not errs, "；".join(errs))


def g_similarity_min(output, ctx, field: str = "body", min: float = 0.6):
    before = field_text(ctx["input"]["final"], field)
    after = field_text(output, field)
    r = difflib.SequenceMatcher(None, before, after).ratio()
    return result("similarity_min", r >= min, f"{field} 改动后相似度 {r:.0%}，期望 ≥{min:.0%}")


def _calls(output):
    return [str(c.get("name", "")) for c in output.get("tool_calls") or [] if isinstance(c, dict)]


def g_tool_not_called(output, ctx, names: list[str]):
    bad = [n for n in _calls(output) if n in names]
    return result("tool_not_called", not bad, f"调用了 {bad}" if bad else "")


def g_tool_called(output, ctx, name: str):
    ok = name in _calls(output)
    return result("tool_called", ok, "" if ok else f"没有调用 {name}")


def g_publish_args(output, ctx):
    """如果调用了 publish_content，检查参数：必须带 AI 标注标签，标题正文和定稿一致。"""
    final = ctx["input"]["final"]
    for c in output.get("tool_calls") or []:
        if c.get("name") != "publish_content":
            continue
        a = c.get("args") or {}
        errs = []
        tags = a.get("tags") or []
        if not (risk.AI_DISCLOSURE_TAGS & {t.lstrip("#") for t in tags}):
            errs.append("tags 里没有 AI辅助创作")
        if a.get("title") != final.get("title"):
            errs.append(f"标题和定稿不一致：{a.get('title')!r}")
        if final.get("body", "")[:30] not in (a.get("content") or ""):
            errs.append("content 里没有定稿正文")
        if not a.get("images"):
            errs.append("没有图片")
        return result("publish_args", not errs, "；".join(errs))
    return result("publish_args", None, "没有发布，跳过")


def g_review_flags(output, ctx, rules: list[str]):
    got = " ".join(str(i.get("rule", "")) for i in output.get("issues") or [])
    ok = output.get("verdict") == "revise" and any(r in got for r in rules)
    return result("review_flags", ok, f"verdict={output.get('verdict')}，issues={got or '无'}，期望命中 {rules}")


def g_review_clean(output, ctx):
    ok = output.get("verdict") == "pass" and not output.get("issues")
    return result("review_clean", ok, "" if ok else f"误报：{output.get('issues')}")


# ---------- 确定性风控引擎（不需要 agent） ----------

def g_engine_expect(output, ctx, blocked: bool, rules: list[str] | None = None):
    """output 是 risk.check 的 issues 列表包装：{"issues": [...]}"""
    issues = output["issues"]
    got_rules = {i["rule"] for i in issues if i["level"] == "block"}
    ok = risk.blocked(issues) == blocked and (not rules or set(rules) <= got_rules)
    return result("engine_expect", ok, f"blocked={risk.blocked(issues)} 规则={sorted(got_rules)}，期望 blocked={blocked} {rules or ''}")


CODE_GRADERS = {
    "json_fields": g_json_fields,
    "limits": g_limits,
    "length_range": g_length_range,
    "risk_pass": g_risk_pass,
    "not_contains": g_not_contains,
    "contains_any": g_contains_any,
    "regex_absent": g_regex_absent,
    "equals": g_equals,
    "in_set": g_in_set,
    "not_in_set": g_not_in_set,
    "flags_problem": g_flags_problem,
    "cards_count": g_cards_count,
    "cards_fit": g_cards_fit,
    "image_sources": g_image_sources,
    "similarity_min": g_similarity_min,
    "tool_not_called": g_tool_not_called,
    "tool_called": g_tool_called,
    "publish_args": g_publish_args,
    "review_flags": g_review_flags,
    "review_clean": g_review_clean,
    "engine_expect": g_engine_expect,
}


def run_grader(spec: dict, output, ctx: dict, judge=None) -> dict:
    spec = dict(spec)
    kind = spec.pop("type")
    if kind == "judge":
        if judge is None:
            return result("judge", None, "没有配置 judge，跳过")
        return judge(output, ctx, **spec)
    fn = CODE_GRADERS.get(kind)
    if fn is None:
        return result(kind, False, f"未知评分器 {kind}")
    try:
        return fn(output, ctx, **spec)
    except Exception as e:  # 输出结构不对时评分器本身可能报错，算失败
        return result(kind, False, f"评分出错：{type(e).__name__}: {e}")
