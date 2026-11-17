"""セキュリティに関係する Streamlit の設定の「今の値」を表示するスクリプト。

`.streamlit/config.toml`・環境変数・初期値を合わせた、実際に使われる値を表示する。
（チェック対象のアプリのフォルダで、そのアプリの仮想環境の Python で実行する）

使い方:
    .venv\\Scripts\\python -I <このファイルのパス>
"""

from __future__ import annotations

import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

try:
    import streamlit
    from streamlit import config
except ImportError:
    print("streamlit が見つかりません。アプリの仮想環境の Python で実行してください。")
    sys.exit(1)

OPTIONS = [
    ("server.address", "待ち受けるアドレス。None（未設定）だと他の端末からも開ける場合がある"),
    ("server.port", "ポート番号"),
    ("server.enableXsrfProtection", "XSRF 対策（False は危険）"),
    ("server.enableCORS", "CORS 対策（False は危険）"),
    ("server.enableStaticServing", "static/ フォルダの中身を URL で公開するか"),
    ("server.maxUploadSize", "アップロードできるファイルの最大サイズ（MB）"),
    ("client.showErrorDetails", "エラーの詳細（トレースバック）を画面に出すか"),
    ("browser.gatherUsageStats", "Streamlit への利用統計の送信"),
]

print(f"streamlit {streamlit.__version__}")
for key, note in OPTIONS:
    try:
        value = config.get_option(key)
    except Exception:  # noqa: BLE001  （バージョンによっては無い設定）
        value = "（このバージョンには無い設定）"
    print(f"  {key} = {value!r}    # {note}")
