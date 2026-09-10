# SoA EDM Studio

株式会社SoA 社内用の AI EDM 制作 PWA。作曲未経験者がテキスト入力から、英語 AI ボーカル入りオリジナル EDM、固定 AI アーティスト「AERA」の MV、YouTube Shorts / TikTok 用の 25・65・90 秒版、9:16 / 16:9 フル MV、投稿文・サムネイル・投稿パッケージまでをローカル PC だけで制作し、iPhone の共有シートから代表者が最終公開します。

- 追加費用 0 円（電気代・通信費以外）。有料 API・有料クラウド GPU・有料素材は使いません。
- 楽曲生成は [ACE-Step 1.5](https://github.com/ace-step/ACE-Step-1.5)（コード MIT）の公式 REST API を別プロセスで利用。使えない環境では音源の手動アップロードで全工程を完成できます。
- AI 動画は無料 GPU Notebook（手動実行）を任意で利用。無くても FFmpeg モーショングラフィックス版で作品を完成できます。
- 完全自動投稿・非公式 API・スクレイピング・ブラウザ自動化・実在人物の模倣は行いません。

## 構成
Python 3.11〜3.14（ACE-Step 側は公式要件により 3.11/3.12） · FastAPI · Jinja2 · SQLite (SQLModel) · FFmpeg/ffprobe · librosa · Pillow · pytest · PWA。詳細は `docs/ARCHITECTURE.md`、判断記録は `docs/ADR.md`。

## いちばん簡単な起動
- Windows: `start_windows.bat` をダブルクリック（初回は仮想環境と依存を自動インストール、ブラウザが開きます。Python が無ければ winget での導入を提案（uv が入っていれば uv の Python を自動利用）、FFmpeg が無ければ winget での導入を提案、または zip を `tools` フォルダへ）
- macOS / Linux: `./start.sh`
- 操作手順はアプリ内「ガイド」タブ、または `docs/USER_GUIDE_JA.md`

## 手動セットアップ
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python scripts/diagnose.py      # docs/HARDWARE_REPORT.md を生成（実機で必ず再実行）
python run.py --open            # http://127.0.0.1:8000 をブラウザで開く（--check で前提チェックのみ）
pytest                          # テスト（FFmpeg が必要）
```
iPhone からの利用と制作の流れは `docs/QUICK_START_JA.md`、ACE-Step の導入は `docs/ACESTEP_SETUP.md`、無料 GPU Notebook は `docs/FREE_VIDEO_NOTEBOOK.md`。

## 画面
ダッシュボード / 新規プロジェクト / 生成進捗 / 3案比較 / キャラクター管理 / MV編集 / ショート編集 / 投稿準備（共有） / 分析 / 設定・ハードウェア診断（iPhone Safari 390px 対応・日本語）

## 出力（プロジェクトごと）
youtube_short_25s/65s/90s.mp4, tiktok_hook_25s / reward_65s / story_90s.mp4, full_mv_9x16.mp4, full_mv_16x9.mp4, cover_1x1.png, cover_9x16.png, thumbnail_16x9.png, lyrics_en.txt, lyrics_ja.txt, youtube_title.txt, youtube_description.txt, tiktok_caption.txt, hashtags.txt, disclosure_checklist.txt, video_generation_pack.zip, post_package.zip

## 引継ぎ
作業を引き継ぐときは `HANDOVER.md` を最初に読んでください（状態・ファイル地図・未確認事項・次の作業）。

## 状態
完成・未完成・制約は `STATUS.md`、テスト結果は `docs/TEST_REPORT.md`、未確認事項は `docs/KNOWN_LIMITATIONS.md` を参照。収益化は保証しません。

## リポジトリ内の他ファイル
`docs/khp830-redesign.html`, `docs/komeyoshi-bags-koshihikari.html`, `docs/yamagen-call-prep-2026-08-24.html` は本アプリとは無関係の既存ファイルで、変更していません。
