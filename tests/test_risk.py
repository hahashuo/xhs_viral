import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness import config, risk
from harness.export import export_package


def good_final(**over):
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


class RiskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(config, "PUBLISHED_LOG", self.tmp / "published.jsonl")
        self.patch.start()
        self.niche = config.load_niche("北美职场")

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp)

    def rules(self, issues, level="block"):
        return {i["rule"] for i in issues if i["level"] == level}

    def test_clean_draft_passes_in_mode_b(self):
        issues = risk.check(good_final(), self.niche, mode="B")
        self.assertFalse(risk.blocked(issues), risk.summarize(issues))

    def test_title_too_long(self):
        issues = risk.check(good_final(title="这是一个明显超过二十个字的标题用来测试长度限制是否生效"), self.niche, mode="B")
        self.assertIn("标题长度", self.rules(issues))

    def test_contact_and_banned_words(self):
        issues = risk.check(good_final(body="有问题加我 vx: abc12345"), self.niche, mode="B")
        self.assertIn("引流", self.rules(issues))
        issues = risk.check(good_final(body="我们提供付费内推"), self.niche, mode="B")
        self.assertIn("敏感词", self.rules(issues))

    def test_mode_a_requires_ai_tag(self):
        issues = risk.check(good_final(), self.niche, mode="A")
        self.assertIn("AI 标注", self.rules(issues))
        issues = risk.check(good_final(tags=["北美职场", "AI辅助创作"]), self.niche, mode="A")
        self.assertNotIn("AI 标注", self.rules(issues))

    def test_web_image_blocked(self):
        issues = risk.check(good_final(image_sources=[{"file": "x.jpg", "source": "web"}]), self.niche, mode="B")
        self.assertIn("图片来源", self.rules(issues))

    def test_daily_limit_and_duplicates(self):
        for _ in range(2):
            config.append_published({"title": "被裁第二天我做对了3件事"})
        issues = risk.check(good_final(), self.niche, mode="B")
        self.assertIn("发布频率", self.rules(issues))
        self.assertIn("重复内容", self.rules(issues))

    def test_export_package(self):
        d = self.tmp / "draft"
        (d / "cards").mkdir(parents=True)
        (d / "cards" / "card_01.png").write_bytes(b"png")
        out = export_package(good_final(photos=[{"purpose": "封面", "shoot_tips": "工位俯拍", "reference_url": ""}]), d)
        self.assertTrue((out / "图01_card_01.png").exists())
        self.assertIn("#裁员", (out / "2_正文.txt").read_text(encoding="utf-8"))
        self.assertIn("工位俯拍", (out / "3_发布清单.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
