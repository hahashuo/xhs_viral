"""测试工具：每个测试在一个临时仓库副本里运行，不碰真实的 drafts/ 和 state/。"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness import config

REAL_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TOML = """active_niche = "北美职场"
publish_mode = "B"
daily_post_limit = 2
min_hours_between_posts = 4

[limits]
title_max_chars = 20
body_max_chars = 1000
tags_max = 10

[cards]
width = 1080
height = 1440
"""


def good_final(**over) -> dict:
    final = {
        "title": "被裁第二天我做对了3件事",
        "body": "先别慌。第一周最重要的是把 severance 和保险的时间线理清楚。",
        "tags": ["北美职场", "裁员"],
        "cards": [{"heading": "被裁第一周", "lines": ["确认 severance", "处理保险"]}],
        "photos": [],
        "image_sources": [{"file": "card_01.png", "source": "card"}],
        "ai_assisted": True,
        "niche": "北美职场",
    }
    final.update(over)
    return final


class TempRepoTestCase(unittest.TestCase):
    """把 niches/、risk/、templates/ 复制到临时目录，并把 harness.config 的路径指过去。"""

    toml = DEFAULT_TOML

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="xhs_test_"))
        for name in ("niches", "risk", "templates"):
            shutil.copytree(REAL_ROOT / name, self.root / name)
        (self.root / "drafts").mkdir()
        (self.root / "state").mkdir()
        (self.root / "harness.toml").write_text(self.toml, encoding="utf-8")
        paths = {
            "ROOT": self.root,
            "NICHES_DIR": self.root / "niches",
            "RISK_DIR": self.root / "risk",
            "DRAFTS_DIR": self.root / "drafts",
            "STATE_DIR": self.root / "state",
            "TEMPLATES_DIR": self.root / "templates",
            "PUBLISHED_LOG": self.root / "state" / "published.jsonl",
        }
        self._patches = [mock.patch.object(config, k, v) for k, v in paths.items()]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    # 小工具
    def set_toml(self, text: str) -> None:
        (self.root / "harness.toml").write_text(text, encoding="utf-8")

    def make_draft(self, name: str = "20260101-0900-test", final: dict | None = None, cards: int = 1) -> Path:
        d = self.root / "drafts" / name
        (d / "variants").mkdir(parents=True)
        (d / "idea.md").write_text("test idea\n", encoding="utf-8")
        if final is not None:
            (d / "final.json").write_text(json.dumps(final, ensure_ascii=False), encoding="utf-8")
        if cards:
            (d / "cards").mkdir()
            for i in range(1, cards + 1):
                (d / "cards" / f"card_{i:02d}.png").write_bytes(b"\x89PNG")
        return d

    def write_published(self, records: list[dict]) -> None:
        with open(config.PUBLISHED_LOG, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
