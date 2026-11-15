# ✍️ AI ライティングツール

Python + Streamlit で作った、個人用の AI ライティングツールです。
AI は **Google Gemini** と **Cloudflare Workers AI** を、サイドバーで切り替えて使えます。

## 機能

| ツール | 内容 |
|---|---|
| 📝 ブログ記事作成 | テーマ・読者・SEO キーワードから構成案 / 本文 / メタディスクリプションを作成 |
| ✉️ メール返信 | 受信メールと返信方針から、日本のビジネスマナーに沿った返信文を作成 |
| 📋 文章要約 | 箇条書き・3 行まとめ・Q&A など形式を選んで要約、アクションアイテム抽出も可能 |
| 🔍 校正・推敲 | 修正後の全文＋修正点の表＋改善提案 |
| 🔄 リライト・言い換え | トーン・長さ・対象読者を変えて書き換え |
| 🌐 翻訳 | 用途に合わせた自然な翻訳、ニュアンス解説付きも可能 |
| 📱 SNS 投稿作成 | X / Instagram / LinkedIn などに合わせた投稿文を複数パターン |
| 💡 タイトル・キャッチコピー | タイトル・コピー・件名・商品名の案出し＋おすすめ理由 |
| 🧠 アイデア出し | ブログネタや企画のブレインストーミング |
| 💬 フリー入力 | 自由な指示で文章作成 |

共通機能:
- ストリーミング表示（生成中の文章がリアルタイムで表示されます）
- 生成後に「もっと短く」などの **修正指示をチャットで追加** できます
- Markdown ファイルとして保存 / コピー用テキスト / 文字数表示
- 生成履歴（セッション中のみ保持）
- AI サービスの切り替え（Google Gemini / Cloudflare Workers AI。`.env` にキーがあるものだけ表示）
- モデル選択（選んだサービスのモデル一覧を自動取得、日本語向けのおすすめ順）
- 創造性（temperature）・最大出力トークン数の調整
- 簡易ログイン（`.env` に `APP_AUTH_USER` / `APP_AUTH_PASSWORD` を設定した場合）

## セットアップ

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

`.env.example` を `.env` にコピーして、使いたい AI サービスの認証情報を設定します。
Gemini と Cloudflare は、どちらか片方だけでも動きます。

```
GEMINI_API_KEY=Gemini の API キー
CLOUDFLARE_ACCOUNT_ID=アカウント ID
CLOUDFLARE_API_TOKEN=API トークン（Workers AI の権限付き）
APP_AUTH_USER=ログイン用ユーザー名
APP_AUTH_PASSWORD=ログイン用パスワード
```

Gemini の API キーは、Google AI Studio（https://aistudio.google.com/apikey）で取得できます。

Cloudflare のアカウント ID と API トークンは、Cloudflare ダッシュボードの「AI > Workers AI > REST API を使用」から取得できます。
※ 無料プランでは使えないモデル（Kimi、DeepSeek v4、GLM-5.x など）があります。選ぶとエラーメッセージが表示されます。

## 起動

```powershell
streamlit run app.py
```

## ツールの追加方法

`tools.py` の `TOOLS` リストに `Tool(...)` を追加し、プロンプトを組み立てる関数を書くだけで、
サイドバーと入力フォームに自動で反映されます。
