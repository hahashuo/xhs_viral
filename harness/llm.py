"""调用 DeepSeek 和豆包生成初稿。两家都兼容 OpenAI 接口。

Claude 那一版由 Claude Code 自己在 /idea 指令里写，不需要额外的 API key。
"""
from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .config import RISK_DIR, ROOT, Niche, load_settings
from .draft import FINAL_SCHEMA_HINT


@dataclass
class Provider:
    name: str
    key_env: str
    model_env: str
    base_url: str
    base_url_env: str | None = None
    default_model: str | None = None

    def configured(self) -> bool:
        return bool(os.getenv(self.key_env)) and bool(self.model())

    def model(self) -> str | None:
        return os.getenv(self.model_env) or self.default_model

    def url(self) -> str:
        return (self.base_url_env and os.getenv(self.base_url_env)) or self.base_url


PROVIDERS = [
    Provider("deepseek", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "https://api.deepseek.com", default_model="deepseek-chat"),
    Provider("doubao", "DOUBAO_API_KEY", "DOUBAO_MODEL", "https://ark.cn-beijing.volces.com/api/v3", "DOUBAO_BASE_URL"),
]


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ROOT / ".env")


def build_messages(niche: Niche, idea: str, brief: str = "") -> list[dict]:
    limits = load_settings()["limits"]
    banned = (RISK_DIR / "banned_words.txt").read_text(encoding="utf-8") if (RISK_DIR / "banned_words.txt").exists() else ""
    system = f"""你是一位小红书「{niche.name}」领域的资深创作者，按下面的领域配置写笔记。

{niche.as_prompt_context()}

硬性要求：
- 标题不超过 {limits['title_max_chars']} 字，正文不超过 {limits['body_max_chars']} 字，标签不超过 {limits['tags_max']} 个。
- 只写原创内容，不照搬任何已有笔记的原文。
- 不出现任何联系方式、引流、站外平台名称、谐音或拆字替代，下列词一律不能出现：
{banned}
- 配图以文字卡片和建议作者自己拍摄为主。photos 只写拍摄建议；reference_url 只填参考图链接（可留空），绝不建议直接使用网图。
- 只输出一个 JSON 对象，不要任何解释，字段如下：
{json.dumps(FINAL_SCHEMA_HINT, ensure_ascii=False, indent=2)}
"""
    user = f"idea：{idea}"
    if brief:
        user += f"\n\n选题策划（请按这个方向写）：\n{brief}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("模型没有返回 JSON")
    return json.loads(text[start : end + 1])


def call_provider(p: Provider, messages: list[dict]) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv(p.key_env), base_url=p.url())
    resp = client.chat.completions.create(model=p.model(), messages=messages, temperature=0.9)
    raw = resp.choices[0].message.content or ""
    try:
        data = parse_json(raw)
    except (ValueError, json.JSONDecodeError) as e:
        return {"provider": p.name, "error": f"解析失败：{e}", "raw": raw}
    data["provider"] = p.name
    data["model"] = p.model()
    return data


def generate_variants(niche: Niche, idea: str, brief: str = "") -> list[dict]:
    load_env()
    messages = build_messages(niche, idea, brief)
    ready = [p for p in PROVIDERS if p.configured()]
    results = [
        {"provider": p.name, "error": f"未配置：在 .env 里填写 {p.key_env} 和 {p.model_env}"}
        for p in PROVIDERS
        if not p.configured()
    ]
    if ready:
        with ThreadPoolExecutor(max_workers=len(ready)) as pool:
            futures = {pool.submit(call_provider, p, messages): p for p in ready}
            for fut, p in futures.items():
                try:
                    results.append(fut.result(timeout=180))
                except Exception as e:  # 网络错误、额度不足等
                    results.append({"provider": p.name, "error": str(e)})
    return results
