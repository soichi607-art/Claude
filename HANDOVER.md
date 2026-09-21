# 引継ぎ（HANDOVER）— SoA EDM Studio

最終更新: 2026-09-10（2 回目の更新） / 前々セッション: https://claude.ai/code/session_01P8r19KJyeQVYZSM7AUFTXX
新しいセッションは **まずこのファイルだけ** 読めば続きができます（他のドキュメントは必要時のみ）。

## 1. 何を作ったか
株式会社SoA 社内用 AI EDM 制作 PWA。テキスト入力 → 楽曲3案（ACE-Step 1.5 API or 手動アップロード）→ 採用 → FFmpeg モーショングラフィックス MV（9:16/16:9）→ 25/65/90秒版（YouTube/TikTok）→ 投稿パッケージ → iPhone 共有シート → 成績記録。全工程が **ACE-Step なし・AI動画なしでも完成** する。
構成: Python 3.11〜3.14 / FastAPI / Jinja2 / SQLite(SQLModel) / FFmpeg / librosa / Pillow / pytest / PWA。外部 CDN・有料 API・自動投稿なし。

## 2. 場所と状態
- リポジトリ: `soichi607-art/Claude`、ブランチ `claude/soa-edm-studio-pwa-lvx0ur`（ベース: `claude/rice-bag-inquiry-prep-wawy0l` = リポジトリの既定ブランチ）
- PR: https://github.com/soichi607-art/Claude/pull/2（ドラフト、CI なし）
- ローカルクローン: 利用者の AMD 機 `C:\Users\soich\Projects\Claude`（2026-09-10 作成。`.venv` `.env` `docs/HARDWARE_REPORT.md` `data/` は git 管理外）
- テスト: `python -m pytest`。FFmpeg のある環境で 37 件（描画テストは縮小解像度）。FFmpeg が無い環境では描画・ffprobe 依存のテストが失敗する（想定内、docs/TEST_REPORT.md）

## 3. 利用者の PC（2 台）— 2026-09-10 時点の実測
| | Intel 機（HANDOVER 旧記載） | AMD 機（今回実走） |
|---|---|---|
| CPU / GPU / RAM | Core 5 120U / Intel 内蔵 / 16GB | AMD Ryzen 5 220 / Radeon 740M / 16.4GB（空き 2.5GB） |
| Python | 「最新の Python」を入れたと報告（版不明） | python.exe 無し（Store の案内だけの stub）。**uv 0.12.7 と uv 管理の CPython 3.12.14 あり** |
| FFmpeg | 「bin が無い」と報告 | 無し（PATH / tools / winget / ダウンロード いずれも未検出） |
| 起動スクリプト | 未報告 | `start_windows.bat` が uv の Python で venv 作成 → 依存導入 → `.env` 作成 → 「FFmpeg が見つかりません」案内まで到達（正常） |
| 診断 | 未実施 | `scripts/diagnose.py --no-encoder-test` 実行済み。GPU は Intel 以外の判定が出る |

## 4. 起動（利用者向け・最短）
- Windows: `start_windows.bat` をダブルクリック。Python が無ければ「A) winget で Python 3.12 を入れる」を提案（uv があれば uv の Python を自動利用）。FFmpeg が無ければ「A) winget `Gyan.FFmpeg`」を提案、または zip を `tools/` に入れる（bin を探す必要なし）
- macOS/Linux: `./start.sh`
- 手動: `pip install -r requirements.txt` → `python run.py --check` → `python run.py --open` → http://127.0.0.1:8000
- iPhone: `.env` に `SOA_HOST=0.0.0.0` + `SOA_AUTH_USER/PASSWORD`（LAN 公開は Basic 認証必須）

## 5. ファイル地図（触るならここ）
| 目的 | ファイル |
|---|---|
| 起動・前提チェック | `run.py`, `start_windows.bat`（UTF-8・CRLF・先頭で `chcp 65001`）, `start.sh`, `.gitattributes` |
| 設定（.env 読み込み） | `app/config.py`（`SOA_*`, `ACESTEP_*`。`parse_env_value` が引用符と行内コメントを除去） |
| 画面（11 画面） | `app/routers/*.py` + `app/templates/*.html`、CSS/JS は `app/static/` |
| DB モデル | `app/models.py`（None = 未取得、0 = 実際に0） |
| ACE-Step 連携 | `app/services/acestep_client.py`（公式 docs/en/API.md 準拠） |
| 生成キュー・PC保護・実測ETA・モード | `app/services/generation.py`, `safety.py` |
| プロンプト中立化・歌詞・投稿文 | `prompt_builder.py`, `lyrics.py`, `copywriter.py` |
| MV / ショート描画 | `mv_builder.py`, `shorts_builder.py`（HW エンコーダー失敗→libx264 は `_run_with_fallback`） |
| FFmpeg ラッパー・検出・エンコーダー | `app/services/ffmpeg.py`（`find_binary`, `HW_ENCODER_PRIORITY` = qsv → nvenc → amf → videotoolbox → vaapi, `encoder_args`, `pick_encoder`） |
| 診断 | `app/services/hardware.py`（`HW_ENCODERS`, CPU 名は CIM から, GPU 判定）, `scripts/diagnose.py` → `docs/HARDWARE_REPORT.md`（生成物、git 管理外） |
| ドキュメント | `README.md`, `STATUS.md`, `PLAN.md`, `docs/USER_GUIDE_JA.md`, `docs/QUICK_START_JA.md`, `docs/ACESTEP_SETUP.md`, `docs/FREE_VIDEO_NOTEBOOK.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md`, `docs/TEST_REPORT.md`, `docs/KNOWN_LIMITATIONS.md` |

