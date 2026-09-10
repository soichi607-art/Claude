@echo off
chcp 65001 >nul
REM このファイルは UTF-8。cmd が Shift-JIS として読まないように、最初にコードページを UTF-8 にする（日本語の行末で改行が飲み込まれる事故を防ぐ）
setlocal enabledelayedexpansion
REM ============================================================
REM  SoA EDM Studio - Windows ワンクリック起動
REM  初回: Python 探索 + 仮想環境の作成 + 依存インストール + 診断 → 起動
REM  2回目以降: 起動のみ（.venv があれば Python の再探索はしない）
REM ============================================================
cd /d "%~dp0"
echo [SoA EDM Studio] 起動準備中...

if exist ".venv\Scripts\python.exe" goto :venv_ready

REM ---- Python を探す ----
REM  順序: py ランチャー(3.12→3.11→3.13→3.14) → python3.12 などの実行ファイル名 → python → uv が管理する Python
REM  Microsoft Store の「案内だけの python」は import に失敗するので自動的に除外されます
set "PY="
for %%V in (3.12 3.11 3.13 3.14) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
for %%V in (3.12 3.11 3.13 3.14) do (
  if not defined PY (
    python%%V -c "import sys" >nul 2>&1 && set "PY=python%%V"
  )
)
if not defined PY (
  python -c "import sys" >nul 2>&1 && set "PY=python"
)
if defined PY goto :make_venv

REM ---- uv があれば、uv が管理する Python で仮想環境を作る（新規ダウンロードはしない） ----
where uv >nul 2>&1 && (
  echo [1/4] uv が管理する Python で仮想環境を作成しています...
  uv venv .venv --python 3.12 --no-python-downloads >nul 2>&1 || uv venv .venv --no-python-downloads >nul 2>&1
)
if exist ".venv\Scripts\python.exe" goto :venv_ready

echo.
echo [WARN] Python が見つかりません。次のどちらかで用意してください。
echo   A^) このウィンドウで自動インストール（Microsoft の winget 公式リポジトリの Python.Python.3.12 を使用）
echo   B^) https://www.python.org/downloads/ から Python 3.12 を入れる（"Add python.exe to PATH" にチェック）
echo.
set /p INSTALLPY="A を実行しますか？ (Y/N): "
if /i "!INSTALLPY!"=="Y" (
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  echo.
  echo [INFO] インストールが終わったら、このウィンドウを閉じて start_windows.bat をもう一度実行してください（PATH の反映に新しいウィンドウが必要です）。
  pause & exit /b 0
)
echo [INFO] B の手順の後、start_windows.bat をもう一度実行してください。
pause & exit /b 1

:make_venv
echo [INFO] 使用する Python: %PY%
echo [1/4] 仮想環境を作成しています...
%PY% -m venv .venv || (echo [ERROR] 仮想環境の作成に失敗 & pause & exit /b 1)

:venv_ready
call ".venv\Scripts\activate.bat"
for /f "tokens=*" %%i in ('.venv\Scripts\python.exe -c "import sys;print(sys.version.split()[0])"') do set PYVER=%%i
echo [INFO] 仮想環境の Python: !PYVER!

if not exist ".venv\.deps_installed" (
  echo [2/4] 依存パッケージをインストールしています（初回のみ、数分かかります）...
  REM uv が作った仮想環境には pip が無いので、ensurepip か uv で pip を入れる
  python -m pip --version >nul 2>&1 || python -m ensurepip --upgrade >nul 2>&1
  python -m pip --version >nul 2>&1 || uv pip install --python ".venv\Scripts\python.exe" pip >nul 2>&1
  python -m pip install --upgrade pip >nul
  python -m pip install -r requirements.txt || (
    echo [ERROR] インストールに失敗しました。上のメッセージを確認してください。
    echo         Python !PYVER! 用のパッケージが無い場合は Python 3.12 を追加インストールし、.venv フォルダを削除して再実行してください。
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
  echo   A^) このウィンドウで自動インストール（Microsoft の winget 公式リポジトリの Gyan.FFmpeg を使用）
  echo   B^) ダウンロードした FFmpeg の zip を解凍し、フォルダごと "%~dp0tools" に入れる（bin を探す必要はありません）
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
