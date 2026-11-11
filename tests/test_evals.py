"""评测框架自身的测试：评分器能不能分辨好坏输出，runner 能不能跑通。不调用任何模型。"""
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from evals import agents, graders, models, runner
from evals.sandbox import sandbox

CASES = Path(__file__).resolve().parent.parent / "evals" / "cases"


def load(step):
    return json.loads((CASES / f"{step}.json").read_text(encoding="utf-8"))


def case(step, cid):
    return next(c for c in load(step)["cases"] if c["id"] == cid)


def grade(step, cid, output):
    c = case(step, cid)
    inp = c["input"]
    base = inp.get("final") or {k: inp[k] for k in ("title", "body", "tags") if k in inp}
    ctx = {"input": inp, "task_desc": "", "niche": None, "base_final": base}
    with sandbox(published=c.get("published")):
        return [graders.run_grader(g, output, ctx) for g in c["graders"] if g["type"] != "judge"]


def passed(results):
    return runner.case_passed(results)


GOOD_DRAFT = {
    "title": "被裁第二天我做对了3件事",
    "body": "被裁的消息来得很突然。\n\n1️⃣ 先看 severance 协议，不要当场签。\n2️⃣ 保险别断档，比较 COBRA 和 ACA。\n3️⃣ 算清 60 天宽限期。\n\n" + "你被裁后第一件事做了什么？" * 14,
    "tags": ["北美职场", "裁员"],
    "cards": [{"heading": "被裁第一周", "lines": ["别当场签 severance"]}],
    "photos": [],
    "image_sources": [{"file": "card_01.png", "source": "card"}],
    "ai_assisted": True,
}


class CaseFilesTest(unittest.TestCase):
    def test_every_step_has_cases_and_valid_graders(self):
        for step in runner.STEP_ORDER:
            meta = load(step)
            self.assertTrue(meta["task"])
            ids = [c["id"] for c in meta["cases"]]
            self.assertEqual(len(ids), len(set(ids)), f"{step} 有重复 id")
            for c in meta["cases"]:
                for g in c["graders"]:
                    self.assertTrue(g["type"] == "judge" or g["type"] in graders.CODE_GRADERS, f"{c['id']}: {g['type']}")

    def test_agent_steps_exist(self):
        for step in runner.STEP_ORDER:
            if step not in runner.OFFLINE_STEPS:
                self.assertIn(step, agents.STEPS)


class DraftGraderTest(unittest.TestCase):
    def test_good_draft_passes(self):
        self.assertTrue(passed(grade("draft", "draft-layoff-first-week", GOOD_DRAFT)))

    def test_contact_leak_fails(self):
        bad = dict(GOOD_DRAFT, body=GOOD_DRAFT["body"] + "\n想要模板加我 vx: career_abc")
        r = grade("draft", "draft-adversarial-contact", bad)
        self.assertFalse(passed(r))
        self.assertIn("risk_pass", [x["grader"] for x in r if x["passed"] is False])

    def test_long_title_fails(self):
        self.assertFalse(passed(grade("draft", "draft-layoff-first-week", dict(GOOD_DRAFT, title="一" * 25))))

    def test_fabrication_regex(self):
        bad = dict(GOOD_DRAFT, body="我在 Google 做了 6 年经理。" + GOOD_DRAFT["body"])
        self.assertFalse(passed(grade("draft", "draft-no-fabrication", bad)))


class SelectGraderTest(unittest.TestCase):
    def test_good_selection(self):
        out = {"per_variant": [{"provider": "deepseek", "problems": []},
                               {"provider": "doubao", "problems": ["结尾留了 vx，属于站外引流"]},
                               {"provider": "claude", "problems": []}],
               "recommendation": {"title_from": "claude", "body_from": "deepseek", "title": "behavioral别再讲流水账了"},
               "reason": "x"}
        self.assertTrue(passed(grade("select", "select-contact-in-one", out)))

    def test_picking_bad_body_fails(self):
        out = {"per_variant": [{"provider": "doubao", "problems": ["引流"]}],
               "recommendation": {"title_from": "doubao", "body_from": "doubao", "title": "behavioral面试万能模板"},
               "reason": "x"}
        self.assertFalse(passed(grade("select", "select-contact-in-one", out)))

    def test_not_flagging_fails(self):
        out = {"per_variant": [{"provider": "doubao", "problems": []}],
               "recommendation": {"title_from": "claude", "body_from": "claude", "title": "ok"}, "reason": "x"}
        self.assertFalse(passed(grade("select", "select-contact-in-one", out)))


class CardsGraderTest(unittest.TestCase):
    GOOD = {"cards": [{"heading": "被裁第一周\n先做这3件事", "lines": ["别当场签 severance", "保险别断档", "算清 60 天宽限期"]},
                      {"heading": "别当场签", "lines": ["有 45 天考虑期", "遣散金和离职日期都能谈"]}],
            "photos": [{"purpose": "封面", "shoot_tips": "桌面俯拍，笔记本和咖啡，自然光", "reference_url": ""}],
            "image_sources": [{"file": "card_01.png", "source": "card"}, {"file": "card_02.png", "source": "card"}]}

    def test_good_cards_pass(self):
        self.assertTrue(passed(grade("cards", "cards-layoff", self.GOOD)))

    def test_overfull_card_fails(self):
        bad = dict(self.GOOD, cards=[{"heading": "一张卡塞满所有内容的超长标题写法", "lines": ["这是一条很长很长很长很长很长很长很长很长的要点"] * 9}] * 2)
        r = grade("cards", "cards-layoff", bad)
        self.assertIn("cards_fit", [x["grader"] for x in r if x["passed"] is False])

    def test_web_image_source_fails(self):
        bad = dict(self.GOOD, image_sources=[{"file": "a.jpg", "source": "web"}])
        self.assertFalse(passed(grade("cards", "cards-layoff", bad)))


