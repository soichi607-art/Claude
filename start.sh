#!/usr/bin/env bash
# SoA EDM Studio - macOS / Linux 起動スクリプト（初回はセットアップも行う）
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if ! command -v "$PY" >/dev/null 2>&1; then echo "[ERROR] python3 が見つかりません（3.11 / 3.12 を入れてください）"; exit 1; fi
if [ ! -x .venv/bin/python ]; then echo "[1/4] 仮想環境を作成..."; "$PY" -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
if [ ! -f .venv/.deps_installed ]; then
  echo "[2/4] 依存パッケージをインストール（初回のみ）..."
  python -m pip install --upgrade pip >/dev/null
  python -m pip install -r requirements.txt
  echo ok > .venv/.deps_installed
fi
[ -f .env ] || { cp .env.example .env; echo "[INFO] .env を作成しました"; }
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[WARN] ffmpeg が見つかりません。macOS: brew install ffmpeg / Ubuntu: sudo apt install ffmpeg （公式: https://ffmpeg.org/download.html）"; exit 1
fi
[ -f docs/HARDWARE_REPORT.md ] || { echo "[3/4] ハードウェア診断..."; python scripts/diagnose.py >/dev/null; }
echo "[4/4] 起動します（終了は Ctrl+C）"
exec python run.py --open
