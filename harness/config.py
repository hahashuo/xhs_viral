"""读取 harness.toml、领域配置包和本地状态。"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NICHES_DIR = ROOT / "niches"
RISK_DIR = ROOT / "risk"
DRAFTS_DIR = ROOT / "drafts"
STATE_DIR = ROOT / "state"
TEMPLATES_DIR = ROOT / "templates"
PUBLISHED_LOG = STATE_DIR / "published.jsonl"

NICHE_FILES = ["persona.md", "topics.md", "style.md", "tags.md", "banned.md", "insights.md"]


def load_settings() -> dict:
    with open(ROOT / "harness.toml", "rb") as f:
        return tomllib.load(f)


@dataclass
class Niche:
    name: str
    path: Path
    files: dict[str, str]

    def text(self, filename: str) -> str:
        return self.files.get(filename, "")

    def as_prompt_context(self) -> str:
        parts = []
        for name in NICHE_FILES:
            body = self.files.get(name, "").strip()
            if body:
                parts.append(f"### {name}\n{body}")
        return "\n\n".join(parts)


def load_niche(name: str | None = None) -> Niche:
    name = name or load_settings()["active_niche"]
    path = NICHES_DIR / name
    if not path.is_dir():
        available = sorted(p.name for p in NICHES_DIR.iterdir() if p.is_dir() and not p.name.startswith("_"))
        raise SystemExit(f"找不到领域「{name}」。现有领域：{', '.join(available) or '无'}")
    files = {}
    for fn in NICHE_FILES:
        fp = path / fn
        if fp.exists():
            files[fn] = fp.read_text(encoding="utf-8")
    return Niche(name=name, path=path, files=files)


def read_published() -> list[dict]:
    if not PUBLISHED_LOG.exists():
        return []
    out = []
    for line in PUBLISHED_LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def append_published(record: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    record = {"published_at": datetime.now(timezone.utc).isoformat(), **record}
    with open(PUBLISHED_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
