import io
import json
from contextlib import redirect_stdout
from unittest import mock

from harness import config
from harness.__main__ import main
from tests.helpers import TempRepoTestCase, good_final


class CliTestCase(TempRepoTestCase):
    def run_cli(self, *argv):
        buf = io.StringIO()
        code = 0
        with redirect_stdout(buf):
            try:
                main(list(argv))
            except SystemExit as e:
                code = e.code
        return code, buf.getvalue()


class VariantsCmdTest(CliTestCase):
    def test_writes_variant_files(self):
        fake = [{"provider": "deepseek", "title": "标题A"}, {"provider": "doubao", "error": "未配置"}]
        with mock.patch("harness.llm.generate_variants", return_value=fake) as gen:
            code, out = self.run_cli("variants", "裁员后第一周", "--brief", "策划内容")
        self.assertEqual(code, 0)
        gen.assert_called_once()
        self.assertEqual(gen.call_args.args[1:], ("裁员后第一周", "策划内容"))
        d = next((self.root / "drafts").iterdir())
        self.assertEqual(json.loads((d / "variants" / "deepseek.json").read_text(encoding="utf-8"))["title"], "标题A")
        self.assertTrue((d / "variants" / "doubao.json").exists())
        self.assertEqual((d / "brief.md").read_text(encoding="utf-8").strip(), "策划内容")
        self.assertIn("[deepseek] 「标题A」", out)
        self.assertIn("[doubao] 失败", out)

    def test_unknown_niche(self):
        code, _ = self.run_cli("variants", "x", "--niche", "不存在")
        self.assertNotEqual(code, 0)


class CheckCmdTest(CliTestCase):
    def test_pass_exits_zero_and_writes_report(self):
        d = self.make_draft(final=good_final())
        code, out = self.run_cli("check")
        self.assertEqual(code, 0)
        report = json.loads((d / "check.json").read_text(encoding="utf-8"))
        self.assertFalse(report["blocked"])

    def test_block_exits_one(self):
        self.make_draft(final=good_final(body="加微 abc"))
        code, out = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("必须修改", out)

    def test_mode_flag(self):
        self.make_draft(final=good_final())
        code, out = self.run_cli("check", "--mode", "A")
        self.assertEqual(code, 1)
        self.assertIn("AI 标注", out)

    def test_named_draft(self):
        self.make_draft("20260101-0900-bad", final=good_final(title=""))
        self.make_draft("20260102-0900-good", final=good_final())
        self.assertEqual(self.run_cli("check", "20260101-0900-bad")[0], 1)
        self.assertEqual(self.run_cli("check")[0], 0)

    def test_missing_final(self):
        self.make_draft()
        code, _ = self.run_cli("check")
        self.assertIn("final.json", str(code))


class CardsCmdTest(CliTestCase):
    def test_calls_renderer(self):
        d = self.make_draft(final=good_final())
        with mock.patch("harness.cards.render_cards", return_value=[d / "cards" / "card_01.png"]) as r:
            code, out = self.run_cli("cards")
        self.assertEqual(code, 0)
        self.assertEqual(r.call_args.args[2], d)
        self.assertIn("card_01.png", out)


class ExportCmdTest(CliTestCase):
    def test_exports_when_clean(self):
        d = self.make_draft(final=good_final())
        code, out = self.run_cli("export")
        self.assertEqual(code, 0)
        self.assertTrue((d / "发布包" / "1_标题.txt").exists())

    def test_refuses_when_blocked(self):
        d = self.make_draft(final=good_final(body="电话 13812345678"))
        code, out = self.run_cli("export")
        self.assertIn("没有导出", str(code))
        self.assertFalse((d / "发布包").exists())


class PublishedAndStatusTest(CliTestCase):
    def test_published_records_and_status_reports(self):
        self.make_draft("20260101-0900-a", final=good_final())
        code, out = self.run_cli("published", "--url", "https://xhs.example/1")
        self.assertEqual(code, 0)
        rec = config.read_published()[-1]
        self.assertEqual(rec["title"], good_final()["title"])
        self.assertEqual(rec["mode"], "B")
        self.assertEqual(rec["url"], "https://xhs.example/1")
        self.assertEqual(rec["draft"], "20260101-0900-a")

        code, out = self.run_cli("status")
        status = json.loads(out)
        self.assertEqual(status["published_total"], 1)
        self.assertEqual(status["active_niche"], "北美职场")

    def test_published_then_same_title_is_blocked(self):
        self.make_draft("20260101-0900-a", final=good_final())
        self.run_cli("published")
        self.make_draft("20260102-0900-b", final=good_final())
        code, out = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("重复内容", out)

    def test_status_empty(self):
        code, out = self.run_cli("status")
        self.assertIsNone(json.loads(out)["last_published"])


class ArgparseTest(CliTestCase):
    def test_requires_command(self):
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            code, _ = self.run_cli()
        self.assertEqual(code, 2)

    def test_bad_mode(self):
        with mock.patch("sys.stderr", io.StringIO()):
            code, _ = self.run_cli("check", "--mode", "C")
        self.assertEqual(code, 2)
