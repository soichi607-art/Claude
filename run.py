"""Start SoA EDM Studio.

    python run.py            # http://127.0.0.1:8000
    python run.py --open     # ブラウザも自動で開く
    python run.py --check    # 起動せず前提チェックだけ行う
"""
from __future__ import annotations

import argparse
import shutil
import sys
import threading
import webbrowser

from app.config import settings


def preflight() -> list[str]:
    """Return a list of problems (empty = OK). Never guesses; only reports what it can see."""
    problems: list[str] = []
    if sys.version_info < (3, 11):
        problems.append(f"Python 3.11 以上が必要です（現在 {sys.version.split()[0]}）")
    elif sys.version_info >= (3, 15):
        problems.append(f"[注意] Python {sys.version.split()[0]} は未検証です（3.11〜3.14 で確認）。依存パッケージが入れば動作します")
    from app.services.ffmpeg import find_binary

    for binary in ("ffmpeg", "ffprobe"):
        if not find_binary(binary):
            problems.append(
                f"{binary} が見つかりません。次のどれかで用意してください: "
                "(a) Windows: コマンドプロンプトで  winget install -e --id Gyan.FFmpeg  → 新しいウィンドウで再実行 / "
                "(b) ダウンロードした FFmpeg の zip を解凍し、そのフォルダごと このアプリの tools フォルダに入れる（bin を探す必要はありません） / "
                "(c) .env の SOA_FFMPEG と SOA_FFPROBE に ffmpeg.exe / ffprobe.exe のフルパスを書く"
            )
    for mod in ("fastapi", "uvicorn", "sqlmodel", "jinja2", "multipart", "itsdangerous", "httpx", "PIL", "numpy", "librosa", "soundfile", "psutil"):
        try:
            __import__(mod)
        except ImportError:
            problems.append(f"Python パッケージ {mod} が未インストールです → pip install -r requirements.txt")
    if not settings.is_localhost and not (settings.auth_user and settings.auth_password):
        problems.append("LAN公開 (SOA_HOST != 127.0.0.1) には .env の SOA_AUTH_USER / SOA_AUTH_PASSWORD が必須です")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="SoA EDM Studio")
    ap.add_argument("--open", action="store_true", help="起動後にブラウザを開く")
    ap.add_argument("--check", action="store_true", help="前提チェックのみ実行")
    args = ap.parse_args()
    problems = preflight()
    url = f"http://{'127.0.0.1' if settings.is_localhost else settings.host}:{settings.port}"
    if problems:
        print("=== 前提チェック: 問題あり ===")
        for p in problems:
            print(" - " + p)
        if args.check or any("Python パッケージ" in p or "が見つかりません" in p or "以上が必要" in p for p in problems):
            return 1
    else:
        print("=== 前提チェック: OK ===")
    if args.check:
        print(f"起動コマンド: python run.py --open  → {url}")
        return 0
    import uvicorn

    print(f"SoA EDM Studio を起動します → {url}  （終了は Ctrl+C）")
    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False, workers=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
