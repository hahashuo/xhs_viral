from harness import config
from tests.helpers import TempRepoTestCase


class SettingsTest(TempRepoTestCase):
    def test_load_settings(self):
        s = config.load_settings()
        self.assertEqual(s["active_niche"], "北美职场")
        self.assertEqual(s["publish_mode"], "B")
        self.assertEqual(s["limits"]["title_max_chars"], 20)

    def test_repo_harness_toml_is_valid(self):
        """真实仓库里的 harness.toml 必须能解析且字段齐全。"""
        import tomllib
        from tests.helpers import REAL_ROOT

        with open(REAL_ROOT / "harness.toml", "rb") as f:
            s = tomllib.load(f)
        for key in ("active_niche", "publish_mode", "daily_post_limit", "min_hours_between_posts"):
            self.assertIn(key, s)
        self.assertIn(s["publish_mode"], ("A", "B"))
        self.assertTrue((REAL_ROOT / "niches" / s["active_niche"]).is_dir())


class NicheTest(TempRepoTestCase):
    def test_load_active_niche_by_default(self):
        n = config.load_niche()
        self.assertEqual(n.name, "北美职场")
        self.assertIn("北美求职", n.text("tags.md"))

    def test_load_named_niche(self):
        n = config.load_niche("_template")
        self.assertEqual(n.name, "_template")

    def test_missing_niche_lists_available_without_template(self):
        with self.assertRaises(SystemExit) as cm:
            config.load_niche("不存在")
        msg = str(cm.exception.code)
        self.assertIn("北美职场", msg)
        self.assertNotIn("_template", msg)

    def test_missing_file_reads_as_empty(self):
        (self.root / "niches" / "北美职场" / "insights.md").unlink()
        n = config.load_niche()
        self.assertEqual(n.text("insights.md"), "")

    def test_prompt_context_includes_files_and_skips_empty(self):
        d = self.root / "niches" / "北美职场"
        (d / "persona.md").write_text("   \n", encoding="utf-8")
        ctx = config.load_niche().as_prompt_context()
        self.assertIn("### style.md", ctx)
        self.assertIn("### topics.md", ctx)
        self.assertNotIn("### persona.md", ctx)


class PublishedLogTest(TempRepoTestCase):
    def test_empty_when_no_log(self):
        self.assertEqual(config.read_published(), [])

    def test_append_then_read(self):
        config.append_published({"title": "a"})
        config.append_published({"title": "中文标题"})
        recs = config.read_published()
        self.assertEqual([r["title"] for r in recs], ["a", "中文标题"])
        self.assertIn("published_at", recs[0])
        self.assertIn("中文标题", config.PUBLISHED_LOG.read_text(encoding="utf-8"))

    def test_creates_state_dir(self):
        import shutil

        shutil.rmtree(self.root / "state")
        config.append_published({"title": "a"})
        self.assertEqual(len(config.read_published()), 1)

    def test_blank_lines_ignored(self):
        config.PUBLISHED_LOG.write_text('{"title": "a"}\n\n  \n{"title": "b"}\n', encoding="utf-8")
        self.assertEqual(len(config.read_published()), 2)
