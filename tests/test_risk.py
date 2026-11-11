from datetime import datetime, timedelta, timezone

from harness import config, risk
from tests.helpers import TempRepoTestCase, good_final


def ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


class RiskTestCase(TempRepoTestCase):
    def setUp(self):
        super().setUp()
        self.niche = config.load_niche()

    def run_check(self, final=None, mode="B", draft_dir=None):
        return risk.check(final or good_final(), self.niche, draft_dir, mode=mode)

    def rules(self, issues, level="block"):
        return {i["rule"] for i in issues if i["level"] == level}


class LengthTest(RiskTestCase):
    def test_clean_draft_passes(self):
        issues = self.run_check()
        self.assertFalse(risk.blocked(issues), risk.summarize(issues))

    def test_title_exactly_at_limit_ok(self):
        self.assertNotIn("标题长度", self.rules(self.run_check(good_final(title="一" * 20))))

    def test_title_over_limit(self):
        self.assertIn("标题长度", self.rules(self.run_check(good_final(title="一" * 21))))

    def test_empty_title(self):
        self.assertIn("标题", self.rules(self.run_check(good_final(title=""))))

    def test_body_over_limit(self):
        self.assertIn("正文长度", self.rules(self.run_check(good_final(body="字" * 1001))))

    def test_too_many_tags_is_warning(self):
        issues = self.run_check(good_final(tags=[f"t{i}" for i in range(11)]))
        self.assertIn("标签数量", self.rules(issues, "warn"))
        self.assertNotIn("标签数量", self.rules(issues))

    def test_limits_come_from_toml(self):
        self.set_toml((self.root / "harness.toml").read_text(encoding="utf-8").replace("title_max_chars = 20", "title_max_chars = 5"))
        self.assertIn("标题长度", self.rules(self.run_check(good_final(title="六个字的标题"))))


class BannedWordsTest(RiskTestCase):
    def test_global_banned_word(self):
        self.assertIn("敏感词", self.rules(self.run_check(good_final(body="有事加微聊"))))

    def test_case_insensitive(self):
        self.assertIn("敏感词", self.rules(self.run_check(good_final(body="我的 VX 在主页"))))

    def test_niche_banned_word(self):
        self.assertIn("敏感词", self.rules(self.run_check(good_final(body="我们提供付费内推"))))

    def test_banned_word_in_title_tags_and_cards(self):
        self.assertIn("敏感词", self.rules(self.run_check(good_final(title="刷粉技巧"))))
        self.assertIn("敏感词", self.rules(self.run_check(good_final(tags=["闲鱼"]))))
        cards = [{"heading": "x", "lines": ["扫码领取"]}]
        self.assertIn("敏感词", self.rules(self.run_check(good_final(cards=cards))))

    def test_comment_lines_are_not_words(self):
        words = risk.load_banned_words(self.niche)
        self.assertFalse(any(w.startswith("#") for w in words))
        self.assertIn("加微", words)
        self.assertIn("付费内推", words)

    def test_markdown_description_is_not_a_word(self):
        """领域 banned.md 里只有「- 词」算敏感词，说明文字不算。"""
        tpl = config.load_niche("_template")
        words = risk.load_banned_words(tpl)
        self.assertFalse(any("每行一个" in w for w in words))

    def test_common_career_words_are_not_blocked(self):
        body = "第一份工作最好选成长快的团队，这点我可以保证说的是真心话。"
        self.assertNotIn("敏感词", self.rules(self.run_check(good_final(body=body))))


class ContactTest(RiskTestCase):
    def assert_blocked(self, body):
        issues = self.run_check(good_final(body=body))
        self.assertIn("引流", self.rules(issues), body)

    def test_cn_phone(self):
        self.assert_blocked("电话 13812345678")

    def test_na_phone(self):
        self.assert_blocked("call (415) 555-1234")
        self.assert_blocked("415-555-1234")

    def test_email(self):
        self.assert_blocked("发简历到 me@example.com")

    def test_link(self):
        self.assert_blocked("看 https://example.com")
        self.assert_blocked("看 www.example.com")

    def test_wechat_id(self):
        self.assert_blocked("wx: hello_123")

    def test_dm_bait(self):
        self.assert_blocked("需要模板的私信我")
        self.assert_blocked("评论区扣1发你")

    def test_numbers_and_salaries_not_flagged(self):
        body = "base 15万刀，RSU 4年 vest，2026 年 3 月入职，面了 12 家。"
        self.assertNotIn("引流", self.rules(self.run_check(good_final(body=body))))


