from harness.export import export_package
from tests.helpers import TempRepoTestCase, good_final


class ExportTest(TempRepoTestCase):
    def test_package_contents(self):
        d = self.make_draft(cards=2)
        out = export_package(good_final(), d)
        self.assertEqual(out, d / "发布包")
        names = sorted(p.name for p in out.iterdir())
        self.assertEqual(names, ["1_标题.txt", "2_正文.txt", "3_发布清单.md", "图01_card_01.png", "图02_card_02.png"])
        self.assertEqual((out / "1_标题.txt").read_text(encoding="utf-8").strip(), "被裁第二天我做对了3件事")
        body = (out / "2_正文.txt").read_text(encoding="utf-8")
        self.assertTrue(body.startswith("先别慌"))
        self.assertTrue(body.rstrip().endswith("#北美职场 #裁员"))

    def test_photos_come_before_cards(self):
        d = self.make_draft(cards=1)
        (d / "photos").mkdir()
        (d / "photos" / "cover.jpg").write_bytes(b"x")
        (d / "photos" / "notes.txt").write_text("not an image")
        out = export_package(good_final(), d)
        imgs = sorted(p.name for p in out.glob("图*"))
        self.assertEqual(imgs, ["图01_cover.jpg", "图02_card_01.png"])

    def test_checklist_has_ai_label_and_shoot_tips(self):
        d = self.make_draft()
        photos = [{"purpose": "封面", "shoot_tips": "工位俯拍", "reference_url": "https://example.com/ref.jpg"}]
        md = (export_package(good_final(photos=photos), d) / "3_发布清单.md").read_text(encoding="utf-8")
        self.assertIn("AI 辅助创作", md)
        self.assertIn("**封面**：工位俯拍", md)
        self.assertIn("不要直接用", md)
        self.assertIn("https://example.com/ref.jpg", md)

    def test_no_ai_label_line_when_not_ai(self):
        d = self.make_draft()
        md = (export_package(good_final(ai_assisted=False), d) / "3_发布清单.md").read_text(encoding="utf-8")
        self.assertNotIn("AI 辅助创作", md)
        self.assertNotIn("拍摄建议", md)

    def test_rerun_replaces_old_package(self):
        d = self.make_draft(cards=2)
        export_package(good_final(), d)
        (d / "cards" / "card_02.png").unlink()
        out = export_package(good_final(), d)
        self.assertFalse((out / "图02_card_02.png").exists())