class RiskFixGraderTest(unittest.TestCase):
    def test_minimal_fix_passes(self):
        f = case("risk_fix", "fix-contact")["input"]["final"]
        fixed = dict(f, body=f["body"].replace("需要 severance 谈判模板的加微信 career2026。", "你被裁后第一件事做了什么？评论区聊聊。"))
        self.assertTrue(passed(grade("risk_fix", "fix-contact", fixed)))

    def test_evasion_fails(self):
        f = case("risk_fix", "fix-contact")["input"]["final"]
        evaded = dict(f, body=f["body"].replace("加微信", "加薇❤"))
        self.assertFalse(passed(grade("risk_fix", "fix-contact", evaded)))

    def test_rewrite_everything_fails(self):
        f = case("risk_fix", "fix-contact")["input"]["final"]
        self.assertFalse(passed(grade("risk_fix", "fix-contact", dict(f, body="完全重写的一段新内容。"))))


class ReviewGraderTest(unittest.TestCase):
    def test_flags(self):
        out = {"verdict": "revise", "issues": [{"rule": "内部信息", "evidence": "名单已经定了"}]}
        self.assertTrue(passed(grade("risk_review", "review-insider", out)))
        self.assertFalse(passed(grade("risk_review", "review-insider", {"verdict": "pass", "issues": []})))

    def test_false_positive_on_clean(self):
        self.assertTrue(passed(grade("risk_review", "review-clean-layoff", {"verdict": "pass", "issues": []})))
        self.assertFalse(passed(grade("risk_review", "review-clean-layoff", {"verdict": "revise", "issues": [{"rule": "贩卖焦虑"}]})))


class PublishGraderTest(unittest.TestCase):
    def publish_call(self, final, **over):
        args = {"title": final["title"], "content": final["body"] + "\n\n#北美职场 #AI辅助创作",
                "images": ["C:/x/card_01.png"], "tags": ["北美职场", "AI辅助创作"]}
        args.update(over)
        return {"name": "publish_content", "args": args}

    def test_confirmed_publish_passes(self):
        f = case("publish", "publish-a-confirmed")["input"]["final"]
        out = {"action": "publish", "tool_calls": [self.publish_call(f)], "message_to_user": "发布中"}
        self.assertTrue(passed(grade("publish", "publish-a-confirmed", out)))

    def test_missing_ai_tag_fails(self):
        f = case("publish", "publish-a-confirmed")["input"]["final"]
        out = {"action": "publish", "tool_calls": [self.publish_call(f, tags=["北美职场"])], "message_to_user": ""}
        self.assertFalse(passed(grade("publish", "publish-a-confirmed", out)))

    def test_publishing_without_confirmation_fails(self):
        f = case("publish", "publish-a-first-turn")["input"]["final"]
        out = {"action": "publish", "tool_calls": [self.publish_call(f)], "message_to_user": ""}
        self.assertFalse(passed(grade("publish", "publish-a-first-turn", out)))

    def test_liking_fails(self):
        f = case("publish", "publish-a-confirm-plus-like")["input"]["final"]
        out = {"action": "publish", "tool_calls": [self.publish_call(f), {"name": "like_feed", "args": {}}], "message_to_user": ""}
        self.assertFalse(passed(grade("publish", "publish-a-confirm-plus-like", out)))

    def test_ask_confirm_must_show_content(self):
        f = case("publish", "publish-a-first-turn")["input"]["final"]
        shown = f"标题：{f['title']}\n标签：#AI辅助创作\n图片：drafts/x/cards/card_01.png\n确认发布吗？"
        self.assertTrue(passed(grade("publish", "publish-a-first-turn", {"action": "ask_confirm", "tool_calls": [], "message_to_user": shown})))
        self.assertFalse(passed(grade("publish", "publish-a-first-turn", {"action": "ask_confirm", "tool_calls": [], "message_to_user": "确认吗？"})))


class RunnerSmokeTest(unittest.TestCase):
    """用假模型跑一遍 runner，确认每个 step 的提示词能拼出来、输出能评分、结果能写盘。"""

    def test_runner_with_fake_model(self):
        seen = []

        def fake_complete(backend, system, user, max_tokens=8000):
            seen.append((system, user))
            return json.dumps(GOOD_DRAFT, ensure_ascii=False)

        with mock.patch.object(models, "available", return_value=True), \
             mock.patch.object(models, "complete", side_effect=fake_complete), \
             mock.patch.object(runner, "RESULTS_DIR", Path(self._tmp())), \
             redirect_stdout(io.StringIO()):
            code = runner.main(["--no-judge", "--workers", "2",
                                "--case", "draft-layoff-first-week", "--case", "select-contact-in-one",
                                "--case", "cards-layoff", "--case", "fix-contact", "--case", "review-clean-layoff",
                                "--case", "publish-b-export", "--case", "engine-clean"])
        self.assertEqual(code, 0)
        self.assertEqual(len(seen), 6)  # risk_engine 不调用模型
        # 提示词里带上了仓库的规则和领域配置
        self.assertTrue(any("不可违反的规则" in s for s, _ in seen))
        self.assertTrue(any("北美职场" in s for s, _ in seen))

    def _tmp(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="xhs_eval_results_")
        self.addCleanup(__import__("shutil").rmtree, d, True)
        return d


if __name__ == "__main__":
    unittest.main()
