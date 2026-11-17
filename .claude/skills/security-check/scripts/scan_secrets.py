"""API キーやパスワードの「直書き」を探すスクリプト。

- git で管理しているファイル、まだ git に入れていない（無視されていない）ファイル、
  git の全履歴（過去のコミット）を調べる。
- `.env` 系のファイル（`.env.example` などのひな形以外）と `secrets.toml` は中身を読まない。
  追跡されているかどうかだけ報告する。
- 見つけた値は先頭 4 文字だけを表示し、残りは伏せ字にする。

使い方（チェック対象のプロジェクトのフォルダで実行）:
    python <このファイルのパス>
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

# 文字化け対策（Windows の PowerShell でも日本語を表示できるように）
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

PATTERNS = [
    ("Google API キー", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("Anthropic API キー", re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}")),
    ("OpenAI 形式の API キー", re.compile(r"sk-(?!ant-)(?:proj-)?[A-Za-z0-9\-_]{20,}")),
    ("Hugging Face トークン", re.compile(r"hf_[A-Za-z0-9]{30,}")),
    ("GitHub トークン", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("AWS アクセスキー", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("秘密鍵", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Bearer トークンの直書き", re.compile(r"Bearer\s+[A-Za-z0-9\-_.]{20,}")),
    (
        "キー・トークン・パスワードの代入",
        re.compile(
            r"(?i)(api[_-]?key|api[_-]?token|secret|password|passwd|token)\w*\s*[:=]\s*"
            r"[\"']([^\"'\s]{8,})[\"']"
        ),
    ),
]

# ダミー値として明らかなもの（.env.example の例など）は無視する
PLACEHOLDER = re.compile(r"(?i)your[-_]|xxx|example|dummy|placeholder|<.*>|\*\*\*")


SAFE_ENV_NAMES = (".env.example", ".env.sample", ".env.template")


def is_env_file(path: str) -> bool:
    """中身を読んではいけない秘密情報のファイルか（.env 系と Streamlit の secrets.toml）。"""
    name = os.path.basename(path)
    if name == "secrets.toml":
        return True
    return name.startswith(".env") and name not in SAFE_ENV_NAMES


def git(*args: str) -> str:
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        capture_output=True,
        check=False,
    )
    return out.stdout.decode("utf-8", errors="replace")


def mask(value: str) -> str:
    return value[:4] + "*" * 8


def scan_line(line: str) -> list[tuple[str, str]]:
    hits = []
    for label, pat in PATTERNS:
        for m in pat.finditer(line):
            value = m.group(m.lastindex or 0)
            if PLACEHOLDER.search(value):
                continue
            hits.append((label, mask(value)))
    return hits


def scan_files(paths: list[str], kind: str) -> list[str]:
    results = []
    for path in paths:
        if not path or is_env_file(path) or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except (UnicodeDecodeError, OSError):
            continue  # 画像などのバイナリは飛ばす
        for no, line in enumerate(lines, 1):
            for label, masked in scan_line(line):
                results.append(f"  [{kind}] {path}:{no}  {label}  {masked}")
    return results


def scan_history() -> list[str]:
    log = git("log", "--all", "-p", "--no-color", "--format=commit %h")
    results = []
    commit = path = ""
    for line in log.splitlines():
        if line.startswith("commit "):
            commit = line.split()[1]
        elif line.startswith("diff --git "):
            path = line.split(" b/", 1)[-1]
        elif line.startswith("+") and not line.startswith("+++"):
            if is_env_file(path):
                continue  # 秘密情報のファイルの中身は見ない（追跡の有無は別に報告する）
            for label, masked in scan_line(line[1:]):
                results.append(f"  [履歴 {commit}] {path}  {label}  {masked}")
    return results


def main() -> int:
    if git("rev-parse", "--is-inside-work-tree").strip() != "true":
        print("git 管理のフォルダではありません。プロジェクトのフォルダで実行してください。")
        return 1

    tracked = git("ls-files", "-z").split("\0")
    untracked = git("ls-files", "-z", "--others", "--exclude-standard").split("\0")

    print("■ .env 系・secrets.toml の状態（中身は読んでいません）")
    tracked_env = [p for p in tracked if p and is_env_file(p)]
    untracked_env = [p for p in untracked if p and is_env_file(p)]
    history_env = sorted({
        p for p in git("log", "--all", "--name-only", "--format=").splitlines()
        if p and is_env_file(p)
    })
    print(f"  git で追跡中: {tracked_env or 'なし'}")
    print(f"  .gitignore で無視されていない（git add で入ってしまう）: {untracked_env or 'なし'}")
    print(f"  過去にコミットされたことがある: {history_env or 'なし'}")

    sections = [
        ("■ git で管理しているファイル", scan_files(tracked, "追跡中")),
        ("■ まだ git に入れていないファイル", scan_files(untracked, "未追跡")),
        ("■ git の履歴（過去のコミット）", scan_history()),
    ]
    total = 0
    for title, hits in sections:
        print(title)
        print("\n".join(hits) if hits else "  見つかりませんでした")
        total += len(hits)

    print(f"\n合計 {total} 件の候補（値は先頭 4 文字以外を伏せています）")
    print("※ 候補は機械的な一致です。本物のキーかどうかは、該当行のコードを読んで判断してください。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
