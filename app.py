"""AI ライティングツール（Streamlit + Cloudflare Workers AI / Google Gemini）"""

from __future__ import annotations

import hmac
import os
import re
import time
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

import cloudflare_client
import gemini_client
from tools import TOOLS, TOOLS_BY_ID, Field, Tool

load_dotenv()

st.set_page_config(page_title="AI ライティングツール", page_icon="✍️", layout="wide")

HISTORY_PAGE = "history"

# ---------------------------------------------------------------------------
# セッション状態
# ---------------------------------------------------------------------------
ss = st.session_state
ss.setdefault("conversations", {})  # tool_id -> [{"role", "text"}]
ss.setdefault("history", [])        # 生成履歴（新しい順）
ss.setdefault("pending", None)      # 生成待ちの tool_id


ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
AUTH_USER = os.getenv("APP_AUTH_USER", "")
AUTH_PASSWORD = os.getenv("APP_AUTH_PASSWORD", "")


# 使える AI サービス（.env に認証情報があるものだけ）
PROVIDERS = {}
if GEMINI_API_KEY:
    PROVIDERS["gemini"] = "Google Gemini"
if ACCOUNT_ID and API_TOKEN:
    PROVIDERS["cloudflare"] = "Cloudflare Workers AI"


@st.cache_data(show_spinner=False, ttl=3600)
def cached_models(provider: str) -> list[str]:
    if provider == "gemini":
        return gemini_client.list_text_models(GEMINI_API_KEY)
    return cloudflare_client.list_text_models(ACCOUNT_ID, API_TOKEN)


# ---------------------------------------------------------------------------
# ログイン（.env に APP_AUTH_USER / APP_AUTH_PASSWORD がある場合のみ）
# ---------------------------------------------------------------------------
LOGIN_FAIL_WAIT = 3  # ログイン失敗時に待たせる秒数（パスワードの総当たりを遅くするため）


