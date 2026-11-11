import os
from types import SimpleNamespace
from unittest import mock

from harness import config, llm
from tests.helpers import TempRepoTestCase

NO_KEYS = {k: "" for k in ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "DOUBAO_API_KEY", "DOUBAO_MODEL", "DOUBAO_BASE_URL")}


def fake_completion(content: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class ProviderTest(TempRepoTestCase):
    def setUp(self):
        super().setUp()
        self.deepseek, self.doubao = llm.PROVIDERS

    def test_not_configured_without_key(self):
        with mock.patch.dict(os.environ, NO_KEYS):
            self.assertFalse(self.deepseek.configured())
            self.assertFalse(self.doubao.configured())

    def test_deepseek_has_default_model(self):
        with mock.patch.dict(os.environ, {**NO_KEYS, "DEEPSEEK_API_KEY": "k"}):
            self.assertTrue(self.deepseek.configured())
            self.assertEqual(self.deepseek.model(), "deepseek-chat")

    def test_doubao_needs_model(self):
        with mock.patch.dict(os.environ, {**NO_KEYS, "DOUBAO_API_KEY": "k"}):
            self.assertFalse(self.doubao.configured())
        with mock.patch.dict(os.environ, {**NO_KEYS, "DOUBAO_API_KEY": "k", "DOUBAO_MODEL": "ep-1"}):
            self.assertTrue(self.doubao.configured())

    def test_base_url_override(self):
        with mock.patch.dict(os.environ, {**NO_KEYS, "DOUBAO_BASE_URL": "https://x.example/v3"}):
            self.assertEqual(self.doubao.url(), "https://x.example/v3")
        with mock.patch.dict(os.environ, NO_KEYS):
            self.assertIn("volces.com", self.doubao.url())
            self.assertEqual(self.deepseek.url(), "https://api.deepseek.com")


class ParseJsonTest(TempRepoTestCase):
    def test_plain(self):
        self.assertEqual(llm.parse_json('{"title": "a"}'), {"title": "a"})

    def test_fenced(self):
        self.assertEqual(llm.parse_json('```json\n{"title": "a"}\n```'), {"title": "a"})

    def test_surrounding_prose(self):
        self.assertEqual(llm.parse_json('好的，下面是笔记：\n{"title": "a", "tags": ["x"]}\n希望有帮助'), {"title": "a", "tags": ["x"]})

    def test_no_json(self):
        with self.assertRaises(ValueError):
            llm.parse_json("抱歉，我无法完成")

    def test_broken_json(self):
        import json

        with self.assertRaises(json.JSONDecodeError):
            llm.parse_json('{"title": "a",}')


class BuildMessagesTest(TempRepoTestCase):
    def test_contains_niche_limits_banned_and_schema(self):
        msgs = llm.build_messages(config.load_niche(), "裁员后第一周", brief="角度：过来人")
        system, user = msgs[0]["content"], msgs[1]["content"]
        self.assertEqual([m["role"] for m in msgs], ["system", "user"])
        self.assertIn("北美职场", system)
        self.assertIn("不超过 20 字", system)
        self.assertIn("加微", system)  # 全局敏感词
        self.assertIn("image_sources", system)  # 输出格式
        self.assertIn("### style.md", system)
        self.assertIn("裁员后第一周", user)
        self.assertIn("角度：过来人", user)

    def test_no_brief(self):
        msgs = llm.build_messages(config.load_niche(), "idea")
        self.assertNotIn("选题策划", msgs[1]["content"])

    def test_missing_banned_file(self):
        (self.root / "risk" / "banned_words.txt").unlink()
        llm.build_messages(config.load_niche(), "idea")


class CallProviderTest(TempRepoTestCase):
    def setUp(self):
        super().setUp()
        self.env = mock.patch.dict(os.environ, {**NO_KEYS, "DEEPSEEK_API_KEY": "sk-test"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        super().tearDown()

    def test_success(self):
        with mock.patch("openai.OpenAI") as OpenAI:
            OpenAI.return_value.chat.completions.create.return_value = fake_completion('{"title": "t", "body": "b"}')
            out = llm.call_provider(llm.PROVIDERS[0], [{"role": "user", "content": "x"}])
        OpenAI.assert_called_once_with(api_key="sk-test", base_url="https://api.deepseek.com")
        kwargs = OpenAI.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "deepseek-chat")
        self.assertEqual(out, {"title": "t", "body": "b", "provider": "deepseek", "model": "deepseek-chat"})

    def test_unparseable_reply_keeps_raw(self):
        with mock.patch("openai.OpenAI") as OpenAI:
            OpenAI.return_value.chat.completions.create.return_value = fake_completion("不是 JSON")
            out = llm.call_provider(llm.PROVIDERS[0], [])
        self.assertIn("error", out)
        self.assertEqual(out["raw"], "不是 JSON")

    def test_empty_reply(self):
        with mock.patch("openai.OpenAI") as OpenAI:
            OpenAI.return_value.chat.completions.create.return_value = fake_completion(None)
            out = llm.call_provider(llm.PROVIDERS[0], [])
        self.assertIn("error", out)


class GenerateVariantsTest(TempRepoTestCase):
    def setUp(self):
        super().setUp()
        self.no_dotenv = mock.patch.object(llm, "load_env", lambda: None)
        self.no_dotenv.start()

    def tearDown(self):
        self.no_dotenv.stop()
        super().tearDown()

    def test_nothing_configured(self):
        with mock.patch.dict(os.environ, NO_KEYS):
            out = llm.generate_variants(config.load_niche(), "idea")
        self.assertEqual({r["provider"] for r in out}, {"deepseek", "doubao"})
        self.assertTrue(all("未配置" in r["error"] for r in out))

    def test_one_configured(self):
        with mock.patch.dict(os.environ, {**NO_KEYS, "DEEPSEEK_API_KEY": "k"}), \
             mock.patch.object(llm, "call_provider", return_value={"provider": "deepseek", "title": "t"}) as call:
            out = llm.generate_variants(config.load_niche(), "idea")
        call.assert_called_once()
        by = {r["provider"]: r for r in out}
        self.assertEqual(by["deepseek"]["title"], "t")
        self.assertIn("DOUBAO_API_KEY", by["doubao"]["error"])

    def test_provider_exception_is_captured(self):
        env = {**NO_KEYS, "DEEPSEEK_API_KEY": "k", "DOUBAO_API_KEY": "k", "DOUBAO_MODEL": "m"}

        def boom(p, messages):
            if p.name == "doubao":
                raise RuntimeError("额度不足")
            return {"provider": p.name, "title": "ok"}

        with mock.patch.dict(os.environ, env), mock.patch.object(llm, "call_provider", side_effect=boom):
            out = llm.generate_variants(config.load_niche(), "idea")
        by = {r["provider"]: r for r in out}
        self.assertEqual(by["deepseek"]["title"], "ok")
        self.assertIn("额度不足", by["doubao"]["error"])
