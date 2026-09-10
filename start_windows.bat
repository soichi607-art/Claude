@echo off
setlocal enabledelayedexpansion
REM ============================================================
REM  SoA EDM Studio - Windows ワンクリック起動
REM  初回: 仮想環境の作成 + 依存インストール + 診断 → 起動
REM  2回目以降: 起動のみ
REM ============================================================
cd /d "%~dp0"
echo [SoA EDM Studio] 起動準備中...

REM ---- Python を探す（3.12 → 3.11 → 3.13 → 3.14 → python の順） ----
set "PY="
for %%V in (3.12 3.11 3.13 3.14) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python が見つかりません。https://www.python.org/downloads/ からインストールし、
  echo         インストール時に "Add python.exe to PATH" にチェックを入れてください。
  pause & exit /b 1
)
for /f "tokens=*" %%i in ('!PY! -c "import sys;print(sys.version.split()[0])"') do set PYVER=%%i
echo [INFO] 使用する Python: !PY! (!PYVER!)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] 仮想環境を作成しています...
  !PY! -m venv .venv || (echo [ERROR] 仮想環境の作成に失敗 & pause & exit /b 1)
)
call ".venv\Scripts\activate.bat"

if not exist ".venv\.deps_installed" (
  echo [2/4] 依存パッケージをインストールしています（初回のみ、数分かかります）...
  python -m pip install --upgrade pip >nul
  python -m pip install -r requirements.txt || (
    echo [ERROR] インストールに失敗しました。上のメッセージを確認してください。
    echo         Python !PYVER! 用のパッケージが無い場合は Python 3.12 を追加インストールして再実行してください。
    pause & exit /b 1
  )
  echo ok> ".venv\.deps_installed"
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo [INFO] .env を作成しました（既定: http://127.0.0.1:8000）
)

REM ---- FFmpeg を探す（PATH / tools フォルダ / winget / ダウンロード フォルダ を自動検索） ----
python -c "import sys; sys.path.insert(0,'.'); from app.services.ffmpeg import find_binary; sys.exit(0 if (find_binary('ffmpeg') and find_binary('ffprobe')) else 1)" >nul 2>&1
if errorlevel 1 (
  echo.
  echo [WARN] FFmpeg が見つかりません。次のどちらかで用意してください。
  echo   A) このウィンドウで自動インストール（Microsoft の winget 公式リポジトリの Gyan.FFmpeg を使用）
  echo   B) ダウンロードした FFmpeg の zip を解凍し、フォルダごと "%~dp0tools" に入れる（bin を探す必要はありません）
  echo.
  set /p INSTALLFF="A を実行しますか？ (Y/N): "
  if /i "!INSTALLFF!"=="Y" (
    winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
    echo.
    echo [INFO] インストールが終わったら、このウィンドウを閉じて start_windows.bat をもう一度実行してください（PATH の反映に新しいウィンドウが必要です）。
    pause & exit /b 0
  )
  echo [INFO] B の手順の後、start_windows.bat をもう一度実行してください。
  pause & exit /b 1
)

if not exist "docs\HARDWARE_REPORT.md" (
  echo [3/4] ハードウェア診断を実行しています...
  python scripts\diagnose.py >nul
)

echo [4/4] 起動します。ブラウザが自動で開きます（終了はこのウィンドウで Ctrl+C）。
python run.py --open
pause
