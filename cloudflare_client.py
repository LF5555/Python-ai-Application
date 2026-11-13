"""Cloudflare Workers AI とのやり取りをまとめたモジュール。

OpenAI 互換エンドポイント (/ai/v1/chat/completions) を使っています。
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import requests

API_BASE = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai"

# 日本語の文章作成に向いていて、無料プランでも動作確認できたモデル（上ほどおすすめ）
PREFERRED_MODELS = [
    "@cf/openai/gpt-oss-120b",
    "@cf/qwen/qwen3.8-27b",
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "@cf/mistralai/mistral-small-3.1-24b-instruct",
    "@cf/google/gemma-4-26b-a4b-it",
    "@cf/openai/gpt-oss-20b",
]

# 文章作成に向かないモデル（LoRA 用・安全判定用・コード専用・特殊用途など）を除外
_EXCLUDE = ("lora", "guard", "coder", "-code", "vision", "clef", "clairic", "phonellm")


class CloudflareAIError(Exception):
    pass


def _headers(api_token: str) -> dict:
    return {"Authorization": f"Bearer {api_token}"}


def list_text_models(account_id: str, api_token: str) -> list[str]:
    """テキスト生成モデルの一覧を返す（おすすめ順）。失敗時はおすすめリストを返す。"""
    try:
        r = requests.get(
            f"{API_BASE.format(account_id=account_id)}/models/search",
            headers=_headers(api_token),
            params={"task": "Text Generation", "per_page": 200},
            timeout=20,
        )
        r.raise_for_status()
        names = {m["name"] for m in r.json().get("result", [])}
        names = {n for n in names if not any(x in n for x in _EXCLUDE)}
        if not names:
            return PREFERRED_MODELS
        preferred = [m for m in PREFERRED_MODELS if m in names]
        return preferred + sorted(names - set(preferred))
    except Exception:
        return PREFERRED_MODELS


def _error_message(r: requests.Response) -> str:
    try:
        msg = r.json()["errors"][0]["message"]
    except Exception:
        msg = r.text[:300]
    if "not available on the Workers Free plan" in msg:
        return "このモデルは Workers の無料プランでは使えません。別のモデルを選んでください。"
    if r.status_code in (401, 403) and "plan" not in msg:
        return f"認証に失敗しました。.env の CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN を確認してください。（{msg}）"
    return f"HTTP {r.status_code}: {msg}"


def stream_generate(
    account_id: str,
    api_token: str,
    model: str,
    messages: list[dict],
    system_instruction: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 8192,
) -> Iterator[str]:
    """会話履歴を渡してストリーミングでテキストを生成する。

    messages: [{"role": "user" | "model", "text": "..."}]
    """
    chat = []
    if system_instruction:
        chat.append({"role": "system", "content": system_instruction})
    chat += [
        {"role": "assistant" if m["role"] == "model" else "user", "content": m["text"]}
        for m in messages
    ]
    body = {
        "model": model,
        "messages": chat,
        "stream": True,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    r = requests.post(
        f"{API_BASE.format(account_id=account_id)}/v1/chat/completions",
        headers=_headers(api_token),
        json=body,
        stream=True,
        timeout=(10, 300),
    )
    if r.status_code != 200:
        raise CloudflareAIError(_error_message(r))

    started = False  # 先頭の空行を取り除くため
    got_content = False
    finish_reason = None
    with r:
        for raw in r.iter_lines():
            line = raw.decode("utf-8", errors="replace")
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            # OpenAI 互換形式（choices[].delta.content）と旧形式（response）の両方に対応
            pieces = [
                (c.get("delta") or {}).get("content") or ""
                for c in obj.get("choices") or []
            ]
            for c in obj.get("choices") or []:
                finish_reason = c.get("finish_reason") or finish_reason
            if isinstance(obj.get("response"), str):
                pieces.append(obj["response"])
            for text in pieces:
                if not text:
                    continue
                if not started:
                    text = text.lstrip()
                    if not text:
                        continue
                    started = True
                got_content = True
                yield text

    if not got_content:
        raise CloudflareAIError(
            "回答が空でした。推論（考える処理）で出力上限を使い切った可能性があります。"
            "サイドバーの「最大出力トークン数」を増やすか、別のモデルを試してください。"
        )
    if finish_reason == "length":
        yield "\n\n> ⚠️ 出力上限に達したため途中で終了しました。「続きを書いて」と指示するか、最大出力トークン数を増やしてください。"
