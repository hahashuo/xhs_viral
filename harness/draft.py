"""草稿文件夹的读写。

每篇笔记一个文件夹 drafts/<日期>-<短名>/：
  idea.md            原始 idea
  variants/*.json    各模型的初稿（deepseek / doubao / claude）
  final.json         你确认的定稿（标题、正文、标签、卡片、拍摄建议、图片来源）
  cards/*.png        自动生成的文字卡片
  check.json         最近一次风控检查结果
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from . import config

FINAL_SCHEMA_HINT = {
    "title": "标题，≤20 字",
    "body": "正文，≤1000 字，不含话题标签",
    "tags": ["话题标签，不带 #"],
    "cards": [{"heading": "卡片大标题", "lines": ["卡片正文要点"]}],
    "photos": [
        {
            "purpose": "这张图在笔记里的作用，如封面",
            "shoot_tips": "怎么拍：构图、道具、光线、文字位置",
            "reference_url": "可选：参考图链接，只作参考，不直接使用",
        }
    ],
    "image_sources": [{"file": "图片文件名", "source": "own | card | licensed", "note": "来源说明"}],
    "ai_assisted": True,
}


def slugify(text: str, max_len: int = 16) -> str:
    text = re.sub(r"[\\/:*?\"<>|\s]+", "-", text.strip())
    return text[:max_len].strip("-") or "draft"


def new_draft_dir(idea: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path = config.DRAFTS_DIR / f"{stamp}-{slugify(idea)}"
    (path / "variants").mkdir(parents=True, exist_ok=True)
    (path / "idea.md").write_text(idea.strip() + "\n", encoding="utf-8")
    return path


def resolve_draft(arg: str | None) -> Path:
    """接受草稿路径或名字；不传时取最新的一篇。"""
    if arg:
        p = Path(arg)
        if not p.is_absolute() and not p.exists():
            p = config.DRAFTS_DIR / arg
        if not p.is_dir():
            raise SystemExit(f"找不到草稿：{arg}")
        return p
    drafts_dir = config.DRAFTS_DIR
    drafts = sorted((d for d in drafts_dir.iterdir() if d.is_dir()), key=lambda d: d.name) if drafts_dir.exists() else []
    if not drafts:
        raise SystemExit("还没有草稿。先用 /idea 生成一篇。")
    return drafts[-1]


def load_final(path: Path) -> dict:
    fp = path / "final.json"
    if not fp.exists():
        raise SystemExit(f"{path.name} 还没有 final.json，先确认定稿。")
    return json.loads(fp.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
