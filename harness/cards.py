"""把 final.json 里的 cards 渲染成 1080x1440 的 PNG 文字卡片。"""
from __future__ import annotations

import html
import os
from pathlib import Path

from .config import TEMPLATES_DIR, Niche, load_settings


def card_html(template: str, niche_name: str, card: dict, page: str, size: dict) -> str:
    items = "".join(f"<li>{html.escape(line)}</li>" for line in card.get("lines", []))
    return (
        template.replace("{{width}}", str(size["width"]))
        .replace("{{height}}", str(size["height"]))
        .replace("{{niche}}", html.escape(niche_name))
        .replace("{{heading}}", html.escape(card.get("heading", "")).replace("\n", "<br>"))
        .replace("{{items}}", items)
        .replace("{{page}}", page)
    )


def render_cards(final: dict, niche: Niche, draft_dir: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright

    size = load_settings()["cards"]
    tpl_path = niche.path / "templates" / "card.html"
    if not tpl_path.exists():
        tpl_path = TEMPLATES_DIR / "card.html"
    template = tpl_path.read_text(encoding="utf-8")

    out_dir = draft_dir / "cards"
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("card_*.png"):
        old.unlink()

    cards = final.get("cards", [])
    paths = []
    launch_args = {}
    if os.getenv("PW_CHROMIUM_PATH"):
        launch_args["executable_path"] = os.environ["PW_CHROMIUM_PATH"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_args)
        page = browser.new_page(viewport={"width": size["width"], "height": size["height"]})
        for i, card in enumerate(cards, 1):
            page.set_content(card_html(template, niche.name, card, f"{i}/{len(cards)}", size))
            path = out_dir / f"card_{i:02d}.png"
            page.screenshot(path=str(path), full_page=False)
            paths.append(path)
        browser.close()
    return paths
