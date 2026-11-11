"""评测用的模型调用：被测 agent 和评分 judge 都走这里。

后端：
- claude：Anthropic API（ANTHROPIC_API_KEY），模型由 EVAL_CLAUDE_MODEL 指定
- deepseek / doubao：复用 harness.llm 里的配置（DEEPSEEK_API_KEY、DOUBAO_API_KEY 等）
"""
from __future__ import annotations

import os

from harness.llm import PROVIDERS, load_env, parse_json

BACKENDS = ("claude", "deepseek", "doubao")
DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"


class BackendUnavailable(RuntimeError):
    pass


def claude_model() -> str:
    return os.getenv("EVAL_CLAUDE_MODEL") or DEFAULT_CLAUDE_MODEL


def available(backend: str) -> bool:
    load_env()
    if backend == "claude":
        return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))
    p = _provider(backend)
    return p.configured()


def model_name(backend: str) -> str:
    if backend == "claude":
        return claude_model()
    return _provider(backend).model() or "?"


def _provider(name: str):
    for p in PROVIDERS:
        if p.name == name:
            return p
    raise ValueError(f"未知后端：{name}，可选 {', '.join(BACKENDS)}")


def complete(backend: str, system: str, user: str, max_tokens: int = 8000) -> str:
    """单轮调用，返回文本。"""
    load_env()
    if not available(backend):
        raise BackendUnavailable(f"{backend} 没有配置 API key")
    if backend == "claude":
        import anthropic

        client = anthropic.Anthropic()
        # fallbacks="default"：Claude 因安全分类器拒答时，服务端自动换模型重试
        resp = client.beta.messages.create(
            model=claude_model(),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude 拒绝回答")
        return "".join(b.text for b in resp.content if b.type == "text")

    from openai import OpenAI

    p = _provider(backend)
    client = OpenAI(api_key=os.getenv(p.key_env), base_url=p.url())
    resp = client.chat.completions.create(
        model=p.model(),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.7,
    )
    return resp.choices[0].message.content or ""


def complete_json(backend: str, system: str, user: str, max_tokens: int = 8000) -> dict:
    return parse_json(complete(backend, system, user, max_tokens))
