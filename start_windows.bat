@echo off
setlocal
REM ============================================================
REM  SoA EDM Studio - Windows ワンクリック起動
REM  初回: 仮想環境の作成 + 依存インストール + 診断 → 起動
REM  2回目以降: 起動のみ
REM ============================================================
cd /d "%~dp0"
echo [SoA EDM Studio] 起動準備中...

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python が見つかりません。https://www.python.org/downloads/ から Python 3.11 または 3.12 をインストールし、
  echo         インストール時に "Add Python to PATH" にチェックを入れてください。
  pause & exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] 仮想環境を作成しています...
  python -m venv .venv || (echo [ERROR] 仮想環境の作成に失敗 & pause & exit /b 1)
)
call ".venv\Scripts\activate.bat"

if not exist ".venv\.deps_installed" (
  echo [2/4] 依存パッケージをインストールしています（初回のみ、数分かかります）...
  python -m pip install --upgrade pip >nul
  python -m pip install -r requirements.txt || (echo [ERROR] インストールに失敗 & pause & exit /b 1)
  echo ok> ".venv\.deps_installed"
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo [INFO] .env を作成しました（既定: http://127.0.0.1:8000）
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [WARN] ffmpeg が見つかりません。https://ffmpeg.org/download.html から Windows 用ビルドを入手し、
  echo        bin フォルダを PATH に追加してから、このファイルをもう一度実行してください。
  pause & exit /b 1
)

if not exist "docs\HARDWARE_REPORT.md" (
  echo [3/4] ハードウェア診断を実行しています...
  python scripts\diagnose.py >nul
)

echo [4/4] 起動します。ブラウザが自動で開きます（終了はこのウィンドウで Ctrl+C）。
python run.py --open
pause
