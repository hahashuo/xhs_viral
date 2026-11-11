"""发布前风控检查。规则来源见 risk/rules.md。

结果分三级：block（必须改）、warn（建议改）、ok。有任何 block 就不能发布或导出。
"""
from __future__ import annotations

import difflib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .config import Niche, load_settings, read_published

# 联系方式和引流的常见写法
CONTACT_PATTERNS = [
    (r"(?<!\d)1[3-9]\d{9}(?!\d)", "疑似手机号"),
    (r"\+?1?[\s-]?\(?\d{3}\)?[\s-]\d{3}[\s-]\d{4}", "疑似北美电话号码"),
    (r"[\w.+-]+@[\w-]+\.[\w.]+", "疑似邮箱"),
    (r"https?://|www\.", "站外链接"),
    (r"(?i)\b(v|vx|wx|wechat|weixin)\s*[:：]?\s*[\w-]{4,}", "疑似微信号"),
    (r"(?i)(加我|私我|私信我|戳我|主页.{0,4}(联系|找我)|评论区.{0,4}(扣|留)\s*\d)", "引导私信或站外联系"),
]

AI_DISCLOSURE_TAGS = {"AI创作", "AI辅助创作"}


def load_banned_words(niche: Niche | None = None) -> list[str]:
    words: list[str] = []
    sources = [config.RISK_DIR / "banned_words.txt"]
    if niche is not None:
        sources.append(niche.path / "banned.md")
    for src in sources:
        if not src.exists():
            continue
        is_md = src.suffix == ".md"
        for line in src.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if is_md:
                # Markdown 文件只认列表项（- 词），说明文字不算
                if not line.startswith("- "):
                    continue
                line = line[2:].strip()
            if line and not line.startswith("#"):
                words.append(line)
    return words


def check(final: dict, niche: Niche | None = None, draft_dir: Path | None = None, mode: str | None = None) -> list[dict]:
    settings = load_settings()
    limits = settings["limits"]
    mode = mode or settings.get("publish_mode", "B")
    issues: list[dict] = []

    def add(level: str, rule: str, detail: str) -> None:
        issues.append({"level": level, "rule": rule, "detail": detail})

    title = final.get("title", "")
    body = final.get("body", "")
    tags = final.get("tags", [])
    card_text = "\n".join(
        c.get("heading", "") + "\n" + "\n".join(c.get("lines", [])) for c in final.get("cards", [])
    )
    all_text = "\n".join([title, body, " ".join(tags), card_text])

    # 1. 长度
    if not title:
        add("block", "标题", "标题为空")
    elif len(title) > limits["title_max_chars"]:
        add("block", "标题长度", f"标题 {len(title)} 字，上限 {limits['title_max_chars']}")
    if len(body) > limits["body_max_chars"]:
        add("block", "正文长度", f"正文 {len(body)} 字，上限 {limits['body_max_chars']}")
    if len(tags) > limits["tags_max"]:
        add("warn", "标签数量", f"{len(tags)} 个标签，建议不超过 {limits['tags_max']}")

    # 2. 敏感词和引流
    for word in load_banned_words(niche):
        if word and word.lower() in all_text.lower():
            add("block", "敏感词", f"出现「{word}」")
    for pattern, label in CONTACT_PATTERNS:
        m = re.search(pattern, all_text)
        if m:
            add("block", "引流", f"{label}：「{m.group(0)}」")

    # 3. AI 标注
    if final.get("ai_assisted", True):
        if mode == "B":
            add("warn", "AI 标注", "手动发布时记得勾选「AI 辅助创作」")
        elif not (AI_DISCLOSURE_TAGS & set(tags)):
            add("block", "AI 标注", "自动发布无法勾选声明框，需在标签里加「AI辅助创作」")

    # 4. 图片来源
    sources = final.get("image_sources", [])
    for s in sources:
        if s.get("source") not in {"own", "card", "licensed"}:
            add("block", "图片来源", f"{s.get('file', '?')} 来源为「{s.get('source')}」，只允许自拍、卡片或可商用图库")
    if draft_dir is not None:
        imgs = [p.name for p in (draft_dir / "cards").glob("*.png")] if (draft_dir / "cards").exists() else []
        imgs += [p.name for p in (draft_dir / "photos").glob("*") if p.is_file()] if (draft_dir / "photos").exists() else []
        declared = {s.get("file") for s in sources}
        for name in imgs:
            if name not in declared and not name.startswith("card_"):
                add("block", "图片来源", f"{name} 没有在 image_sources 里登记来源")
        if not imgs:
            add("warn", "配图", "还没有任何图片，先生成卡片或放入照片")

    # 5. 与近期笔记重复
    history = read_published()
    for rec in history[-30:]:
        ratio = difflib.SequenceMatcher(None, title, rec.get("title", "")).ratio()
        if ratio >= 0.8:
            add("block", "重复内容", f"标题和已发的「{rec.get('title')}」相似度 {ratio:.0%}")
        elif ratio >= 0.6:
            add("warn", "重复内容", f"标题和已发的「{rec.get('title')}」相似度 {ratio:.0%}")

    # 6. 发布频率
    now = datetime.now(timezone.utc)
    times = [datetime.fromisoformat(r["published_at"]) for r in history if "published_at" in r]
    today = [t for t in times if now - t < timedelta(hours=24)]
    if len(today) >= settings.get("daily_post_limit", 2):
        add("block", "发布频率", f"过去 24 小时已发 {len(today)} 篇，上限 {settings['daily_post_limit']}")
    if times:
        gap = (now - max(times)).total_seconds() / 3600
        if gap < settings.get("min_hours_between_posts", 4):
            add("warn", "发布间隔", f"距上一篇只有 {gap:.1f} 小时，建议至少 {settings['min_hours_between_posts']} 小时")

    return issues


def summarize(issues: list[dict]) -> str:
    if not issues:
        return "风控检查通过，没有问题。"
    lines = []
    for level, label in (("block", "必须修改"), ("warn", "建议注意")):
        group = [i for i in issues if i["level"] == level]
        if group:
            lines.append(f"{label}（{len(group)}）：")
            lines += [f"  - [{i['rule']}] {i['detail']}" for i in group]
    return "\n".join(lines)


def blocked(issues: list[dict]) -> bool:
    return any(i["level"] == "block" for i in issues)
