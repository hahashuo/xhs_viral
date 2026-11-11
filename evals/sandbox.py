"""评测在临时仓库副本里跑：不碰真实的 drafts/ 和 state/，发布记录按用例单独设置。"""
from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from harness import config

REAL_ROOT = Path(__file__).resolve().parent.parent


def hours_ago(h: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()


@contextmanager
def sandbox(published: list[dict] | None = None, settings_override: str | None = None):
    """复制 niches/、risk/、templates/、harness.toml 到临时目录，并把 harness.config 指过去。

    published 里的记录可以用 {"hours_ago": 3} 代替 published_at。
    """
    root = Path(tempfile.mkdtemp(prefix="xhs_eval_"))
    try:
        for name in ("niches", "risk", "templates"):
            shutil.copytree(REAL_ROOT / name, root / name)
        toml = (REAL_ROOT / "harness.toml").read_text(encoding="utf-8")
        if settings_override:
            toml = settings_override
        (root / "harness.toml").write_text(toml, encoding="utf-8")
        (root / "drafts").mkdir()
        (root / "state").mkdir()
        log = root / "state" / "published.jsonl"
        if published:
            with open(log, "w", encoding="utf-8") as f:
                for rec in published:
                    rec = dict(rec)
                    if "hours_ago" in rec:
                        rec["published_at"] = hours_ago(rec.pop("hours_ago"))
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        paths = {
            "ROOT": root,
            "NICHES_DIR": root / "niches",
            "RISK_DIR": root / "risk",
            "DRAFTS_DIR": root / "drafts",
            "STATE_DIR": root / "state",
            "TEMPLATES_DIR": root / "templates",
            "PUBLISHED_LOG": log,
        }
        patches = [mock.patch.object(config, k, v) for k, v in paths.items()]
        for p in patches:
            p.start()
        try:
            yield root
        finally:
            for p in patches:
                p.stop()
    finally:
        shutil.rmtree(root, ignore_errors=True)
