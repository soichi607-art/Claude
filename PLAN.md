# SoA EDM Studio — 実装計画（PLAN.md）

作成日: 2026-09-09
対象: 株式会社SoA 社内用 AI EDM 制作 PWA（localhost 運用、代表者承認で公開）

## 0. 事前確認済み事項（推測ではなく公式ソースを確認した項目）

| 項目 | 確認結果 | 出典 | 確認日 |
|---|---|---|---|
| ACE-Step 1.5 ライセンス | コードは **MIT**（`LICENSE`, README「License & Disclaimer」） | https://github.com/ace-step/ACE-Step-1.5 (commit ca1e85f, 2026-08-29) | 2026-09-09 |
| ACE-Step 1.5 対応デバイス | 「CUDA GPU recommended (also supports MPS / ROCm / Intel XPU / CPU)」 | README.md / docs/en/INSTALL.md | 2026-09-09 |
| ACE-Step 1.5 CPU実行 | 「ACE-Step can run on CPU for inference only, but performance will be significantly slower.」DiT-only (`ACESTEP_INIT_LLM=false`) 推奨 | docs/en/INSTALL.md「CPU-Only Mode」 | 2026-09-09 |
| ACE-Step 1.5 Intel GPU | 「Tested Device: Windows laptop with Ultra 9 285H integrated graphics」「Intel discrete GPUs are expected to work but not yet tested」`setup_xpu.bat` / `requirements-xpu.txt` / `README-XPU.md` あり | docs/en/INSTALL.md「Intel GPUs」, README-XPU.md | 2026-09-09 |
| ACE-Step 1.5 Python | 3.11–3.12（XPUは3.11推奨） | pyproject.toml `requires-python = ">=3.11,<3.13"`, README-XPU.md | 2026-09-09 |
| ACE-Step 1.5 生成尺 | 10秒〜600秒（`audio_duration`） | docs/en/API.md | 2026-09-09 |
| ACE-Step 1.5 REST API | `POST /release_task` → `POST /query_result` → `GET /v1/audio?path=` / `GET /health` / `GET /v1/models` / `GET /v1/stats`。既定 `127.0.0.1:8001`。認証は任意（`ACESTEP_API_KEY`） | docs/en/API.md | 2026-09-09 |
| ACE-Step 1.5 モデル重みのライセンス | **未確認**（本セッションから huggingface.co に到達不可）。導入時に https://huggingface.co/ACE-Step の各モデルカードを確認し docs/ACESTEP_SETUP.md に記録すること | — | 2026-09-09 |
| Wan2.1 ライセンス | コード/モデル **Apache-2.0**（リポジトリ `LICENSE.txt`） | https://github.com/Wan-Video/Wan2.1 | 2026-09-09 |
| Wan2.1 軽量モデル | T2V-1.3B「requires only 8.19 GB VRAM」/ I2V は 14B のみ（480P/720P） | Wan2.1 README | 2026-09-09 |
| YouTube Shorts 尺 | 2024-10-15 以降の縦/正方形動画は最大3分がShorts扱い | YouTube ヘルプ「Understand three-minute YouTube Shorts」(support.google.com/youtube/answer/15424877) ※本セッションでは検索結果経由で確認、ページ本文は到達不可 | 2026-09-09 |
| TikTok Creator Rewards | 対象動画は「duration of at least 1 minute」 | TikTok Creator Rewards Program Terms (tiktok.com/legal/page/global/creator-rewards-program-us/en) ※検索結果経由、ページ本文は到達不可 | 2026-09-09 |
| Google Colab / Kaggle 無料GPU の条件 | **未確認**（本セッションから FAQ ページに到達不可）。使用時に必ず確認し docs/FREE_VIDEO_NOTEBOOK.md の確認欄を更新すること | — | 2026-09-09 |
| Web Share API (files) | **未確認**（MDN/W3C/caniuse が本セッションから到達不可）。実装は `navigator.canShare({files})` で実行時に機能検出し、非対応時はフォールバック | — | 2026-09-09 |

「未確認」の項目はアプリ内でも「未確認」と表示し、完成扱いにしない。

## 1. 想定ハードウェアと方針

- 判明PC: Intel Core 5 120U / 16GB DDR5 / 512GB SSD / 専用GPU不明 / OS不明
- Core 5 120U の内蔵GPUは Intel Graphics（4コアXe相当）だが、**本セッションの診断は開発コンテナ上で実行**されており、実機の GPU/XPU/QSV は未確認。実機で `python scripts/diagnose.py` を再実行して `docs/HARDWARE_REPORT.md` を更新すること。
- ACE-Step 実行優先: Intel XPU → CPU → 手動アップロード。10秒テスト成功 → 30秒テスト成功 の順でのみフル生成を解放。
- 重い動画モデルは実機に入れない。AI動画は無料GPU Notebook（手動実行）か、FFmpegモーショングラフィックスで完成させる。

## 2. 技術構成

Python 3.11 / FastAPI / Jinja2 + HTMX / SQLite + SQLModel / FFmpeg・ffprobe / librosa / Pillow / pytest / PWA(manifest + service worker) / .env / ローカルファイル保存。
React・Redis・Docker は使わない（docs/ADR.md 参照）。

## 3. 実装順序（Phase）

| Phase | 内容 | 完了条件 |
|---|---|---|
| 1 | 環境診断 (`scripts/diagnose.py`, `app/services/hardware.py`) | docs/HARDWARE_REPORT.md 生成 |
| 2 | PLAN.md | 本書 |
| 3 | Web UI・DB・PWA・セキュリティ基盤 | 10画面が390pxで表示、CSRF、アップロード検証 |
| 4 | プロジェクト管理 | 入力保存、3案(A/B/C)管理、監査ログ |
| 5 | キャラクター管理 | AERA設定・プロンプト・seed・基準画像アップロード・承認フラグ |
| 6 | FFmpeg MV | 音源→9:16/16:9 モーショングラフィックスMV |
| 7 | 25/65/90/Full 版 | 尺別再編集（冒頭・構成・字幕・結末） |
| 8 | 投稿パッケージ・Web Share | post_package.zip、共有シート、フォールバック |
| 9 | ACE-Step 10秒テスト | 公式APIクライアント、実測時間記録 |
| 10 | 30秒テスト | 実測から完了予定を表示 |
| 11 | Eco モード | 30秒×3案→採用1案のみ2〜3分化 |
| 12 | Overnight モード | 夜間順次生成、休止時間、安全停止 |
| 13 | 無料GPU Notebook | ipynb 生成、video_generation_pack.zip |
| 14 | AI動画ZIP取り込み | シーン差し替え→MV再生成 |
| 15 | 分析画面 | 手動入力、未取得と0の区別、比較 |
| 16 | テスト・ドキュメント | pytest 通過、STATUS.md |

## 4. データ配置

```
data/
  soa_edm.db                 SQLite
  projects/<id>/             入力・案・音源・動画・出力
  characters/<id>/           基準画像・シート・透過PNG
  uploads/                   検証済みアップロード
  tmp/                       一時ファイル（生成後に削除）
  audit/                     プロンプト中立化ログ
```

## 5. 完了条件（要件から転記）

ローカル起動 / iPhone操作 / 3案管理 / ACE-Step可否の正しい表示 / AI動画なしでMV完成 / AI動画取り込み差し替え / 25・65・90・Full出力 / 投稿素材を2〜3操作で渡す / 有料サービス不使用 / テスト通過 / STATUS.md。
