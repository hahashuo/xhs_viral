"""真实调用 DeepSeek 和豆包的集成测试。默认跳过。

在本地运行：
    设置 RUN_LIVE_TESTS=1，并在 .env 里填好 key，然后
    python -m unittest tests.test_live_llm -v
每次运行会产生少量费用（两次调用）。
"""
import os
import unittest

from harness import config, llm

llm.load_env()
LIVE = os.getenv("RUN_LIVE_TESTS") == "1"
PROVIDERS = {p.name: p for p in llm.PROVIDERS}


@unittest.skipUnless(LIVE, "设置 RUN_LIVE_TESTS=1 才运行真实接口测试")
class LiveLlmTest(unittest.TestCase):
    def check_provider(self, name):
        p = PROVIDERS[name]
        if not p.configured():
            self.skipTest(f"{name} 未配置：需要 {p.key_env} 和 {p.model_env}")
        messages = llm.build_messages(config.load_niche(), "刚入职第一个月，怎么和美国老板做 1:1")
        out = llm.call_provider(p, messages)
        self.assertNotIn("error", out, out.get("raw", "")[:500])
        for key in ("title", "body", "tags", "cards"):
            self.assertIn(key, out)
        self.assertTrue(out["title"])
        self.assertIsInstance(out["tags"], list)

    def test_deepseek(self):
        self.check_provider("deepseek")

    def test_doubao(self):
        self.check_provider("doubao")
