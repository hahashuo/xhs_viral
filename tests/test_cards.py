import os
import struct
import unittest

from harness import cards, config
from tests.helpers import TempRepoTestCase, good_final

SIZE = {"width": 1080, "height": 1440}


class CardHtmlTest(TempRepoTestCase):
    def setUp(self):
        super().setUp()
        self.tpl = (self.root / "templates" / "card.html").read_text(encoding="utf-8")

    def test_fills_all_placeholders(self):
        html = cards.card_html(self.tpl, "北美职场", {"heading": "标题", "lines": ["一", "二"]}, "1/2", SIZE)
        self.assertNotIn("{{", html)
        self.assertIn("北美职场", html)
        self.assertIn("<li>一</li><li>二</li>", html)
        self.assertIn("1/2", html)
        self.assertIn("1080px", html)

    def test_escapes_html(self):
        html = cards.card_html(self.tpl, "n", {"heading": "<script>x</script>", "lines": ["a & b <i>"]}, "1/1", SIZE)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("a &amp; b &lt;i&gt;", html)

    def test_heading_newline_becomes_br(self):
        html = cards.card_html(self.tpl, "n", {"heading": "第一行\n第二行", "lines": []}, "1/1", SIZE)
        self.assertIn("第一行<br>第二行", html)

    def test_missing_fields(self):
        html = cards.card_html(self.tpl, "n", {}, "1/1", SIZE)
        self.assertIn("<ul></ul>", html)


def chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        kwargs = {"executable_path": os.environ["PW_CHROMIUM_PATH"]} if os.getenv("PW_CHROMIUM_PATH") else {}
        with sync_playwright() as pw:
            pw.chromium.launch(**kwargs).close()
        return True
    except Exception:
        return False


@unittest.skipUnless(chromium_available(), "需要 playwright 和 chromium（python -m playwright install chromium）")
class RenderTest(TempRepoTestCase):
    def png_size(self, path):
        with open(path, "rb") as f:
            head = f.read(24)
        self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n")
        return struct.unpack(">II", head[16:24])

    def test_renders_one_png_per_card(self):
        d = self.make_draft(cards=0)
        final = good_final(cards=[{"heading": "一", "lines": ["a"]}, {"heading": "二", "lines": ["b"]}])
        paths = cards.render_cards(final, config.load_niche(), d)
        self.assertEqual([p.name for p in paths], ["card_01.png", "card_02.png"])
        self.assertEqual(self.png_size(paths[0]), (1080, 1440))

    def test_rerender_removes_stale_cards(self):
        d = self.make_draft(cards=5)
        cards.render_cards(good_final(), config.load_niche(), d)
        self.assertEqual(sorted(p.name for p in (d / "cards").glob("*.png")), ["card_01.png"])

    def test_niche_template_overrides_default(self):
        tdir = self.root / "niches" / "北美职场" / "templates"
        tdir.mkdir()
        (tdir / "card.html").write_text(
            "<html><body style='width:{{width}}px;height:{{height}}px'>{{heading}}{{items}}{{niche}}{{page}}</body></html>",
            encoding="utf-8",
        )
        self.set_toml((self.root / "harness.toml").read_text(encoding="utf-8").replace("width = 1080", "width = 600"))
        d = self.make_draft(cards=0)
        paths = cards.render_cards(good_final(), config.load_niche(), d)
        self.assertEqual(self.png_size(paths[0])[0], 600)
