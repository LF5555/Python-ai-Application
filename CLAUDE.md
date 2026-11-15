# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

個人用の AI ライティングツール（ブログ記事・メール返信・要約・校正・翻訳など 10 ツール）。
Python + Streamlit + **Google Gemini / Cloudflare Workers AI**（サイドバーの「AI サービス」で切り替え）。
一度 Gemini（公式 SDK）から Cloudflare に移行し、その後 Gemini を REST で再追加した経緯がある。`google-genai` は使っておらず、どちらも `requests` で直接呼んでいる。
データベースなし。ユーザーとのやり取りや UI の文言はすべて日本語。

## コマンド（Windows / PowerShell）

```powershell
.venv\Scripts\activate                       # 仮想環境の有効化（.venv は作成・インストール済み）
streamlit run app.py                         # 起動 → http://localhost:8501
.venv\Scripts\python -m streamlit run app.py # 有効化せずに起動
pip install -r requirements.txt              # 依存の再インストール
```

起動手順を説明するときは「ターミナルを開く → activate → 起動」の順に書く。

テスト・リンターの設定はない。動作確認には `streamlit.testing.v1.AppTest` を使う:
- `AppTest.from_file()` には**絶対パス**を渡す（相対パスは呼び出し元のスクリプトの場所から解決される）。
- `app.py` は `import cloudflare_client` / `import gemini_client` とモジュールごと import している。API をモックするなら、AppTest を実行する前に各モジュールの `stream_generate` / `list_text_models` を差し替える。
- stdin から流すスクリプトでは、`load_dotenv()` に `.env` のパスを明示的に渡す（引数なしだと `find_dotenv` の assertion で落ちる）。

## アーキテクチャ

**`tools.py` — ツールはデータ駆動で定義されている**
- 各ツールは `Tool`（入力項目 `fields`、`build_prompt`、`system`、`temperature` の初期値）で、`TOOLS` リストに並んでいる。ツールの追加はここだけで済み、サイドバーとフォームに自動で反映される。
- `Field.kind`（`text` / `textarea` / `select` / `slider` / `checkbox`）を `app.py` の `render_field()` が Streamlit の widget に変換する。widget の key は `f"{tool.id}__{field.key}"`。
- `build_prompt(values)` は `field.key` をキーにした dict を受け取り、`v["key"]` で直接参照する。そのため、項目を消したり名前を変えたりするときは、プロンプト関数も合わせて直すこと。

**`app.py` — 画面の流れとセッション状態**
- ログインゲート: `.env` に `APP_AUTH_USER` と `APP_AUTH_PASSWORD` の**両方**があるときだけ表示され、`st.stop()` で先に進ませない。
- 会話は `ss.conversations[tool_id]` にツールごとに保持する。`conv[0]` はフォームから組み立てたプロンプト全文で、画面には「送信したプロンプト」の expander にだけ出す。それ以降の `user` は `st.chat_input` から入力した修正指示。
- 使える AI サービスは `PROVIDERS`（`.env` に認証情報があるものだけ）。サイドバーの `provider` によって `cached_models()` と `run_generation()` が呼ぶクライアントを切り替える。モデルの selectbox の key は `model_{provider}`。
- 内部のロールは `"user"` / `"model"`。Gemini はそのまま送り、Cloudflare は `cloudflare_client` 側で `"assistant"` に変換している。
- 生成の流れ: フォーム送信または修正指示で `ss.pending = tool.id` を立てる → 結果表示の最後で `run_generation()` が `st.write_stream` でストリーミング表示する → `ss.history` に追加 → `st.rerun()` で保存ボタンなどを描き直す。失敗したときは最後の user メッセージを `pop` して取り消す。
- 生成履歴は `ss.history`（セッション内だけで、再読み込みすると消える）。

**`cloudflare_client.py` — Workers AI**
- OpenAI 互換の `/accounts/{id}/ai/v1/chat/completions` に SSE ストリーミングで接続し、`choices[].delta.content` だけを出力する（旧形式の `response` にも対応）。推論モデルの `reasoning` / `reasoning_content` は表示しない。
- SSE は `iter_lines()` で受け取った**バイト列を自分で UTF-8 デコード**する。`decode_unicode=True` を使うと日本語の JSON が壊れる。
- 推論モデルは考える処理でトークンを使い切って本文が空になることがあるため、`max_tokens` は大きめ（UI の初期値 8192）にしている。本文が空なら `CloudflareAIError`、`finish_reason == "length"` なら末尾に警告を付ける。
- モデル一覧は `/ai/models/search?task=Text Generation` から取得し、`_EXCLUDE` で除外したうえで `PREFERRED_MODELS` を先頭に並べる。
- **Workers の無料プラン**では一部のモデル（Kimi、DeepSeek v4、GLM-5.x など）が 403 になる。`PREFERRED_MODELS` には、無料プランで日本語の生成を確認できたモデルだけを入れている。

**`gemini_client.py` — Google Gemini**
- REST の `/v1beta/models/{model}:streamGenerateContent?alt=sse` に接続（ヘッダー `x-goog-api-key`）。`candidates[].content.parts[].text` を出力し、`thought: true` の部分は表示しない。
- UTF-8 の自前デコード、空の本文でのエラー（`GeminiError`）、`finishReason == "MAX_TOKENS"` での警告は Cloudflare 側と同じ方針。ブロックされたときは専用のメッセージを出す。
- モデル一覧は `/v1beta/models` から `generateContent` 対応のものを取得し、`_EXCLUDE`（音声・画像・音楽・エージェント用など）を除外して `PREFERRED_MODELS` を先頭に並べる。
- 2026-11-16 に `gemini-flash-latest` で日本語の生成を確認済み（短い文でも応答に 2 分以上かかった。原因は未確認）。

## プロジェクトの前提

- 個人用ツール。データベースや複数ユーザー対応は作らない（ログインは `.env` による簡易的なものだけ）。
- Cloudflare は **Workers の無料プラン**で使っている。有料プラン専用のモデルや機能を前提にしない。
- パスに日本語（`Claude練習用`）が含まれる。
- git で管理している（ブランチは `main`、リモートなし）。動作確認できたらこまめにコミットする。`git push` はユーザーの確認を取ってから。

## このプロジェクト固有のルール

※ 説明の仕方・確認を取る作業・`.env` の扱いなどの共通ルールは `C:\Users\tama\.claude\CLAUDE.md` にある。

- コードのコメントと UI の文言は日本語で書く。
- コードを変えたら AppTest（上記参照）で動作確認してから報告する。API 呼び出しを含む確認は、短いテキストで1回だけ行う（無料枠を使うため）。
- 「次にやること」には、反映方法を書く。`.py` を変えた場合は、ブラウザで画面右上の「Rerun」を押すか、ページを再読み込みすれば反映される。`requirements.txt` を変えた場合は、ターミナルで Ctrl + C を押して再起動が必要。`.env` は、**新しい変数の追加**ならページの再読み込みで反映される（`load_dotenv()` が毎回実行されるため）が、**既存の値の変更**は再起動が必要（`load_dotenv()` は読み込み済みの値を上書きしない）。

## 環境変数（`.env`、テンプレートは `.env.example`）

`GEMINI_API_KEY`、または `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN`（少なくともどちらか一方が必須。どちらもない場合はエラーを表示して停止）、`APP_AUTH_USER`、`APP_AUTH_PASSWORD`（任意）。
