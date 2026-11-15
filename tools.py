"""ライティングツールの定義。

ツールを追加したいときは TOOLS リストに Tool を 1 つ足すだけで、
サイドバーと入力フォームに自動で反映されます。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

BASE_SYSTEM = (
    "あなたは日本語のプロのライター兼編集者です。"
    "ユーザーの指示に忠実に、自然で読みやすい日本語で書いてください。"
    "前置きや「承知しました」などの挨拶は書かず、成果物だけを Markdown で出力してください。"
)

# ブログ記事作成専用（SEO を意識した書き方の方針）
BLOG_SYSTEM = """あなたは日本語の SEO に詳しいプロの Web ライター兼編集者です。
次の方針で、検索した人の役に立つブログ記事を書いてください。

- 検索意図：キーワードで検索する人が知りたいことと、その奥にある悩みを考え、両方に答える。
- 結論を先に：導入文で、記事の結論と「読むと何が分かるか」を簡潔に示す。
- タイトル：32文字前後にし、主要キーワードをなるべく前半に入れる。
- 見出し：H2/H3 の階層を正しく使う。見出しだけ読んでも内容が分かるようにし、キーワードや関連語を自然に含める。
- キーワード：詰め込まない。関連語や言い換えを自然に使う。
- 読みやすさ：1文は短めにし、段落は2〜4文にする。手順は番号付きリスト、比較は表にする。
- 具体性：具体例や手順を入れる。ただし、確認できない統計・数値・出典は作らず、【要確認：〇〇】と書く。
- 体験：筆者の実体験があると良い箇所には【体験談を追記：〇〇】と書く。
- FAQ：まとめの前に、よくある質問を2〜3個、Q&A 形式で入れる。
- まとめ：要点を箇条書きで振り返り、読者が次にとる行動を示す。

