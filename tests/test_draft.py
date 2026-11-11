import json

from harness import draft
from tests.helpers import TempRepoTestCase, good_final


class SlugifyTest(TempRepoTestCase):
    def test_removes_windows_illegal_chars(self):
        s = draft.slugify('a/b\\c:d*e?f"g<h>i|j k')
        for ch in '/\\:*?"<>| ':
            self.assertNotIn(ch, s)

    def test_truncates(self):
        self.assertEqual(len(draft.slugify("一" * 50)), 16)

    def test_empty_falls_back(self):
        self.assertEqual(draft.slugify("   "), "draft")
        self.assertEqual(draft.slugify("???"), "draft")


class DraftDirTest(TempRepoTestCase):
    def test_new_draft_dir(self):
        d = draft.new_draft_dir("  被裁员后第一周  ")
        self.assertTrue((d / "variants").is_dir())
        self.assertEqual((d / "idea.md").read_text(encoding="utf-8"), "被裁员后第一周\n")
        self.assertEqual(d.parent, self.root / "drafts")
        self.assertIn("被裁员后第一周", d.name)

    def test_resolve_by_name_and_path(self):
        d = self.make_draft("20260101-0900-a")
        self.assertEqual(draft.resolve_draft("20260101-0900-a"), d)
        self.assertEqual(draft.resolve_draft(str(d)), d)

    def test_resolve_latest(self):
        self.make_draft("20260101-0900-a")
        latest = self.make_draft("20260102-0900-b")
        self.assertEqual(draft.resolve_draft(None), latest)

    def test_resolve_ignores_files(self):
        d = self.make_draft("20260101-0900-a")
        (self.root / "drafts" / ".gitkeep").write_text("")
        self.assertEqual(draft.resolve_draft(None), d)

    def test_resolve_missing(self):
        with self.assertRaises(SystemExit):
            draft.resolve_draft("nope")

    def test_resolve_none_when_empty(self):
        with self.assertRaises(SystemExit) as cm:
            draft.resolve_draft(None)
        self.assertIn("/idea", str(cm.exception.code))

    def test_resolve_none_when_drafts_dir_missing(self):
        (self.root / "drafts").rmdir()
        with self.assertRaises(SystemExit):
            draft.resolve_draft(None)


class FinalJsonTest(TempRepoTestCase):
    def test_load_final_missing(self):
        d = self.make_draft()
        with self.assertRaises(SystemExit):
            draft.load_final(d)

    def test_save_and_load_roundtrip_keeps_chinese(self):
        d = self.make_draft()
        draft.save_json(d / "final.json", good_final())
        raw = (d / "final.json").read_text(encoding="utf-8")
        self.assertIn("被裁第二天", raw)  # 不转义成 \\uXXXX
        self.assertEqual(draft.load_final(d), good_final())

    def test_schema_hint_has_all_fields(self):
        for key in ("title", "body", "tags", "cards", "photos", "image_sources", "ai_assisted"):
            self.assertIn(key, draft.FINAL_SCHEMA_HINT)
        json.dumps(draft.FINAL_SCHEMA_HINT, ensure_ascii=False)
