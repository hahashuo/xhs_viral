"""模式 B：导出发布包，你在手机上手动发布。"""
from __future__ import annotations

import shutil
from pathlib import Path


def export_package(final: dict, draft_dir: Path) -> Path:
    out = draft_dir / "发布包"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()

    tags = " ".join(f"#{t}" for t in final.get("tags", []))
    (out / "1_标题.txt").write_text(final.get("title", "") + "\n", encoding="utf-8")
    (out / "2_正文.txt").write_text(final.get("body", "").rstrip() + "\n\n" + tags + "\n", encoding="utf-8")

    n = 0
    for folder in ("photos", "cards"):
        src = draft_dir / folder
        if src.exists():
            for img in sorted(src.iterdir()):
                if img.is_file() and img.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".heic"}:
                    n += 1
                    shutil.copy2(img, out / f"图{n:02d}_{img.name}")

    lines = ["# 发布前清单", "", "- [ ] 用手机小红书发布（不要用电脑网页版）", "- [ ] 勾选「AI 辅助创作」声明" if final.get("ai_assisted", True) else "", "- [ ] 图片顺序：按文件名 图01、图02…", "- [ ] 发布后回到 Claude Code 运行 /published 记一笔", ""]
    photos = final.get("photos", [])
    if photos:
        lines += ["# 拍摄建议", ""]
        for i, p in enumerate(photos, 1):
            lines.append(f"{i}. **{p.get('purpose', '')}**：{p.get('shoot_tips', '')}")
            if p.get("reference_url"):
                lines.append(f"   参考（只看构图，不要直接用）：{p['reference_url']}")
    (out / "3_发布清单.md").write_text("\n".join(l for l in lines if l is not None) + "\n", encoding="utf-8")
    return out