class AiLabelTest(RiskTestCase):
    def test_mode_b_warns_to_tick_box(self):
        issues = self.run_check(mode="B")
        self.assertIn("AI 标注", self.rules(issues, "warn"))
        self.assertNotIn("AI 标注", self.rules(issues))

    def test_mode_a_requires_tag(self):
        self.assertIn("AI 标注", self.rules(self.run_check(mode="A")))
        ok = self.run_check(good_final(tags=["北美职场", "AI辅助创作"]), mode="A")
        self.assertNotIn("AI 标注", self.rules(ok))

    def test_not_ai_assisted(self):
        issues = self.run_check(good_final(ai_assisted=False), mode="A")
        self.assertNotIn("AI 标注", self.rules(issues) | self.rules(issues, "warn"))

    def test_mode_defaults_to_toml(self):
        self.set_toml((self.root / "harness.toml").read_text(encoding="utf-8").replace('publish_mode = "B"', 'publish_mode = "A"'))
        issues = risk.check(good_final(), self.niche)
        self.assertIn("AI 标注", self.rules(issues))


class ImageSourceTest(RiskTestCase):
    def test_web_image_blocked(self):
        f = good_final(image_sources=[{"file": "x.jpg", "source": "web"}])
        self.assertIn("图片来源", self.rules(self.run_check(f)))

    def test_allowed_sources(self):
        f = good_final(image_sources=[{"file": "a.jpg", "source": "own"}, {"file": "b.jpg", "source": "licensed"}, {"file": "card_01.png", "source": "card"}])
        self.assertNotIn("图片来源", self.rules(self.run_check(f)))

    def test_undeclared_photo_in_folder_blocked(self):
        d = self.make_draft(final=good_final())
        (d / "photos").mkdir()
        (d / "photos" / "from_google.jpg").write_bytes(b"x")
        self.assertIn("图片来源", self.rules(self.run_check(draft_dir=d)))

    def test_declared_photo_ok(self):
        d = self.make_draft(final=good_final())
        (d / "photos").mkdir()
        (d / "photos" / "desk.jpg").write_bytes(b"x")
        f = good_final(image_sources=[{"file": "card_01.png", "source": "card"}, {"file": "desk.jpg", "source": "own"}])
        self.assertNotIn("图片来源", self.rules(self.run_check(f, draft_dir=d)))

    def test_undeclared_cards_are_fine(self):
        d = self.make_draft(final=good_final(), cards=3)
        self.assertNotIn("图片来源", self.rules(self.run_check(good_final(image_sources=[]), draft_dir=d)))

    def test_no_images_warns(self):
        d = self.make_draft(final=good_final(), cards=0)
        self.assertIn("配图", self.rules(self.run_check(draft_dir=d), "warn"))


class HistoryTest(RiskTestCase):
    def test_duplicate_title_blocked(self):
        self.write_published([{"title": "被裁第二天我做对了3件事", "published_at": ago(100)}])
        self.assertIn("重复内容", self.rules(self.run_check()))

    def test_similar_title_warns(self):
        self.write_published([{"title": "被裁第三天我做错了5件事", "published_at": ago(100)}])
        issues = self.run_check()
        self.assertIn("重复内容", self.rules(issues, "warn") | self.rules(issues))

    def test_different_title_ok(self):
        self.write_published([{"title": "谈薪别只看base", "published_at": ago(100)}])
        issues = self.run_check()
        self.assertNotIn("重复内容", self.rules(issues) | self.rules(issues, "warn"))

    def test_only_last_30_compared(self):
        old = [{"title": "被裁第二天我做对了3件事", "published_at": ago(1000)}]
        filler = [{"title": f"别的笔记{i}", "published_at": ago(900 - i)} for i in range(30)]
        self.write_published(old + filler)
        self.assertNotIn("重复内容", self.rules(self.run_check()))

    def test_daily_limit(self):
        self.write_published([{"title": "a", "published_at": ago(10)}, {"title": "b", "published_at": ago(5)}])
        self.assertIn("发布频率", self.rules(self.run_check()))

    def test_old_posts_do_not_count_toward_daily_limit(self):
        self.write_published([{"title": "a", "published_at": ago(30)}, {"title": "b", "published_at": ago(25)}])
        self.assertNotIn("发布频率", self.rules(self.run_check()))

    def test_min_gap_warning(self):
        self.write_published([{"title": "a", "published_at": ago(1)}])
        issues = self.run_check()
        self.assertIn("发布间隔", self.rules(issues, "warn"))
        self.assertNotIn("发布频率", self.rules(issues))

    def test_records_without_timestamp_are_ignored(self):
        self.write_published([{"title": "a"}])
        self.assertFalse(risk.blocked(self.run_check()))


class SummaryTest(RiskTestCase):
    def test_summary_empty(self):
        self.assertIn("通过", risk.summarize([]))
        self.assertFalse(risk.blocked([]))

    def test_summary_groups(self):
        issues = [
            {"level": "block", "rule": "引流", "detail": "x"},
            {"level": "warn", "rule": "配图", "detail": "y"},
        ]
        s = risk.summarize(issues)
        self.assertIn("必须修改（1）", s)
        self.assertIn("建议注意（1）", s)
        self.assertTrue(risk.blocked(issues))
        self.assertFalse(risk.blocked(issues[1:]))
