"""命令行入口：python -m harness <命令>。日常由 Claude Code 的斜杠指令调用。"""
from __future__ import annotations

import argparse
import json
import sys

from . import risk
from .config import load_niche, load_settings, append_published, read_published
from .draft import load_final, new_draft_dir, resolve_draft, save_json


def cmd_variants(args) -> None:
    from .llm import generate_variants

    niche = load_niche(args.niche)
    draft = new_draft_dir(args.idea)
    brief = args.brief or ""
    if brief:
        (draft / "brief.md").write_text(brief + "\n", encoding="utf-8")
    results = generate_variants(niche, args.idea, brief)
    for r in results:
        save_json(draft / "variants" / f"{r['provider']}.json", r)
        status = "失败：" + r["error"] if "error" in r else f"「{r.get('title', '')}」"
        print(f"[{r['provider']}] {status}")
    print(f"\n草稿文件夹：{draft}")


def cmd_check(args) -> None:
    draft = resolve_draft(args.draft)
    final = load_final(draft)
    niche = load_niche(final.get("niche"))
    issues = risk.check(final, niche, draft, mode=args.mode)
    save_json(draft / "check.json", {"issues": issues, "blocked": risk.blocked(issues)})
    print(risk.summarize(issues))
    sys.exit(1 if risk.blocked(issues) else 0)


def cmd_cards(args) -> None:
    from .cards import render_cards

    draft = resolve_draft(args.draft)
    final = load_final(draft)
    niche = load_niche(final.get("niche"))
    for p in render_cards(final, niche, draft):
        print(p)


def cmd_export(args) -> None:
    from .export import export_package

    draft = resolve_draft(args.draft)
    final = load_final(draft)
    issues = risk.check(final, load_niche(final.get("niche")), draft, mode="B")
    if risk.blocked(issues):
        print(risk.summarize(issues))
        sys.exit("风控检查未通过，没有导出。")
    print(export_package(final, draft))


def cmd_published(args) -> None:
    draft = resolve_draft(args.draft)
    final = load_final(draft)
    append_published({
        "draft": draft.name,
        "title": final.get("title", ""),
        "niche": final.get("niche"),
        "mode": args.mode,
        "url": args.url or "",
    })
    print(f"已记录：{final.get('title')}")


def cmd_status(args) -> None:
    s = load_settings()
    pub = read_published()
    print(json.dumps({
        "active_niche": s["active_niche"],
        "publish_mode": s["publish_mode"],
        "daily_post_limit": s["daily_post_limit"],
        "published_total": len(pub),
        "last_published": pub[-1] if pub else None,
    }, ensure_ascii=False, indent=2))


def main(argv=None) -> None:
    # Windows 下被 Claude Code 捕获输出时默认编码可能不是 UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m harness")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("variants", help="用 DeepSeek 和豆包生成初稿")
    p.add_argument("idea")
    p.add_argument("--brief", help="Claude 写的选题策划")
    p.add_argument("--niche")
    p.set_defaults(func=cmd_variants)

    p = sub.add_parser("check", help="风控检查定稿")
    p.add_argument("draft", nargs="?")
    p.add_argument("--mode", choices=["A", "B"])
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("cards", help="渲染文字卡片")
    p.add_argument("draft", nargs="?")
    p.set_defaults(func=cmd_cards)

    p = sub.add_parser("export", help="模式 B：导出手机发布包")
    p.add_argument("draft", nargs="?")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("published", help="记录一篇已发布的笔记")
    p.add_argument("draft", nargs="?")
    p.add_argument("--mode", choices=["A", "B"], default="B")
    p.add_argument("--url")
    p.set_defaults(func=cmd_published)

    p = sub.add_parser("status", help="查看当前设置和发布记录")
    p.set_defaults(func=cmd_status)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