## 6. 今回（2026-09-10 2 回目）直した不具合 — 理由つき
1. **`.env` の行内コメントが値に混入**: `.env.example` を `.env` にコピーすると `SOA_HOST` が `127.0.0.1   # LAN公開は…` になり、LAN モードと誤判定 → 全画面 503 / uvicorn がバインド失敗。`ACESTEP_DIR` `SOA_VIDEO_ENCODER` `ACESTEP_API_KEY` `SOA_FONT_PATH` も同様。→ `app/config.py parse_env_value` で修正、`scripts/diagnose.py` も同じパーサーを使用。テスト追加
2. **UTF-8 の bat が LF だと cmd で壊れる**: cmd は Shift-JIS として読むため「。」「し」等の末尾バイトが直後の改行や `)` を飲み込む。前版は作業ツリーが CRLF だったので偶然動いていた。→ 先頭に `chcp 65001 >nul`、`.gitattributes` で `*.bat eol=crlf`、ブロック内の `)` は `^)` でエスケープ
3. **Python 探索**: `py -3.x` → `python3.12` 等の実行ファイル名 → `python`（Store stub は import 失敗で除外）→ `uv venv --no-python-downloads`。見つからなければ winget `Python.Python.3.12` を提案（winget 公式ソースに 3.12.10 があることを 2026-09-10 確認）。uv が作る venv には pip が無いので `ensurepip` → `uv pip install pip` で補う
4. **AMD / NVIDIA の HW エンコーダー**: `h264_amf` `h264_nvenc` を候補に追加。1 秒の実動作テストに合格した順（qsv → nvenc → amf → videotoolbox → vaapi）で採用し、描画中に失敗したら libx264 に自動フォールバック（既存の仕組み）。オプションは汎用（`-b:v 8M -pix_fmt yuv420p`）のみ
5. **診断の CPU 名**: Windows で `platform.processor()` は型番しか返さないため CIM `Win32_Processor.Name` を使う。GPU が Intel 以外なら判定欄に明記

## 7. 確認済み（出典つき・PLAN.md に詳細）
- ACE-Step 1.5: コード MIT、対応デバイス CUDA / MPS / ROCm / Intel XPU / CPU、API 仕様（GitHub commit ca1e85f、2026-09-09）
- Wan2.1: Apache-2.0、T2V-1.3B は 8.19GB VRAM（GitHub README、2026-09-09）
- PyPI: 依存の Windows 用ビルドが Python 3.12/3.13/3.14 向けに存在（2026-09-10）。AMD 機で Python 3.12.14 に実際にインストール成功（2026-09-10）
- winget 公式ソース: `Gyan.FFmpeg` 9.0.1、`Python.Python.3.12` 3.12.10（`winget search --source winget`、2026-09-10）

## 8. 未確認（推測で埋めないこと）
- Intel 機（Core 5 120U）の Intel XPU・Quick Sync の可否、および Intel 機での `start_windows.bat` の結果（利用者からの報告待ち）
- AMD 機での `h264_amf` の実エンコード（FFmpeg 未導入のため）。FFmpeg 導入後に `python scripts/diagnose.py` を実行すれば「エンコーダー実動作テスト」に出る
- 実 ACE-Step の生成時間 → 設定画面の 10秒→30秒テストの実測でのみ表示
- ACE-Step / Wan2.1 のモデル重みのライセンス表記、Colab/Kaggle 規約、iOS Safari 実機での Web Share（files）
- gyan.dev の zip 内フォルダ構成 → アプリは構成非依存の再帰検索で対応

## 9. 利用者からの要望・ルール（必ず守る）
- ハルシネーション禁止。出典と確認日を示す。不明は「未確認」と書く。日本語で簡潔に。
- 電気代・通信費以外 0 円。有料 API / クラウド GPU / 素材、非公式 API、スクレイピング、自動投稿、実在人物の模倣は禁止。
- 危険な変更・削除・管理者権限・**ソフトのインストール（winget 等）は事前確認**。`.env` を git に入れない。
- 利用者は非エンジニア寄り。「bin フォルダを探す」のような前提知識を要求する説明は避け、スクリプト側で吸収する。
- リポジトリ内の `docs/khp830-redesign.html`, `docs/komeyoshi-bags-koshihikari.html`, `docs/yamagen-call-prep-2026-08-24.html` は本アプリと無関係の既存ファイル（米袋案件）。削除は利用者の明示指示がある場合のみ。

## 10. 次にやると良いこと（優先順）
1. AMD 機に FFmpeg を入れる（利用者の了承後に `winget install -e --id Gyan.FFmpeg`、または zip を `tools/` へ）→ `start_windows.bat` 再実行 → ブラウザで http://127.0.0.1:8000 が開くことを確認 → `python -m pytest` 全件
2. AMD 機の `docs/HARDWARE_REPORT.md` の「エンコーダー実動作テスト」で h264_amf の成否を見て STATUS.md に反映
3. Intel 機で `start_windows.bat` の結果（黒い画面の最後の数行）を受け取る
4. ACE-Step API 起動 → 10秒/30秒テスト → 3案生成の実測
5. PR #2 をドラフト解除してマージ（利用者の判断）
