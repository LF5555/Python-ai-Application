"""Google Gemini API とのやり取りをまとめたモジュール。

公式 SDK は使わず、REST API（streamGenerateContent?alt=sse）に requests で接続しています。
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import requests

API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# 日本語の文章作成向けのおすすめモデル（上ほどおすすめ）。一覧に無いものは無視される。
PREFERRED_MODELS = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
]

# 文章作成に向かないモデル（音声・画像・音楽・エージェント用など）を除外
_EXCLUDE = (
    "tts", "image", "banana", "lyria", "transcribe", "robotics",
    "computer-use", "antigravity", "deep-research", "customtools", "embedding",
)


class GeminiError(Exception):
    pass


def _headers(api_key: str) -> dict:
    return {"x-goog-api-key": api_key}


def list_text_models(api_key: str) -> list[str]:
    """テキスト生成モデルの一覧を返す（おすすめ順）。失敗時はおすすめリストを返す。"""
    try:
        r = requests.get(
            f"{API_BASE}/models",
            headers=_headers(api_key),
            params={"pageSize": 1000},
            timeout=20,
        )
        r.raise_for_status()
        names = {
            m["name"].removeprefix("models/")
            for m in r.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        }
        names = {n for n in names if not any(x in n for x in _EXCLUDE)}
        if not names:
            return PREFERRED_MODELS
        preferred = [m for m in PREFERRED_MODELS if m in names]
        return preferred + sorted(names - set(preferred))
    except Exception:
        return PREFERRED_MODELS


def _error_message(r: requests.Response) -> str:
    try:
        msg = r.json()["error"]["message"]
    except Exception:
        msg = r.text[:300]
    if r.status_code in (400, 401, 403) and "API key" in msg:
        return f"認証に失敗しました。.env の GEMINI_API_KEY を確認してください。（{msg}）"
    if r.status_code == 429:
        return f"利用上限に達しました。少し待つか、別のモデルを選んでください。（{msg}）"
    return f"HTTP {r.status_code}: {msg}"


def stream_generate(
    api_key: str,
    model: str,
    messages: list[dict],
    system_instruction: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 8192,
) -> Iterator[str]:
    """会話履歴を渡してストリーミングでテキストを生成する。

    messages: [{"role": "user" | "model", "text": "..."}]
    """
    body: dict = {
        "contents": [
            {"role": m["role"], "parts": [{"text": m["text"]}]} for m in messages
        ],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
    }
    if system_instruction:
        body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

    r = requests.post(
        f"{API_BASE}/models/{model}:streamGenerateContent",
        headers=_headers(api_key),
        params={"alt": "sse"},
        json=body,
        stream=True,
        timeout=(10, 300),
    )
    if r.status_code != 200:
        raise GeminiError(_error_message(r))

    started = False  # 先頭の空行を取り除くため
    got_content = False
    finish_reason = None
    block_reason = None
    with r:
        for raw in r.iter_lines():
            # 日本語が壊れないよう、バイト列を自分で UTF-8 デコードする
            line = raw.decode("utf-8", errors="replace")
            if not line.startswith("data:"):
                continue
            try:
                obj = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            block_reason = (obj.get("promptFeedback") or {}).get("blockReason") or block_reason
            for cand in obj.get("candidates") or []:
                finish_reason = cand.get("finishReason") or finish_reason
                for part in (cand.get("content") or {}).get("parts") or []:
                    text = part.get("text") or ""
                    if not text or part.get("thought"):  # 考える過程は表示しない
                        continue
                    if not started:
                        text = text.lstrip()
                        if not text:
                            continue
                        started = True
                    got_content = True
                    yield text

    if not got_content:
        if block_reason or finish_reason in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"):
            raise GeminiError("安全性の判定により回答がブロックされました。入力内容を変えて試してください。")
        raise GeminiError(
            "回答が空でした。考える処理で出力上限を使い切った可能性があります。"
            "サイドバーの「最大出力トークン数」を増やすか、別のモデルを試してください。"
        )
    if finish_reason == "MAX_TOKENS":
        yield "\n\n> ⚠️ 出力上限に達したため途中で終了しました。「続きを書いて」と指示するか、最大出力トークン数を増やしてください。"
