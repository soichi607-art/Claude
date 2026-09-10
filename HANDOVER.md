# 引継ぎ（HANDOVER）— SoA EDM Studio

最終更新: 2026-09-10 / 前セッション: https://claude.ai/code/session_01P8r19KJyeQVYZSM7AUFTXX
新しいセッションは **まずこのファイルだけ** 読めば続きができます（他のドキュメントは必要時のみ）。

## 1. 何を作ったか
株式会社SoA 社内用 AI EDM 制作 PWA。テキスト入力 → 楽曲3案（ACE-Step 1.5 API or 手動アップロード）→ 採用 → FFmpeg モーショングラフィックス MV（9:16/16:9）→ 25/65/90秒版（YouTube/TikTok）→ 投稿パッケージ → iPhone 共有シート → 成績記録。全工程が **ACE-Step なし・AI動画なしでも完成** する。
構成: Python 3.11〜3.14 / FastAPI / Jinja2 / SQLite(SQLModel) / FFmpeg / librosa / Pillow / pytest / PWA。外部 CDN・有料 API・自動投稿なし。

## 2. 場所と状態
- リポジトリ: `soichi607-art/Claude`、ブランチ `claude/soa-edm-studio-pwa-lvx0ur`（ベース: `claude/rice-bag-inquiry-prep-wawy0l` = リポジトリの既定ブランチ）
- PR: https://github.com/soichi607-art/Claude/pull/2（ドラフト、コンフリクトなし、CI なし、コメントなし）
- テスト: `python -m pytest` → 35 件パス（描画テストは縮小解像度、約 2.5 分）
- 前セッションの PR 定期確認（1時間ごと）は **停止済み**。監視を再開するなら `subscribe_pr_activity` と `send_later` を使う。

## 3. 起動（利用者向け・最短）
- Windows: `start_windows.bat` をダブルクリック（Python 3.12→3.11→3.13→3.14 を自動選択、venv 作成、依存導入、FFmpeg 未検出なら winget `Gyan.FFmpeg` 導入を提案、診断、ブラウザ起動）
- macOS/Linux: `./start.sh`
- 手動: `pip install -r requirements.txt` → `python run.py --check` → `python run.py --open` → http://127.0.0.1:8000
- FFmpeg: PATH / `tools/` フォルダ配下（bin 不要、再帰検索）/ winget / ダウンロード フォルダ / `.env` の `SOA_FFMPEG` で検出
- iPhone: `.env` に `SOA_HOST=0.0.0.0` + `SOA_AUTH_USER/PASSWORD`（LAN 公開は Basic 認証必須）

## 4. ファイル地図（触るならここ）
| 目的 | ファイル |
|---|---|
| 起動・前提チェック | `run.py`, `start_windows.bat`, `start.sh` |
| 設定（.env 読み込み） | `app/config.py`（`SOA_*`, `ACESTEP_*`） |
| 画面（11 画面） | `app/routers/*.py` + `app/templates/*.html`、CSS/JS は `app/static/` |
| DB モデル | `app/models.py`（None = 未取得、0 = 実際に0） |
| ACE-Step 連携 | `app/services/acestep_client.py`（公式 docs/en/API.md 準拠: /health, /v1/models, /v1/stats, /release_task, /query_result, /v1/audio） |
| 生成キュー・PC保護・実測ETA・モード | `app/services/generation.py`, `safety.py` |
| プロンプト中立化・歌詞・投稿文 | `prompt_builder.py`, `lyrics.py`(英日対訳フレーズバンク), `copywriter.py` |
| MV / ショート描画 | `mv_builder.py`(セクション描画→concat→波形/スペクトラム/ASS歌詞/テロップ), `shorts_builder.py`(25/65/90 編集プラン+acrossfade) |
| FFmpeg ラッパー・検出 | `app/services/ffmpeg.py`（shell=False、ユーザー文字列はファイル経由、HW エンコーダー失敗→libx264 フォールバック） |
| 出力・ZIP・Notebook・取り込み | `packaging.py`, `notebook.py`, `video_import.py`, `covers.py` |
| 診断 | `app/services/hardware.py`, `scripts/diagnose.py` → `docs/HARDWARE_REPORT.md`（生成物、git 管理外） |
| ドキュメント | `README.md`, `STATUS.md`, `PLAN.md`, `docs/USER_GUIDE_JA.md`, `docs/QUICK_START_JA.md`, `docs/ACESTEP_SETUP.md`, `docs/FREE_VIDEO_NOTEBOOK.md`, `docs/ARCHITECTURE.md`, `docs/ADR.md`, `docs/TEST_REPORT.md`, `docs/KNOWN_LIMITATIONS.md` |

## 5. 確認済み（出典つき・PLAN.md に詳細）
- ACE-Step 1.5: コード MIT、CPU/Intel XPU 対応、API 仕様（GitHub リポジトリ commit ca1e85f、2026-09-09 確認）
- Wan2.1: Apache-2.0、T2V-1.3B は 8.19GB VRAM（GitHub README、2026-09-09）
- PyPI: numba/numpy/scipy/pillow 等の Windows 用ビルドが Python 3.12/3.13/3.14 向けに存在（2026-09-10）
- winget `Gyan.FFmpeg` は microsoft/winget-pkgs 公式リポジトリに登録（2026-09-10）

## 6. 未確認（推測で埋めないこと）
- 実機（Core 5 120U / 16GB）の Intel XPU・Quick Sync の可否 → 実機で `python scripts/diagnose.py`
- 実 ACE-Step の生成時間 → 設定画面の 10秒→30秒テストの実測でのみ表示
- ACE-Step / Wan2.1 のモデル重みのライセンス表記（huggingface.co 到達不可）、Colab/Kaggle 規約、iOS Safari 実機での Web Share（files）
- gyan.dev の zip 内フォルダ構成（到達不可）→ アプリは構成非依存の再帰検索で対応

## 7. 利用者からの要望・ルール（必ず守る）
- ハルシネーション禁止。出典と確認日を示す。不明は「未確認」と書く。日本語で簡潔に。
- 電気代・通信費以外 0 円。有料 API / クラウド GPU / 素材、非公式 API、スクレイピング、自動投稿、実在人物の模倣は禁止。
- 危険な変更・削除・管理者権限は事前確認。`.env` を git に入れない。
- 利用者は非エンジニア寄り。「bin フォルダを探す」のような前提知識を要求する説明は避け、スクリプト側で吸収する。

## 8. 直近の経緯（新しいセッションが知っておくべきこと）
- 利用者が「最新の Python」を入れ、FFmpeg の「bin が無い」と報告 → Python 3.13/3.14 対応と FFmpeg 自動検出・winget 提案を実装済み（コミット a62bcbd）。実機での再試行結果は **未報告**。
- リポジトリ内の `docs/khp830-redesign.html`, `docs/komeyoshi-bags-koshihikari.html`, `docs/yamagen-call-prep-2026-08-24.html` は本アプリと無関係の既存ファイル（米袋案件）。利用者の別プロジェクトのため **削除していない**。削除は利用者の明示指示がある場合のみ。

## 9. 次にやると良いこと（優先順）
1. 利用者の実機で `start_windows.bat` の結果（黒い画面の最後の数行）を受け取り、失敗があれば修正
2. 実機の `docs/HARDWARE_REPORT.md` を見て XPU/QSV の可否を STATUS.md に反映
3. ACE-Step API 起動 → 10秒/30秒テスト → 3案生成の実測
4. PR #2 をドラフト解除してマージ（利用者の判断）