def _match(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


if AUTH_USER and AUTH_PASSWORD and not ss.get("authenticated"):
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.title("✍️ AI ライティング")
        with st.form("login"):
            user = st.text_input("ユーザー名")
            password = st.text_input("パスワード", type="password")
            if st.form_submit_button("ログイン", type="primary", use_container_width=True):
                if _match(user, AUTH_USER) and _match(password, AUTH_PASSWORD):
                    ss.authenticated = True
                    st.rerun()
                else:
                    with st.spinner("確認しています…"):
                        time.sleep(LOGIN_FAIL_WAIT)
                    st.error("ユーザー名またはパスワードが違います。")
    st.stop()

if not PROVIDERS:
    st.error(
        "AI の認証情報が見つかりません。.env に GEMINI_API_KEY、または "
        "CLOUDFLARE_ACCOUNT_ID と CLOUDFLARE_API_TOKEN を設定して、アプリを再起動してください。"
    )
    st.stop()


# ---------------------------------------------------------------------------
# サイドバー
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("✍️ AI ライティング")

    page = st.radio(
        "ツール",
        [t.id for t in TOOLS] + [HISTORY_PAGE],
        format_func=lambda i: "🕘 生成履歴" if i == HISTORY_PAGE else f"{TOOLS_BY_ID[i].icon} {TOOLS_BY_ID[i].name}",
        label_visibility="collapsed",
    )

    st.divider()
    st.subheader("⚙️ 設定")

    provider = st.radio(
        "AI サービス", list(PROVIDERS), format_func=PROVIDERS.get, horizontal=True,
    )
    models = cached_models(provider)
    model = st.selectbox(
        "モデル", models, index=0,
        key=f"model_{provider}",
        format_func=lambda m: m.split("/")[-1],
        help="上にあるものほど日本語の文章作成におすすめです。無料プランでは使えないモデルもあります。",
    )
    max_tokens = st.select_slider(
        "最大出力トークン数", [1024, 2048, 4096, 8192, 16384], value=8192,
        help="長文が途中で切れる場合は増やしてください。考えてから答えるモデルは多めが安心です。",
    )

    if page != HISTORY_PAGE:
        tool_for_temp = TOOLS_BY_ID[page]
        temperature = st.slider(
            "創造性（temperature）",
            0.0, 2.0, tool_for_temp.temperature, 0.1,
            key=f"temp_{page}",
            help="低いほど正確・安定、高いほど多様で自由な表現になります。",
        )

    if AUTH_USER and AUTH_PASSWORD:
        st.divider()
        if st.button("ログアウト", use_container_width=True):
            ss.authenticated = False
            st.rerun()


# ---------------------------------------------------------------------------
# 共通処理
# ---------------------------------------------------------------------------
def render_field(tool: Tool, f: Field):
    key = f"{tool.id}__{f.key}"
    label = f.label + (" *" if f.required else "")
    if f.kind == "textarea":
        return st.text_area(label, value=f.default or "", key=key, height=f.height,
                            placeholder=f.placeholder, help=f.help)
    if f.kind == "select":
        idx = f.options.index(f.default) if f.default in f.options else 0
        return st.selectbox(label, f.options, index=idx, key=key, help=f.help)
    if f.kind == "slider":
        return st.slider(label, f.min_value, f.max_value, f.default or f.min_value,
                         f.step, key=key, help=f.help)
    if f.kind == "checkbox":
        return st.checkbox(label, value=bool(f.default), key=key, help=f.help)
    return st.text_input(label, value=f.default or "", key=key,
                         placeholder=f.placeholder, help=f.help)


# Markdown の画像（![説明](URL) と ![説明][参照名]）
_MD_IMAGE = re.compile(r"!\[([^\]]*)\](\([^)]*\)|\[[^\]]*\])")


def safe_markdown(text: str) -> str:
    """AI の出力を画面に表示する前に、画像を文字に置き換える。

    画像を表示するとブラウザが URL に自動で接続する。貼り付けた文章に悪意ある指示が
    仕込まれていると、入力内容を含む画像 URL を AI に書かせて、内容を外に送らせる手口があるため。
    （保存用・コピー用のテキストは元のまま）
    """
    return _MD_IMAGE.sub(lambda m: f"［画像は表示しません: {m.group(1) or '説明なし'}］", text)


def run_generation(tool: Tool, conv: list[dict]) -> None:
    """会話の最後のユーザーメッセージに対する応答をストリーミング生成する。"""
    with st.chat_message("assistant", avatar="✨"):
        try:
            if provider == "gemini":
                stream = gemini_client.stream_generate(
                    GEMINI_API_KEY, model, conv, tool.system, temperature, max_tokens)
            else:
                stream = cloudflare_client.stream_generate(
                    ACCOUNT_ID, API_TOKEN, model, conv, tool.system, temperature, max_tokens)
            # 届いた文章を積み上げ、画像を取り除いてから表示し直す
            box = st.empty()
            text = ""
            for chunk in stream:
                text += chunk
                box.markdown(safe_markdown(text))
        except Exception as e:  # noqa: BLE001
            conv.pop()  # 失敗したリクエストは取り消す
            st.error(f"生成に失敗しました: {e}")
            return
    conv.append({"role": "model", "text": text})
    ss.history.insert(0, {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tool": tool.id,
        "request": conv[-2]["text"],
        "output": text,
    })


def output_actions(text: str, tool: Tool, idx: int) -> None:
    c1, c2, _ = st.columns([1, 1, 3])
    c1.download_button(
        "⬇️ Markdown で保存",
        text,
        file_name=f"{tool.id}_{datetime.now():%Y%m%d_%H%M%S}.md",
        mime="text/markdown",
        key=f"dl_{tool.id}_{idx}",
        use_container_width=True,
    )
    c2.caption(f"📏 {len(text):,} 文字")
    with st.expander("📋 コピー用テキスト"):
        st.code(text, language=None, wrap_lines=True)


# ---------------------------------------------------------------------------
# 生成履歴ページ
# ---------------------------------------------------------------------------
if page == HISTORY_PAGE:
    st.header("🕘 生成履歴")
    st.caption("このブラウザのセッション中に生成した結果です（ページを再読み込みすると消えます）。")
    if not ss.history:
        st.info("まだ履歴はありません。")
    else:
        if st.button("🗑️ 履歴をすべて削除"):
            ss.history.clear()
            st.rerun()
        for i, h in enumerate(ss.history):
            t = TOOLS_BY_ID[h["tool"]]
            with st.expander(f"{h['time']}　{t.icon} {t.name}　—　{h['output'][:40]}…"):
                st.markdown(safe_markdown(h["output"]))
                output_actions(h["output"], t, 10_000 + i)
    st.stop()


# ---------------------------------------------------------------------------
# ツールページ
# ---------------------------------------------------------------------------
tool = TOOLS_BY_ID[page]
conv: list[dict] = ss.conversations.setdefault(tool.id, [])

st.header(f"{tool.icon} {tool.name}")
st.caption(tool.description)

with st.form(f"form_{tool.id}"):
    values = {f.key: render_field(tool, f) for f in tool.fields}
    submitted = st.form_submit_button("✨ 生成する", type="primary", use_container_width=True)

if submitted:
    missing = [f.label for f in tool.fields if f.required and not str(values[f.key]).strip()]
    if missing:
        st.warning(f"必須項目を入力してください: {', '.join(missing)}")
    else:
        conv.clear()
        conv.append({"role": "user", "text": tool.build_prompt(values)})
        ss.pending = tool.id

# 修正指示（結果がある時だけ表示）
if conv:
    instruction = st.chat_input("結果への修正指示を入力（例: もっと短く / 見出しを増やして / 敬語を柔らかく）")
    if instruction:
        conv.append({"role": "user", "text": instruction})
        ss.pending = tool.id

# ---- 結果表示 ----
if conv:
    st.divider()
    head_l, head_r = st.columns([4, 1])
    head_l.subheader("生成結果")
    if head_r.button("🧹 クリア", use_container_width=True):
        conv.clear()
        ss.pending = None
        st.rerun()

    with st.expander("送信したプロンプトを確認"):
        st.code(conv[0]["text"], language="markdown", wrap_lines=True)

    for i, msg in enumerate(conv):
        if msg["role"] == "user":
            if i > 0:  # 最初のプロンプト以外（修正指示）は吹き出しで表示
                with st.chat_message("user"):
                    st.markdown(msg["text"])
            continue
        with st.chat_message("assistant", avatar="✨"):
            st.markdown(safe_markdown(msg["text"]))
            if i == len(conv) - 1:
                output_actions(msg["text"], tool, i)

    if ss.pending == tool.id and conv[-1]["role"] == "user":
        ss.pending = None
        run_generation(tool, conv)
        if conv and conv[-1]["role"] == "model":
            st.rerun()  # 保存ボタン等を表示するため再描画