前置きや「承知しました」などの挨拶は書かず、成果物だけを Markdown で出力してください。"""

TONES = ["丁寧・フォーマル", "ビジネス標準", "親しみやすい", "カジュアル", "熱意がある", "落ち着いた・論理的"]


@dataclass
class Field:
    key: str
    label: str
    kind: str = "text"  # text / textarea / select / slider / checkbox
    options: list[str] = field(default_factory=list)
    default: object = None
    help: str | None = None
    required: bool = False
    placeholder: str | None = None
    min_value: int = 0
    max_value: int = 100
    step: int = 1
    height: int = 150


@dataclass
class Tool:
    id: str
    name: str
    icon: str
    description: str
    fields: list[Field]
    build_prompt: Callable[[dict], str]
    system: str = BASE_SYSTEM
    temperature: float = 0.7


def _opt(label: str, value) -> str:
    """値が空でなければ「- ラベル: 値」の行を返す。"""
    if value in (None, "", []):
        return ""
    return f"- {label}: {value}\n"


# ---------------------------------------------------------------------------
# 各ツールのプロンプト
# ---------------------------------------------------------------------------

def blog_prompt(v: dict) -> str:
    mode = v["mode"]
    p = f"以下の条件でブログ記事の{mode}を作成してください。\n\n"
    p += _opt("テーマ", v["theme"])
    p += _opt("想定読者", v["audience"])
    p += _opt("SEO キーワード", v["keywords"])
    p += _opt("トーン", v["tone"])
    p += _opt("目安の文字数", f"{v['length']}文字程度" if mode == "本文" else "")
    p += _opt("含めたい内容・メモ", v["notes"])
    if mode == "構成案":
        p += (
            "\n## 出力形式\n"
            "- タイトル案を 3 つ\n- 記事の狙い（1〜2 文）\n"
            "- 見出し構成（H2 / H3）と各見出しで書く内容の要点\n"
        )
    else:
        p += (
            "\n## 出力形式\n"
            "- 1 行目に `# タイトル`\n- 導入文 → H2/H3 見出しで構成した本文 → まとめ\n"
            "- キーワードは不自然にならない範囲で見出しや本文に含める\n"
            "- 具体例を交え、読者が行動に移せる内容にする\n"
        )
        if v["meta"]:
            p += "- 最後に `---` で区切って、120 文字程度のメタディスクリプションを付ける\n"
    return p


def email_prompt(v: dict) -> str:
    p = "以下のメールへの返信文を作成してください。\n\n"
    p += f"## 受信したメール\n```\n{v['received']}\n```\n\n## 条件\n"
    p += _opt("返信の方針", v["stance"])
    p += _opt("伝えたい要点", v["points"])
    p += _opt("相手との関係", v["relation"])
    p += _opt("トーン", v["tone"])
    p += _opt("自分の名前・署名", v["signature"])
    p += (
        "\n## 出力形式\n- 件名（`件名: Re: ...`）と本文\n"
        "- 日本のビジネスメールの慣習（宛名・挨拶・結び）に沿う\n"
        "- 不明な情報は【　】のプレースホルダーにする\n"
    )
    if v["variations"]:
        p += "- トーンや長さを変えた案を 2 パターン出力し、それぞれ `## 案1` `## 案2` の見出しを付ける\n"
    return p


def summary_prompt(v: dict) -> str:
    p = "以下の文章を要約してください。\n\n"
    p += _opt("要約の形式", v["style"])
    p += _opt("長さ", v["length"])
    p += _opt("特に注目してほしい観点", v["focus"])
    p += "- 原文にない情報は追加しないこと\n"
    if v["keypoints"]:
        p += "- 要約の後に「重要キーワード」と「アクションアイテム（あれば）」も挙げる\n"
    p += f"\n## 原文\n```\n{v['text']}\n```\n"
    return p


def proofread_prompt(v: dict) -> str:
    p = "以下の文章を校正・推敲してください。\n\n"
    p += _opt("チェックの強さ", v["level"])
    p += _opt("文章の用途", v["purpose"])
    p += (
        "\n## 出力形式\n"
        "1. `## 修正後の文章` … 修正を反映した全文\n"
        "2. `## 主な修正点` … 「修正前 → 修正後（理由）」の表\n"
        "3. `## さらに良くするための提案` … 箇条書きで 3 つまで\n"
        f"\n## 対象の文章\n```\n{v['text']}\n```\n"
    )
    return p


def rewrite_prompt(v: dict) -> str:
    p = "以下の文章をリライトしてください。意味や事実は変えないでください。\n\n"
    p += _opt("変換後のトーン", v["tone"])
    p += _opt("長さ", v["length"])
    p += _opt("対象読者", v["audience"])
    p += _opt("その他の指示", v["notes"])
    p += f"\n## 元の文章\n```\n{v['text']}\n```\n"
    return p


def translate_prompt(v: dict) -> str:
    p = f"以下の文章を{v['target']}に翻訳してください。\n\n"
    p += _opt("翻訳スタイル", v["style"])
    p += _opt("文脈・用途", v["context"])
    if v["explain"]:
        p += "- 翻訳の後に `## 補足` として、訳し分けに迷った表現や文化的なニュアンスを日本語で解説する\n"
    else:
        p += "- 翻訳文のみを出力する\n"
    p += f"\n## 原文\n```\n{v['text']}\n```\n"
    return p


def sns_prompt(v: dict) -> str:
    p = f"{v['platform']} 向けの投稿文を {v['count']} パターン作成してください。\n\n"
    p += _opt("投稿の内容・伝えたいこと", v["topic"])
    p += _opt("目的", v["goal"])
    p += _opt("トーン", v["tone"])
    p += _opt("ハッシュタグ", "適切なものを付ける" if v["hashtags"] else "付けない")
    p += _opt("絵文字", "適度に使う" if v["emoji"] else "使わない")
    p += (
        "- プラットフォームの文字数制限や文化に合わせる（X は 140 字程度以内）\n"
        "- 各案は `## 案1` のように見出しを付ける\n"
    )
    return p


def copy_prompt(v: dict) -> str:
    p = f"以下の対象について、{v['kind']}を {v['count']} 個提案してください。\n\n"
    p += _opt("対象（商品・記事・サービスなど）", v["subject"])
    p += _opt("ターゲット", v["audience"])
    p += _opt("訴求したいポイント", v["appeal"])
    p += _opt("テイスト", v["tone"])
    p += "- 番号付きリストで出力し、各案に一言で狙いを添える\n- 最後におすすめ上位 3 つとその理由を書く\n"
    return p


def idea_prompt(v: dict) -> str:
    p = f"以下のテーマについて、{v['kind']}を {v['count']} 個ブレインストーミングしてください。\n\n"
    p += _opt("テーマ", v["theme"])
    p += _opt("前提・条件", v["notes"])
    p += "- ありきたりな案だけでなく、意外性のある案も混ぜる\n- 各案に 1〜2 文の説明を付ける\n"
    return p


def free_prompt(v: dict) -> str:
    return v["prompt"]


# ---------------------------------------------------------------------------
# ツール一覧
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    Tool(
        id="blog",
        name="ブログ記事作成",
        icon="📝",
        description="テーマを入力するだけで、構成案または記事本文を作成します。",
        fields=[
            Field("theme", "記事のテーマ", required=True, placeholder="例: 在宅ワークで集中力を保つ方法"),
            Field("audience", "想定読者", placeholder="例: 在宅勤務を始めたばかりの会社員"),
            Field("keywords", "SEO キーワード（任意）", placeholder="例: 在宅ワーク 集中力 コツ"),
            Field("mode", "作成するもの", kind="select", options=["本文", "構成案"]),
            Field("tone", "トーン", kind="select", options=TONES, default="親しみやすい"),
            Field("length", "文字数の目安", kind="slider", min_value=500, max_value=6000, step=500, default=2000),
            Field("notes", "含めたい内容・メモ（任意）", kind="textarea", height=100),
            Field("meta", "メタディスクリプションも作成する", kind="checkbox", default=True),
        ],
        build_prompt=blog_prompt,
        system=BLOG_SYSTEM,
        temperature=0.8,
    ),
    Tool(
        id="email",
        name="メール返信",
        icon="✉️",
        description="受け取ったメールと伝えたい要点から、返信文を作成します。",
        fields=[
            Field("received", "受信したメール", kind="textarea", required=True, height=200),
            Field("stance", "返信の方針", kind="select",
                  options=["承諾する", "丁寧に断る", "質問・確認する", "お礼を伝える", "日程調整する", "お詫びする", "その他（要点に記入）"]),
            Field("points", "伝えたい要点（任意）", kind="textarea", height=100, placeholder="例: 来週火曜なら対応可能、資料は金曜までに送付"),
            Field("relation", "相手との関係", kind="select", options=["取引先・顧客", "社内の上司", "社内の同僚", "初めての相手", "友人・知人"]),
            Field("tone", "トーン", kind="select", options=TONES, default="ビジネス標準"),
            Field("signature", "自分の名前・署名（任意）"),
            Field("variations", "2 パターン作成する", kind="checkbox", default=False),
        ],
        build_prompt=email_prompt,
        temperature=0.6,
    ),
    Tool(
        id="summary",
        name="文章要約",
        icon="📋",
        description="長い文章・議事録・記事などを、目的に合った形式で要約します。",
        fields=[
            Field("text", "要約したい文章", kind="textarea", required=True, height=250),
            Field("style", "形式", kind="select", options=["箇条書き", "段落（文章）", "3 行まとめ", "見出し付きの構造化", "Q&A 形式"]),
            Field("length", "長さ", kind="select", options=["短め（原文の 1 割程度）", "標準（原文の 2〜3 割程度）", "詳しめ（原文の半分程度）"], default="標準（原文の 2〜3 割程度）"),
            Field("focus", "注目してほしい観点（任意）", placeholder="例: 決定事項と期限"),
            Field("keypoints", "重要キーワード・アクションアイテムも抽出", kind="checkbox", default=False),
        ],
        build_prompt=summary_prompt,
        temperature=0.3,
    ),
    Tool(
        id="proofread",
        name="校正・推敲",
        icon="🔍",
        description="誤字脱字・文法・表現をチェックし、修正版と修正理由を示します。",
        fields=[
            Field("text", "チェックしたい文章", kind="textarea", required=True, height=250),
            Field("level", "チェックの強さ", kind="select",
                  options=["誤字脱字・文法のみ（最小限）", "読みやすさも改善（標準）", "表現まで大きく改善（積極的）"], default="読みやすさも改善（標準）"),
            Field("purpose", "文章の用途（任意）", placeholder="例: 社外向けのお知らせ"),
        ],
        build_prompt=proofread_prompt,
        temperature=0.3,
    ),
    Tool(
        id="rewrite",
        name="リライト・言い換え",
        icon="🔄",
        description="意味を保ったまま、トーンや長さ・対象読者に合わせて書き換えます。",
        fields=[
            Field("text", "元の文章", kind="textarea", required=True, height=200),
            Field("tone", "変換後のトーン", kind="select", options=TONES),
            Field("length", "長さ", kind="select", options=["ほぼ同じ", "短く簡潔に", "詳しく膨らませる"]),
            Field("audience", "対象読者（任意）", placeholder="例: 小学生 / 専門家 / 経営層"),
            Field("notes", "その他の指示（任意）", placeholder="例: 箇条書きにして、専門用語を避ける"),
        ],
        build_prompt=rewrite_prompt,
    ),
    Tool(
        id="translate",
        name="翻訳",
        icon="🌐",
        description="文脈に合わせた自然な翻訳を行います。",
        fields=[
            Field("text", "翻訳したい文章", kind="textarea", required=True, height=200),
            Field("target", "翻訳先の言語", kind="select", options=["英語", "日本語", "中国語（簡体字）", "韓国語", "スペイン語", "フランス語", "ドイツ語"]),
            Field("style", "スタイル", kind="select", options=["自然で読みやすい意訳", "原文に忠実な直訳寄り", "ビジネス向けのフォーマル", "カジュアルな会話調"]),
            Field("context", "文脈・用途（任意）", placeholder="例: 海外の取引先へのメール"),
            Field("explain", "訳のニュアンス解説を付ける", kind="checkbox", default=False),
        ],
        build_prompt=translate_prompt,
        temperature=0.3,
    ),
    Tool(
        id="sns",
        name="SNS 投稿作成",
        icon="📱",
        description="各 SNS の特性に合わせた投稿文を複数パターン作成します。",
        fields=[
            Field("platform", "プラットフォーム", kind="select", options=["X（旧 Twitter）", "Instagram", "Facebook", "LinkedIn", "Threads", "note の紹介文"]),
            Field("topic", "投稿の内容・伝えたいこと", kind="textarea", required=True, height=120),
            Field("goal", "目的", kind="select", options=["認知拡大", "記事・サイトへの誘導", "商品・サービスの宣伝", "イベント告知", "日常・共感"]),
            Field("tone", "トーン", kind="select", options=TONES, default="親しみやすい"),
            Field("count", "パターン数", kind="slider", min_value=1, max_value=5, default=3),
            Field("hashtags", "ハッシュタグを付ける", kind="checkbox", default=True),
            Field("emoji", "絵文字を使う", kind="checkbox", default=True),
        ],
        build_prompt=sns_prompt,
        temperature=0.9,
    ),
    Tool(
        id="copy",
        name="タイトル・キャッチコピー",
        icon="💡",
        description="記事タイトル・キャッチコピー・商品名などの案を大量に出します。",
        fields=[
            Field("kind", "作るもの", kind="select", options=["ブログ記事のタイトル", "キャッチコピー", "メールの件名", "商品・サービス名", "YouTube 動画のタイトル"]),
            Field("subject", "対象（内容の説明）", kind="textarea", required=True, height=120),
            Field("audience", "ターゲット（任意）"),
            Field("appeal", "訴求したいポイント（任意）"),
            Field("tone", "テイスト", kind="select", options=["インパクト重視", "信頼感・誠実", "ユーモア", "シンプル", "数字・具体性重視"]),
            Field("count", "案の数", kind="slider", min_value=5, max_value=30, step=5, default=10),
        ],
        build_prompt=copy_prompt,
        temperature=1.0,
    ),
    Tool(
        id="idea",
        name="アイデア出し",
        icon="🧠",
        description="ブログネタ・企画・切り口などをブレインストーミングします。",
        fields=[
            Field("theme", "テーマ", required=True, placeholder="例: 個人ブログで書けるプログラミング学習のネタ"),
            Field("kind", "出してほしいもの", kind="select", options=["ブログのネタ", "企画・イベント案", "記事の切り口", "問題の解決策", "自由"]),
            Field("notes", "前提・条件（任意）", kind="textarea", height=100),
            Field("count", "案の数", kind="slider", min_value=5, max_value=30, step=5, default=10),
        ],
        build_prompt=idea_prompt,
        temperature=1.0,
    ),
    Tool(
        id="free",
        name="フリー入力",
        icon="💬",
        description="上記に当てはまらない文章作成を、自由な指示で依頼できます。",
        fields=[
            Field("prompt", "指示", kind="textarea", required=True, height=200,
                  placeholder="例: 退職する同僚への寄せ書きメッセージを 3 パターン考えて"),
        ],
        build_prompt=free_prompt,
    ),
]

TOOLS_BY_ID = {t.id: t for t in TOOLS}
